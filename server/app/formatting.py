RED = "\x01"


def format_days(name: str, days: int) -> str:
    if days == 0:
        return f"{name} — {RED}today!"
    elif days == 1:
        return f"{name} — {RED}tomorrow"
    elif days <= 2:
        return f"{name} — {RED}in {days} days"
    else:
        return f"{name} in {days} days"
