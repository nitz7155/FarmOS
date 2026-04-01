"""공통 의존성 — 쿠키 기반 JWT 토큰 검증 및 IoT API Key 검증."""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.core import user_store
from app.models.user import User

COOKIE_KEY = "farmos_token"

# IoT 디바이스용 API Key 헤더
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """쿠키에서 JWT 토큰을 추출하고 검증한다."""
    token = request.cookies.get(COOKIE_KEY)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증이 필요합니다.",
        )
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰이 유효하지 않거나 만료되었습니다.",
        )
    user_id: str = payload.get("sub", "")
    user = await user_store.find_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다.",
        )
    return user


async def verify_iot_api_key(api_key: str | None = Depends(_api_key_header)) -> str:
    """ESP8266 디바이스의 X-API-Key 헤더를 검증한다."""
    if not api_key or api_key != settings.IOT_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="유효하지 않은 API Key입니다.",
        )
    return api_key
