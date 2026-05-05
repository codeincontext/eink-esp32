import os

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "300"))
DATA_DIR = os.environ.get("DATA_DIR", "data")

# Location — shared by all weather providers; falls back to METEOBLUE_* for compat
LAT = os.environ.get("LAT", os.environ.get("METEOBLUE_LAT", ""))
LON = os.environ.get("LON", os.environ.get("METEOBLUE_LON", ""))

METEOBLUE_API_KEY = os.environ.get("METEOBLUE_API_KEY", "")
METEOBLUE_LAT = LAT
METEOBLUE_LON = LON

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

HA_URL = os.environ.get("HA_URL", "")  # e.g. http://homeassistant.local:8123
HA_TOKEN = os.environ.get("HA_TOKEN", "")  # long-lived access token
HA_ENTITY_PREFIX = os.environ.get("HA_ENTITY_PREFIX", "sensor.eink_")
