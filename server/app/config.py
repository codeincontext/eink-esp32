import os

SENSECRAFT_API_URL = os.environ.get(
    "SENSECRAFT_API_URL",
    "https://sensecraft-hmi-api.seeed.cc/api/v1/user/device/push_data",
)
SENSECRAFT_API_KEY = os.environ.get("SENSECRAFT_API_KEY", "")
SENSECRAFT_DEVICE_ID = int(os.environ.get("SENSECRAFT_DEVICE_ID", "0"))

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "300"))
DATA_DIR = os.environ.get("DATA_DIR", "data")

# Location — shared by all weather providers; falls back to METEOBLUE_* for compat
LAT = os.environ.get("LAT", os.environ.get("METEOBLUE_LAT", ""))
LON = os.environ.get("LON", os.environ.get("METEOBLUE_LON", ""))

METEOBLUE_API_KEY = os.environ.get("METEOBLUE_API_KEY", "")
METEOBLUE_LAT = LAT
METEOBLUE_LON = LON

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
