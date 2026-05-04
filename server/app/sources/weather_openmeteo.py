import json
import logging
from datetime import datetime
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .. import config
from . import weather_narrative

logger = logging.getLogger(__name__)

# WMO weather interpretation codes → (icon, label)
WMO_CODE = {
    0: ("☀", "Clear"),
    1: ("🌤", "Mainly clear"),
    2: ("⛅", "Partly cloudy"),
    3: ("☁", "Overcast"),
    45: ("🌫", "Fog"),
    48: ("🌫", "Fog"),
    51: ("🌦", "Light drizzle"),
    53: ("🌦", "Drizzle"),
    55: ("🌧", "Heavy drizzle"),
    56: ("🌧", "Freezing drizzle"),
    57: ("🌧", "Freezing drizzle"),
    61: ("🌦", "Light rain"),
    63: ("🌧", "Rain"),
    65: ("🌧", "Heavy rain"),
    66: ("🌧", "Freezing rain"),
    67: ("🌧", "Freezing rain"),
    71: ("🌨", "Light snow"),
    73: ("❄", "Snow"),
    75: ("❄", "Heavy snow"),
    77: ("🌨", "Snow grains"),
    80: ("🌦", "Light showers"),
    81: ("🌧", "Showers"),
    82: ("🌧", "Heavy showers"),
    85: ("🌨", "Snow showers"),
    86: ("❄", "Heavy snow showers"),
    95: ("⛈", "Thunderstorm"),
    96: ("⛈", "Thunderstorm"),
    99: ("⛈", "Thunderstorm"),
}

WALK_START = 8
WALK_END = 18
TEMP_WINDOW_START = 9  # window for computing daily high/low
TEMP_WINDOW_END = 22
HOT_THRESHOLD = 24  # °C — above this, prefer cool periods for walks

API_URL = "https://api.open-meteo.com/v1/meteofrance"
PRIMARY_MODEL = "meteofrance_arome_france_hd"
FALLBACK_MODEL = "meteofrance_arpege_europe"


def _fetch_api() -> dict | None:
    params = {
        "latitude": config.LAT,
        "longitude": config.LON,
        "models": f"{PRIMARY_MODEL},{FALLBACK_MODEL}",
        "daily": ",".join([
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "precipitation_probability_max",
            "snowfall_sum",
        ]),
        "hourly": "temperature_2m,precipitation,weather_code",
        "forecast_days": 3,
        "timezone": "auto",
    }
    url = f"{API_URL}?{urlencode(params)}"
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except (URLError, json.JSONDecodeError, OSError) as e:
        logger.warning("Open-Meteo fetch failed: %s", e)
        return None


def _pick(daily: dict, var: str, i: int):
    """Get value at index i, preferring AROME HD, falling back to ARPEGE."""
    for model in (PRIMARY_MODEL, FALLBACK_MODEL):
        series = daily.get(f"{var}_{model}", [])
        if i < len(series) and series[i] is not None:
            return series[i]
    return None


def _walk_summary(hourly: dict) -> str | None:
    times = hourly.get("time", [])
    precip = hourly.get(f"precipitation_{PRIMARY_MODEL}", [])
    temps = hourly.get(f"temperature_2m_{PRIMARY_MODEL}", [])

    today = datetime.now().strftime("%Y-%m-%d")
    hours = []
    for i, t in enumerate(times):
        if not t.startswith(today):
            continue
        hour = int(t[11:13])
        if WALK_START <= hour < WALK_END:
            hours.append({
                "hour": hour,
                "precip": (precip[i] if i < len(precip) else 0) or 0,
                "temp": (temps[i] if i < len(temps) else 0) or 0,
            })

    if not hours:
        return None

    dry_windows = []
    window_start = None
    window_end = None
    for h in hours:
        if h["precip"] == 0:
            if window_start is None:
                window_start = h
            window_end = h
        else:
            if window_start is not None:
                dry_windows.append((window_start, window_end))
                window_start = None
    if window_start is not None:
        dry_windows.append((window_start, window_end))

    if not dry_windows:
        return "No dry windows today"

    all_dry = (
        len(dry_windows) == 1
        and dry_windows[0][0]["hour"] == WALK_START
        and dry_windows[0][1]["hour"] == WALK_END - 1
    )
    day_peak = max(h["temp"] for h in hours)
    hot = day_peak > HOT_THRESHOLD
    extreme_label = "coolest" if hot else "warmest"
    extreme_fn = min if hot else max

    if all_dry:
        pick = extreme_fn(hours, key=lambda h: h["temp"])
        return f"Dry all day, {extreme_label} around {pick['hour']}h ({round(pick['temp'])}°C)"

    best = max(dry_windows, key=lambda w: w[1]["hour"] - w[0]["hour"])
    start_h = best[0]["hour"]
    end_h = best[1]["hour"] + 1
    window_temp = extreme_fn(h["temp"] for h in hours if start_h <= h["hour"] <= best[1]["hour"])
    return f"Dry {start_h}h–{end_h}h ({round(window_temp)}°C)"


# WMO codes that imply precipitation (drizzle/rain/snow/showers/thunder).
# If AROME's hourly precipitation says 0 for an hour with one of these codes,
# we treat the code as "overcast" (3) instead — the high-res precip is ground
# truth, the code is sometimes a coarser-model artifact.
_WET_CODES = frozenset({51, 53, 55, 56, 57, 61, 63, 65, 66, 67,
                         71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, 99})


def _dominant_code(hourly: dict, date_str: str) -> int | None:
    """Most-common weather code during the TEMP_WINDOW for the given date.

    Open-Meteo's daily weather_code picks the most-significant hourly code,
    so a single hour of trace drizzle dominates 23 hours of overcast.
    AROME doesn't provide weather_code (only ARPEGE does), so we use AROME's
    high-res precipitation to override "wet" codes that have no actual rain.
    """
    times = hourly.get("time", [])
    code_p = hourly.get(f"weather_code_{PRIMARY_MODEL}", [])
    code_f = hourly.get(f"weather_code_{FALLBACK_MODEL}", [])
    precip_p = hourly.get(f"precipitation_{PRIMARY_MODEL}", [])
    precip_f = hourly.get(f"precipitation_{FALLBACK_MODEL}", [])

    counts: dict[int, int] = {}
    for i, t in enumerate(times):
        if not t.startswith(date_str):
            continue
        hour = int(t[11:13])
        if not (TEMP_WINDOW_START <= hour < TEMP_WINDOW_END):
            continue
        code = code_p[i] if i < len(code_p) and code_p[i] is not None else None
        if code is None:
            code = code_f[i] if i < len(code_f) and code_f[i] is not None else None
        if code is None:
            continue
        code = int(code)
        precip = precip_p[i] if i < len(precip_p) and precip_p[i] is not None else None
        if precip is None:
            precip = precip_f[i] if i < len(precip_f) and precip_f[i] is not None else 0
        if code in _WET_CODES and not (precip and precip > 0):
            code = 3  # downgrade phantom wet codes to overcast
        counts[code] = counts.get(code, 0) + 1

    if not counts:
        return None
    return max(counts, key=counts.get)


def _daytime_extremes(hourly: dict, date_str: str) -> tuple[float | None, float | None]:
    """Min and max temp for the given date, restricted to TEMP_WINDOW hours."""
    times = hourly.get("time", [])
    primary = hourly.get(f"temperature_2m_{PRIMARY_MODEL}", [])
    fallback = hourly.get(f"temperature_2m_{FALLBACK_MODEL}", [])
    temps = []
    for i, t in enumerate(times):
        if not t.startswith(date_str):
            continue
        hour = int(t[11:13])
        if not (TEMP_WINDOW_START <= hour < TEMP_WINDOW_END):
            continue
        v = primary[i] if i < len(primary) and primary[i] is not None else None
        if v is None:
            v = fallback[i] if i < len(fallback) and fallback[i] is not None else None
        if v is not None:
            temps.append(v)
    if not temps:
        return None, None
    return max(temps), min(temps)


def _format_body(icon: str, condition: str, high: int, low: int, today: bool = False) -> str:
    prefix = f"{icon} " if icon else ""
    temp = f"{high}°C (min {low})" if today else f"{high}/{low}°C"
    return f"{prefix}{condition}, {temp}"


def _format_summary(label: str, body: str) -> str:
    return f"{label}: {body}" if label else body


def _format_precip(rain_mm: float, snow_cm: float, prob) -> str:
    parts = []
    if snow_cm > 0:
        parts.append(f"{round(snow_cm)}cm snow")
    if rain_mm > 0:
        parts.append(f"{round(rain_mm)}mm rain")
    if not parts:
        return ""
    text = " + ".join(parts)
    if prob:
        text += f" ({prob}%)"
    return text


def get_weather() -> dict | None:
    if not config.LAT or not config.LON:
        return None

    data = _fetch_api()
    if data is None:
        return None

    daily = data.get("daily", {})
    times = daily.get("time", [])
    if not times:
        return None

    slot_keys = ["today", "tomorrow", "day3"]
    days = {}
    for i, key in enumerate(slot_keys):
        if i >= len(times):
            break
        code = _dominant_code(data.get("hourly", {}), times[i])
        if code is None:
            code = _pick(daily, "weather_code", i)
        icon, condition = WMO_CODE.get(int(code), ("", "?")) if code is not None else ("", "?")
        dt = datetime.strptime(times[i], "%Y-%m-%d")
        label = "" if i == 0 else dt.strftime("%A")
        label_short = "" if i == 0 else dt.strftime("%a")
        hi_raw, lo_raw = _daytime_extremes(data.get("hourly", {}), times[i])
        high = round(hi_raw) if hi_raw is not None else round(_pick(daily, "temperature_2m_max", i) or 0)
        low = round(lo_raw) if lo_raw is not None else round(_pick(daily, "temperature_2m_min", i) or 0)
        rain_mm = round(_pick(daily, "precipitation_sum", i) or 0, 1)
        snow_cm = round(_pick(daily, "snowfall_sum", i) or 0, 1)
        precip_prob = _pick(daily, "precipitation_probability_max", i)
        is_today = i == 0
        body = _format_body("", condition, high, low, today=is_today)
        days[key] = {
            "summary": _format_summary(label, body),
            "label": label,
            "label_short": label_short,
            "body": body,
            "precip_summary": _format_precip(rain_mm, snow_cm, precip_prob),
            "icon": icon,
            "condition": condition,
            "high": high,
            "low": low,
            "rain_mm": rain_mm,
            "snow_cm": snow_cm,
            "precip_prob": precip_prob,
        }

    result = {"days": days}

    hourly = data.get("hourly")
    if hourly:
        walk = _walk_summary(hourly)
        if walk:
            result["walk"] = walk

        day_dates = [(k, times[i]) for i, k in enumerate(slot_keys) if i < len(times)]
        narratives = weather_narrative.get_narratives(
            hourly, day_dates, PRIMARY_MODEL, FALLBACK_MODEL
        )
        if narratives:
            for slot, text in narratives.items():
                if slot in days:
                    days[slot]["narrative"] = text

    return result
