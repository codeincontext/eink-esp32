from datetime import datetime
from .sources import dates, holidays, thoughts, weather_openmeteo as weather

UPCOMING_SLOTS = 5
EMPTY_TEXT = "​"  # zero-width space — non-whitespace, renders as nothing


def build() -> dict:
    """Assemble the SensCraft push payload from all data sources."""
    now = datetime.now()

    raw = sorted(
        dates.get_upcoming() + holidays.get_upcoming(),
        key=lambda x: x["days_remaining"],
    )
    upcoming = [
        raw[i] if i < len(raw) else {"text": EMPTY_TEXT, "days_remaining": -1}
        for i in range(UPCOMING_SLOTS)
    ]

    payload: dict = {
        "date": now.strftime("%A, %B %-d"),
        "footer": f"Updated {now.strftime('%H:%M')}",
        "upcoming": upcoming,
    }

    thought = thoughts.get_thought()
    if thought:
        payload["thought"] = thought

    wx = weather.get_weather()
    if wx:
        payload["weather"] = wx.get("days", {})
        if "walk" in wx:
            payload["walk"] = wx["walk"]

    return payload
