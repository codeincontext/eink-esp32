URGENT_DAYS = 2
URGENT_ICON = "⚠"


def format_days(name: str, days: int) -> str:
    if days == 0:
        body = f"{name} — today!"
    elif days == 1:
        body = f"{name} — tomorrow"
    else:
        body = f"{name} — in {days} days"

    if days <= URGENT_DAYS:
        return f"{URGENT_ICON} {body}"
    return body
