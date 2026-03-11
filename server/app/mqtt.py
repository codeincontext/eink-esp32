import json
import paho.mqtt.client as mqtt
from . import config


def publish(payload: dict) -> None:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if config.MQTT_USER:
        client.username_pw_set(config.MQTT_USER, config.MQTT_PASSWORD)
    client.connect(config.MQTT_HOST, config.MQTT_PORT)
    msg = json.dumps(payload, ensure_ascii=False)
    client.publish(config.MQTT_TOPIC, msg, qos=1, retain=True)
    client.disconnect()
    print(f"MQTT: published {len(msg)} bytes to {config.MQTT_TOPIC}")
