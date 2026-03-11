import json
from datetime import datetime
from .sources import dates, holidays, thoughts, weather


def _sanitize(obj):
    """Replace characters that aren't in the display's font glyphs."""
    raw = json.dumps(obj, ensure_ascii=False)
    raw = raw.replace("\u2014", "-")  # em-dash
    raw = raw.replace("\u2013", "-")  # en-dash
    return json.loads(raw)


def build() -> dict:
    """Assemble the display JSON from all data sources."""
    now = datetime.now()

    sections = []

    upcoming = dates.get_upcoming() + holidays.get_upcoming()
    upcoming.sort(key=lambda x: x[0])
    if upcoming:
        sections.append({"heading": "Upcoming", "items": [text for _, text in upcoming]})

    payload = {
        "title": "DAILY BRIEF",
        "subtitle": now.strftime("%A, %B %-d"),
        "sections": sections,
        "footer": f"Updated {now.strftime('%H:%M')}",
    }

    thought = thoughts.get_thought()
    if thought:
        payload["thought"] = thought

    wx = weather.get_weather()
    if wx:
        payload["weather"] = wx

    return _sanitize(payload)
