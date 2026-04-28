import os
from datetime import date, timedelta
from .. import config
from ..formatting import format_days


def _easter(year: int) -> date:
    """Compute Easter Sunday using the Anonymous Gregorian algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _uk_mothers_day(year: int) -> date:
    """Mothering Sunday: 3 weeks before Easter."""
    return _easter(year) - timedelta(weeks=3)


def _french_mothers_day(year: int) -> date:
    """Fête des Mères: last Sunday of May, unless that's Pentecost,
    then first Sunday of June."""
    pentecost = _easter(year) + timedelta(days=49)
    may_31 = date(year, 5, 31)
    last_sun_may = may_31 - timedelta(days=(may_31.weekday() + 1) % 7)
    if last_sun_may == pentecost:
        return last_sun_may + timedelta(weeks=1)
    return last_sun_may


def _parse_ics(path: str, year: int) -> list[tuple[date, str]]:
    """Extract VEVENT entries from an .ics file for the given year."""
    events = []
    if not os.path.exists(path):
        return events

    with open(path) as f:
        lines = f.readlines()

    summary = None
    dtstart = None
    for line in lines:
        line = line.strip()
        if line.startswith("SUMMARY:"):
            summary = line[8:]
        elif line.startswith("DTSTART") and ":" in line:
            val = line.split(":")[-1]
            if len(val) >= 8:
                try:
                    d = date(int(val[:4]), int(val[4:6]), int(val[6:8]))
                    dtstart = d
                except ValueError:
                    dtstart = None
        elif line == "END:VEVENT" and summary and dtstart:
            if dtstart.year == year:
                events.append((dtstart, summary))
            summary = None
            dtstart = None

    return events


def get_upcoming() -> list[dict]:
    """Return {days_remaining, text} for upcoming holidays."""
    today = date.today()
    warn_days = 14
    upcoming = []

    computed = [
        (_uk_mothers_day(today.year), "UK Mother's Day"),
        (_french_mothers_day(today.year), "French Mother's Day"),
    ]
    for d, name in computed:
        delta = (d - today).days
        if 0 <= delta <= warn_days:
            upcoming.append({"days_remaining": delta, "text": format_days(name, delta)})

    ics_path = os.path.join(config.DATA_DIR, "holidays.ics")
    for d, name in _parse_ics(ics_path, today.year):
        delta = (d - today).days
        if 0 <= delta <= warn_days:
            upcoming.append({"days_remaining": delta, "text": format_days(name, delta)})

    return upcoming
