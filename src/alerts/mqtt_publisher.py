"""
mqtt_publisher.py
-----------------
Publication MQTT des alertes et lectures IoT.
Utilise paho-mqtt pour publier sur le broker configuré.
Configuration stockée dans mqtt_config.json.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_FILE = Path(__file__).parent.parent.parent / "mqtt_config.json"

_DEFAULT = {
    "active":       False,
    "broker":       "localhost",
    "port":         1883,
    "username":     "",
    "password":     "",
    "topic_prefix": "iot",
    # TLS (optionnel)
    "tls_enabled":  False,
    "tls_ca_cert":  "",        # chemin vers le fichier CA (ex: /certs/ca.crt)
    "tls_certfile": "",        # certificat client (optionnel)
    "tls_keyfile":  "",        # clé privée client (optionnel)
}


def _load() -> dict:
    if CONFIG_FILE.exists():
        try:
            return {**_DEFAULT, **json.loads(CONFIG_FILE.read_text(encoding="utf-8"))}
        except Exception:
            pass
    return dict(_DEFAULT)


def get_config() -> dict:
    cfg  = _load()
    safe = dict(cfg)
    if safe.get("password"):
        safe["password"] = "***"
    return safe


def set_config(**kwargs) -> dict:
    cfg = _load()
    for k, v in kwargs.items():
        if k in cfg and v is not None:
            cfg[k] = v
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return get_config()


class MQTTPublisher:
    """Publie alertes et lectures sur un broker MQTT."""

    def __init__(self):
        self._client = None
        self._cfg    = {}

    def connect(self):
        """Connecte au broker si la config est active."""
        cfg = _load()
        if not cfg.get("active"):
            return False
        try:
            import paho.mqtt.client as mqtt
            client = mqtt.Client()
            if cfg.get("username"):
                client.username_pw_set(cfg["username"], cfg.get("password", ""))
            # TLS
            if cfg.get("tls_enabled"):
                ca_cert  = cfg.get("tls_ca_cert")  or None
                certfile = cfg.get("tls_certfile") or None
                keyfile  = cfg.get("tls_keyfile")  or None
                client.tls_set(
                    ca_certs=ca_cert,
                    certfile=certfile,
                    keyfile=keyfile,
                )
                logger.info("MQTT TLS activé")
            client.connect(cfg["broker"], int(cfg["port"]), keepalive=60)
            client.loop_start()
            self._client = client
            self._cfg    = cfg
            logger.info(f"MQTT connecté : {cfg['broker']}:{cfg['port']}")
            return True
        except Exception as e:
            logger.warning(f"MQTT connexion impossible : {e}")
            self._client = None
            return False

    def disconnect(self):
        if self._client:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
            self._client = None

    def publish_alert(self, alert: dict):
        """Publie une alerte sur iot/alerts/{sensor}."""
        if not self._client:
            return
        try:
            prefix = self._cfg.get("topic_prefix", "iot")
            sensor = alert.get("sensor", "unknown")
            topic  = f"{prefix}/alerts/{sensor}"
            self._client.publish(topic, json.dumps(alert, ensure_ascii=False), qos=1)
        except Exception:
            pass

    def publish_reading(self, reading: dict):
        """Publie une lecture sur iot/readings/{sensor}."""
        if not self._client:
            return
        try:
            prefix = self._cfg.get("topic_prefix", "iot")
            sensor = reading.get("sensor", "unknown")
            topic  = f"{prefix}/readings/{sensor}"
            self._client.publish(topic, json.dumps(reading, ensure_ascii=False), qos=0)
        except Exception:
            pass


# Instance globale (initialisée dans main.py lifespan)
_publisher: MQTTPublisher | None = None


def get_publisher() -> MQTTPublisher | None:
    return _publisher


def init_publisher() -> MQTTPublisher:
    global _publisher
    _publisher = MQTTPublisher()
    _publisher.connect()
    return _publisher


def shutdown_publisher():
    global _publisher
    if _publisher:
        _publisher.disconnect()
        _publisher = None


def publish_alert(alert: dict):
    """Publie une alerte via le publisher global (si disponible et actif)."""
    cfg = _load()
    if not cfg.get("active"):
        return
    if _publisher:
        _publisher.publish_alert(alert)
