import hashlib
import json
import time
import traceback

from . import config
from . import display
from . import ha_publish
from . import senscraft


def _content_hash(payload: dict) -> str:
    """Hash the display content, ignoring the footer (which has a timestamp)."""
    hashable = {k: v for k, v in payload.items() if k != "footer"}
    return hashlib.sha256(json.dumps(hashable, sort_keys=True).encode()).hexdigest()


def main() -> None:
    print("eink-server starting")
    print(f"  SensCraft device: {config.SENSECRAFT_DEVICE_ID}")
    if config.HA_URL:
        print(f"  HA: {config.HA_URL} (prefix {config.HA_ENTITY_PREFIX})")
    print(f"  Poll interval: {config.POLL_INTERVAL}s")
    print(f"  Data dir: {config.DATA_DIR}")

    last_hash = None

    while True:
        try:
            payload = display.build()
            h = _content_hash(payload)

            if h != last_hash:
                print(f"Content changed (hash: {h[:12]}...)")
                senscraft.publish(payload)
                ha_publish.publish(payload)
                last_hash = h
            else:
                print("No changes, skipping publish")

        except Exception:
            traceback.print_exc()

        time.sleep(config.POLL_INTERVAL)


if __name__ == "__main__":
    main()
