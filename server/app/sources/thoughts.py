import os
from datetime import date

import yaml

from .. import config


def get_thought() -> dict | None:
    """Pick a thought for today, rotating daily through thoughts.yml."""
    path = os.path.join(config.DATA_DIR, "thoughts.yml")
    if not os.path.exists(path):
        return None

    with open(path) as f:
        thoughts = yaml.safe_load(f)

    if not thoughts:
        return None

    index = date.today().toordinal() % len(thoughts)
    t = thoughts[index]

    return {
        "text": t.get("text", ""),
        "author": t.get("author", ""),
        "context": t.get("context", ""),
    }
