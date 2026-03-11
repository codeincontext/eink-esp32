import os

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")
MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "eink/display")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "300"))
DATA_DIR = os.environ.get("DATA_DIR", "data")

METEOBLUE_API_KEY = os.environ.get("METEOBLUE_API_KEY", "")
METEOBLUE_LAT = os.environ.get("METEOBLUE_LAT", "")
METEOBLUE_LON = os.environ.get("METEOBLUE_LON", "")
