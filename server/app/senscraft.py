import json
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

from . import config


def publish(payload: dict) -> None:
    body = json.dumps(
        {"device_id": config.SENSECRAFT_DEVICE_ID, "data": payload},
        ensure_ascii=False,
    ).encode("utf-8")

    req = Request(
        config.SENSECRAFT_API_URL,
        data=body,
        headers={
            "api-key": config.SENSECRAFT_API_KEY,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(req, timeout=10) as resp:
            resp_body = resp.read().decode("utf-8", errors="replace")
            print(f"SensCraft: pushed {len(body)} bytes, status {resp.status}: {resp_body[:200]}")
    except HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"SensCraft: HTTP {e.code}: {err_body[:200]}")
        raise
    except URLError as e:
        print(f"SensCraft: network error: {e.reason}")
        raise
