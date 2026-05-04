"""LLM-generated weather narratives.

Memoised by hash of the input data so identical hourly forecasts always
produce the same narrative — avoids spurious e-ink refreshes from non-
deterministic LLM output.
"""
import hashlib
import json
import logging
from datetime import datetime

from anthropic import Anthropic, APIError

from .. import config

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
NARRATIVE_HOURS = range(6, 23)  # hours included per day in the LLM prompt

# WMO codes implying precipitation. If hourly precip is 0 we downgrade these
# to overcast (3) before showing the LLM — same fix as in weather_openmeteo.
_WET_CODES = frozenset({51, 53, 55, 56, 57, 61, 63, 65, 66, 67,
                         71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, 99})

# Single-entry memo: {input_hash: {today, tomorrow, day3}}
_cache: dict[str, dict[str, str]] = {}


def _build_inputs(hourly: dict, day_dates: list[tuple[str, str]],
                  primary_model: str, fallback_model: str) -> dict:
    """Build the per-day hourly slice the LLM will see.

    day_dates: [("today", "2026-05-04"), ("tomorrow", "2026-05-05"), ...]
    Returns: {slot: [{hour, code, precip_mm, temp_c}, ...], ...}
    """
    times = hourly.get("time", [])
    code_p = hourly.get(f"weather_code_{primary_model}", [])
    code_f = hourly.get(f"weather_code_{fallback_model}", [])
    precip_p = hourly.get(f"precipitation_{primary_model}", [])
    precip_f = hourly.get(f"precipitation_{fallback_model}", [])
    temp_p = hourly.get(f"temperature_2m_{primary_model}", [])
    temp_f = hourly.get(f"temperature_2m_{fallback_model}", [])

    def pick(arr_p, arr_f, i):
        if i < len(arr_p) and arr_p[i] is not None:
            return arr_p[i]
        if i < len(arr_f) and arr_f[i] is not None:
            return arr_f[i]
        return None

    out: dict[str, list] = {}
    for slot, date_str in day_dates:
        rows = []
        for i, t in enumerate(times):
            if not t.startswith(date_str):
                continue
            hour = int(t[11:13])
            if hour not in NARRATIVE_HOURS:
                continue
            code = pick(code_p, code_f, i)
            precip = pick(precip_p, precip_f, i) or 0
            temp = pick(temp_p, temp_f, i)
            code_int = int(code) if code is not None else None
            if code_int in _WET_CODES and precip <= 0:
                code_int = 3  # downgrade phantom wet codes
            rows.append({
                "h": hour,
                "code": code_int,
                "precip": round(precip, 1),
                "temp": round(temp) if temp is not None else None,
            })
        out[slot] = rows
    return out


def _input_hash(inputs: dict) -> str:
    return hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()


PROMPT_HEADER = """You write short weather summaries for a personal e-ink dashboard for a French alpine valley. Given hourly forecast data for three days, write ONE conversational sentence per day capturing the temporal pattern (when rain starts/stops, peak warmth or chill, fog clearing, etc.). 10–15 words per sentence. Plain prose, no emojis, no markdown.

Weather code reference (WMO):
0–3 clear/cloudy, 45/48 fog, 51–57 drizzle, 61–67 rain, 71–77 snow, 80–86 showers, 95–99 thunderstorm.

Hourly data (h=hour, code=WMO, precip=mm, temp=°C):
"""


def _format_prompt(day_labels: dict[str, str], inputs: dict) -> str:
    parts = [PROMPT_HEADER]
    for slot, rows in inputs.items():
        parts.append(f"\n{day_labels.get(slot, slot)}:")
        for r in rows:
            parts.append(f"  {r['h']:02d}h code={r['code']} precip={r['precip']} temp={r['temp']}")
    parts.append('\n\nReturn JSON only, no prose: {"today": "...", "tomorrow": "...", "day3": "..."}')
    return "\n".join(parts)


def get_narratives(hourly: dict, day_dates: list[tuple[str, str]],
                    primary_model: str, fallback_model: str) -> dict[str, str] | None:
    """Return {today, tomorrow, day3} narratives, or None on any failure.

    day_dates: [("today", "2026-05-04"), ("tomorrow", "2026-05-05"), ("day3", "2026-05-06")]
    """
    if not config.ANTHROPIC_API_KEY:
        return None

    inputs = _build_inputs(hourly, day_dates, primary_model, fallback_model)
    h = _input_hash(inputs)
    if h in _cache:
        return _cache[h]

    day_labels = {}
    for slot, date_str in day_dates:
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            day_labels[slot] = f"{slot.capitalize()} ({dt.strftime('%A %B %-d')})"
        except ValueError:
            day_labels[slot] = slot

    prompt = _format_prompt(day_labels, inputs)

    try:
        client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        # Strip code fences if the model added them
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        result = json.loads(text)
    except (APIError, json.JSONDecodeError, IndexError, KeyError) as e:
        logger.warning("Narrative generation failed: %s", e)
        return None

    _cache.clear()
    _cache[h] = result
    return result
