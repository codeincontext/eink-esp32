"""Publish daily-brief payload to Home Assistant as auto-created entities.

Each leaf field becomes one entity (e.g. ``sensor.eink_weather_today_body``).
HA creates the entity on first PUT to ``/api/states/{entity_id}``; subsequent
PUTs update its state. Errors on individual entities are logged but don't
break the rest — partial publishes are better than none.
"""
import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import config

logger = logging.getLogger(__name__)


def _flatten(payload: dict, prefix: str = "") -> dict:
    """Walk the nested payload, returning {entity_suffix: scalar_value}.

    Lists become indexed keys (``upcoming_0_text``). Dicts recurse.
    Scalar values (str, int, float, bool, None) are emitted as-is.
    """
    out: dict = {}
    for k, v in payload.items():
        key = f"{prefix}{k}" if not prefix else f"{prefix}_{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    out.update(_flatten(item, f"{key}_{i}"))
                else:
                    out[f"{key}_{i}"] = item
        else:
            out[key] = v
    return out


def _put_state(entity_id: str, state, headers: dict) -> None:
    body = json.dumps({"state": "" if state is None else str(state)}).encode("utf-8")
    url = f"{config.HA_URL.rstrip('/')}/api/states/{entity_id}"
    req = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=5) as resp:
            if resp.status >= 300:
                logger.warning("HA publish %s: status %s", entity_id, resp.status)
    except HTTPError as e:
        logger.warning("HA publish %s: HTTP %s", entity_id, e.code)
    except (URLError, OSError) as e:
        logger.warning("HA publish %s: %s", entity_id, e)


def publish(payload: dict) -> None:
    if not config.HA_URL or not config.HA_TOKEN:
        return  # not configured — silently skip

    headers = {
        "Authorization": f"Bearer {config.HA_TOKEN}",
        "Content-Type": "application/json",
    }
    flat = _flatten(payload)
    for suffix, value in flat.items():
        _put_state(f"{config.HA_ENTITY_PREFIX}{suffix}", value, headers)
    print(f"HA: published {len(flat)} entities to {config.HA_URL}")
