from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from .settings import settings

api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)

async def get_api_key(api_key: str = Security(api_key_header)):
    if not settings.API_KEY or settings.NO_AUTH:
        # If no API_KEY is configured or auth is disabled, allow access
        return None

    if api_key == settings.API_KEY:
        return api_key
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
