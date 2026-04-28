import os
from datetime import date, datetime
import yaml
from .. import config
from ..formatting import format_days


def _days_until(entry_date: str, today: date) -> int | None:
    """Return days until a date, or None if it's in the past.

    Supports DD-MM (recurring yearly) and YYYY-MM-DD (one-time).
    """
    if len(entry_date) == 5:
        day, month = int(entry_date[:2]), int(entry_date[3:])
        this_year = date(today.year, month, day)
        if this_year < today:
            this_year = date(today.year + 1, month, day)
        return (this_year - today).days
    else:
        target = datetime.strptime(entry_date, "%Y-%m-%d").date()
        delta = (target - today).days
        return delta if delta >= 0 else None


def get_upcoming() -> list[dict]:
    """Read dates.yml and return {days_remaining, text} for upcoming events."""
    path = os.path.join(config.DATA_DIR, "dates.yml")
    if not os.path.exists(path):
        return []

    with open(path) as f:
        entries = yaml.safe_load(f) or []

    today = date.today()
    upcoming = []

    for entry in entries:
        name = entry["name"]
        warn_days = entry.get("warn_days", 14)
        days = _days_until(entry["date"], today)
        if days is not None and days <= warn_days:
            upcoming.append({"days_remaining": days, "text": format_days(name, days)})

    return upcoming
