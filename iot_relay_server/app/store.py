import random
from collections import deque
from datetime import datetime, timezone
from uuid import uuid4

from app.config import settings

MAX_READINGS = 2000

sensor_readings: deque[dict] = deque(maxlen=MAX_READINGS)
irrigation_events: list[dict] = []
sensor_alerts: list[dict] = []


# 이전 토양 습도 추정값 (시간 관성용)
_prev_soil_moisture: float | None = None


def _estimate_soil_moisture(temperature: float, humidity: float, light_intensity: float) -> float:
    """온도·대기 습도·조도를 기반으로 토양 습도를 추정한다.

    원리:
      - 토양은 기본적으로 수분을 보유 (기본값 55%)
      - 대기 습도 ↑ → 증발 억제 → 토양 습도 ↑
      - 온도 ↑     → 증발 증가 → 토양 습도 ↓
      - 조도 ↑     → 일사량 증가 → 토양 습도 ↓
      - 시간 관성   → 토양 습도는 급변하지 않으므로 이전 값과 블렌딩
    """
    global _prev_soil_moisture

    # 1) 토양 기본 보유 수분
    base = 55.0

    # 2) 대기 습도 보정: 50% 기준, ±0.3%p per 1%
    humidity_effect = (humidity - 50) * 0.3

    # 3) 온도 보정: 20℃ 기준, 1℃당 -0.4%
    temp_effect = (temperature - 20) * 0.4

    # 4) 조도 보정: 높을수록 건조
    light_effect = (light_intensity / 100) * 2

    # 5) 추정값 산출
    estimated = base + humidity_effect - temp_effect - light_effect

    # 6) 자연스러운 노이즈 (±2%)
    estimated += random.uniform(-2.0, 2.0)

    # 7) 시간 관성: 이전 값 70% + 새 추정값 30%
    if _prev_soil_moisture is not None:
        estimated = _prev_soil_moisture * 0.7 + estimated * 0.3

    # 8) 현실적 범위 제한 (20~85%)
    estimated = max(20.0, min(85.0, estimated))
    _prev_soil_moisture = estimated

    return round(estimated, 1)


def add_reading(device_id: str, sensors: dict, timestamp: datetime | None = None) -> list[dict]:
    ts = timestamp or datetime.now(timezone.utc)

    # 토양 습도: ESP8266에서 안 보내면 다른 센서값 기반으로 추정
    soil_moisture = sensors.get("soil_moisture")
    if soil_moisture is None:
        soil_moisture = _estimate_soil_moisture(
            temperature=sensors["temperature"],
            humidity=sensors["humidity"],
            light_intensity=sensors["light_intensity"],
        )

    reading = {
        "device_id": device_id,
        "timestamp": ts.isoformat(),
        "soilMoisture": soil_moisture,
        "temperature": sensors["temperature"],
        "humidity": sensors["humidity"],
        "lightIntensity": sensors["light_intensity"],
    }
    sensor_readings.appendleft(reading)

    new_alerts: list[dict] = []

    if soil_moisture < settings.SOIL_MOISTURE_LOW:
        alert = {
            "id": str(uuid4()),
            "type": "moisture",
            "severity": "경고",
            "message": f"토양 습도가 {soil_moisture}%로 임계값 이하입니다",
            "timestamp": ts.isoformat(),
            "resolved": False,
        }
        sensor_alerts.append(alert)
        new_alerts.append(alert)

        irrigation_events.append({
            "id": str(uuid4()),
            "triggeredAt": ts.isoformat(),
            "reason": f"토양 습도 {soil_moisture}% — 임계값({settings.SOIL_MOISTURE_LOW}%) 이하",
            "valveAction": "열림",
            "duration": 30,
            "autoTriggered": True,
        })

    if sensors["humidity"] > 90:
        alert = {
            "id": str(uuid4()),
            "type": "humidity",
            "severity": "주의",
            "message": f"대기 습도 {sensors['humidity']}%. 병해 발생 위험 증가",
            "timestamp": ts.isoformat(),
            "resolved": False,
        }
        sensor_alerts.append(alert)
        new_alerts.append(alert)

    return new_alerts


def get_latest() -> dict | None:
    return sensor_readings[0] if sensor_readings else None


def get_history(limit: int = 300) -> list[dict]:
    items = list(sensor_readings)[:limit]
    items.reverse()
    return items


def get_alerts(resolved: bool | None = None) -> list[dict]:
    if resolved is None:
        return list(reversed(sensor_alerts))
    return [a for a in reversed(sensor_alerts) if a["resolved"] == resolved]


def resolve_alert(alert_id: str) -> bool:
    for a in sensor_alerts:
        if a["id"] == alert_id:
            a["resolved"] = True
            return True
    return False


def get_irrigation_events() -> list[dict]:
    return list(reversed(irrigation_events))


def add_irrigation_event(valve_action: str, reason: str) -> dict:
    event = {
        "id": str(uuid4()),
        "triggeredAt": datetime.now(timezone.utc).isoformat(),
        "reason": reason or "수동 제어",
        "valveAction": valve_action,
        "duration": 30 if valve_action == "열림" else 0,
        "autoTriggered": False,
    }
    irrigation_events.append(event)
    return event
