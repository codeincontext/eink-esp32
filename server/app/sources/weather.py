import logging
import os
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError
import json

from .. import config

logger = logging.getLogger(__name__)

PICTOCODE = {
    1: "Clear",
    2: "Mostly sunny",
    3: "Partly cloudy",
    4: "Overcast",
    5: "Fog",
    6: "Rain",
    7: "Showers",
    8: "Thunderstorms",
    9: "Snow",
    10: "Snow showers",
    11: "Rain/snow mix",
    12: "Light rain",
    13: "Light snow",
    14: "Rain",
    15: "Snow",
    16: "Light rain",
    17: "Light snow",
}

RED = "\x01"

WALK_START = 8
WALK_END = 18
DAYTIME_START = 7
DAYTIME_END = 21
CACHE_MAX_AGE = 1800  # seconds

CACHE_PATH = os.path.join(config.DATA_DIR, ".weather_cache.json")


def _load_cache() -> dict | None:
    """Load cached API response if fresh enough and daytime."""
    if not os.path.exists(CACHE_PATH):
        return None

    try:
        with open(CACHE_PATH) as f:
            cache = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    fetched = datetime.fromisoformat(cache.get("fetched", ""))
    now = datetime.now()
    age = (now - fetched).total_seconds()

    if age > CACHE_MAX_AGE:
        return None

    # Cache from a different day is stale
    if fetched.date() != now.date():
        return None

    return cache.get("data")


def _save_cache(data: dict) -> None:
    try:
        with open(CACHE_PATH, "w") as f:
            json.dump({"fetched": datetime.now().isoformat(), "data": data}, f)
    except OSError as e:
        logger.warning("Failed to write weather cache: %s", e)


def _fetch_api() -> dict | None:
    url = (
        f"https://my.meteoblue.com/packages/basic-day_basic-1h"
        f"?lat={config.METEOBLUE_LAT}"
        f"&lon={config.METEOBLUE_LON}"
        f"&apikey={config.METEOBLUE_API_KEY}"
        f"&format=json"
    )

    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except (URLError, json.JSONDecodeError, OSError) as e:
        logger.warning("Meteoblue fetch failed: %s", e)
        return None

    _save_cache(data)
    return data


def _walk_summary(hourly: dict) -> str | None:
    """Find the best dog walking window from hourly data (8:00-18:00 today)."""
    times = hourly.get("time", [])
    precip = hourly.get("precipitation", [])
    temps = hourly.get("temperature", [])

    today = datetime.now().strftime("%Y-%m-%d")
    hours = []
    for i, t in enumerate(times):
        if not t.startswith(today):
            continue
        hour = int(t[11:13])
        if WALK_START <= hour < WALK_END:
            hours.append({
                "hour": hour,
                "precip": precip[i] if i < len(precip) else 0,
                "temp": temps[i] if i < len(temps) else 0,
            })

    if not hours:
        return None

    dry_windows = []
    window_start = None
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

    all_dry = (
        len(dry_windows) == 1
        and dry_windows[0][0]["hour"] == WALK_START
        and dry_windows[0][1]["hour"] == WALK_END - 1
    )

    if not dry_windows:
        return f"{RED}No dry windows today"

    if all_dry:
        warmest = max(hours, key=lambda h: h["temp"])
        return f"Dry all day, warmest around {warmest['hour']}:00 ({round(warmest['temp'])}\u00b0C)"

    best = max(dry_windows, key=lambda w: w[1]["hour"] - w[0]["hour"])
    start_h = best[0]["hour"]
    end_h = best[1]["hour"] + 1
    duration = end_h - start_h
    best_temp = max(h["temp"] for h in hours if start_h <= h["hour"] <= best[1]["hour"])
    text = f"Dry {start_h}:00\u2013{end_h}:00 ({round(best_temp)}\u00b0C)"
    if duration <= 3:
        return f"{RED}{text}"
    return text


def get_weather() -> dict | None:
    """Fetch today + next 2 days from Meteoblue, with daytime-only caching."""
    if not config.METEOBLUE_API_KEY or not config.METEOBLUE_LAT:
        return None

    now = datetime.now()
    is_daytime = DAYTIME_START <= now.hour < DAYTIME_END

    # Try cache first
    data = _load_cache()
    if data is None:
        if is_daytime:
            logger.info("Weather: fetching from API")
            data = _fetch_api()
        else:
            # Nighttime with stale/no cache — serve stale if available
            logger.info("Weather: nighttime, using stale cache if available")
            if os.path.exists(CACHE_PATH):
                try:
                    with open(CACHE_PATH) as f:
                        data = json.load(f).get("data")
                except (json.JSONDecodeError, OSError):
                    data = None

    if data is None:
        return None

    day = data.get("data_day", {})
    times = day.get("time", [])
    if not times:
        return None

    days = []
    for i in range(min(3, len(times))):
        picto = day.get("pictocode", [None])[i]
        dt = datetime.strptime(times[i], "%Y-%m-%d")
        label = "" if i == 0 else dt.strftime("%A")
        total_mm = day["precipitation"][i]
        snow_frac = day.get("snowfraction", [0])[i] or 0
        rain_mm = round(total_mm * (1 - snow_frac), 1)
        snow_cm = round(total_mm * snow_frac, 1)  # 1mm water ≈ 1cm snow
        days.append({
            "label": label,
            "high": round(day["temperature_max"][i]),
            "low": round(day["temperature_min"][i]),
            "condition": PICTOCODE.get(picto, "?"),
            "rain_mm": rain_mm,
            "snow_cm": snow_cm,
            "precip_prob": day.get("precipitation_probability", [None])[i],
        })

    result = {"days": days}

    hourly = data.get("data_1h")
    if hourly:
        walk = _walk_summary(hourly)
        if walk:
            result["walk"] = walk

    return result
