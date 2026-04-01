from fastapi import APIRouter, Depends, Query

from app.core.deps import get_current_user, verify_iot_api_key
from app.core.store import (
    add_reading,
    get_alerts,
    get_history,
    get_latest,
    resolve_alert,
)
from app.schemas.sensor import SensorDataIn

router = APIRouter(prefix="/sensors", tags=["sensors"])


@router.post("", status_code=201, dependencies=[Depends(verify_iot_api_key)])
async def receive_sensor_data(data: SensorDataIn) -> dict:
    """ESP8266에서 센서 데이터를 수신한다 (API Key 인증)."""
    new_alerts = add_reading(
        device_id=data.device_id,
        sensors=data.sensors.model_dump(),
        timestamp=data.timestamp,
    )
    return {"status": "ok", "alerts_generated": len(new_alerts)}


@router.get("/latest", dependencies=[Depends(get_current_user)])
async def get_latest_reading() -> dict:
    """최신 센서 값 1건을 반환한다 (로그인 필요)."""
    reading = get_latest()
    if reading is None:
        return {"timestamp": None, "soilMoisture": 0, "temperature": 0, "humidity": 0, "lightIntensity": 0}
    return reading


@router.get("/history", dependencies=[Depends(get_current_user)])
async def get_sensor_history(limit: int = Query(default=300, ge=1, le=2000)) -> list[dict]:
    """시계열 센서 데이터를 반환한다 (로그인 필요)."""
    return get_history(limit)


@router.get("/alerts", dependencies=[Depends(get_current_user)])
async def get_sensor_alerts(resolved: bool | None = None) -> list[dict]:
    """센서 알림 목록을 반환한다 (로그인 필요)."""
    return get_alerts(resolved)


@router.patch("/alerts/{alert_id}/resolve", dependencies=[Depends(get_current_user)])
async def resolve_sensor_alert(alert_id: str) -> dict:
    """알림을 해결 처리한다 (로그인 필요)."""
    if resolve_alert(alert_id):
        return {"status": "resolved"}
    return {"error": "alert not found"}
