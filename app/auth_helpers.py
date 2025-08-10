"""
API Authentication Helpers.

This module provides dependency functions for FastAPI to handle API key
authentication. It checks for an API key in the `X-API-KEY` header and
validates it against the key defined in the application settings.
"""
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from .settings import settings

# Define the API key header that clients are expected to use.
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)

async def get_api_key(api_key: str = Security(api_key_header)):
    """
    FastAPI dependency to validate the API key.

    This function is used in the `dependencies` list of the FastAPI app instance.
    It checks the incoming request for an `X-API-KEY` header and compares its
    value to the `API_KEY` in the settings.

    If authentication is disabled via `NO_AUTH` or no `API_KEY` is configured,
    it allows the request to proceed. Otherwise, it enforces a valid API key.

    Args:
        api_key: The API key extracted from the `X-API-KEY` header.

    Raises:
        HTTPException: A 403 Forbidden error if the API key is invalid.

    Returns:
        The validated API key if successful, or None if auth is disabled.
    """
    if settings.NO_AUTH or not settings.API_KEY:
        # If auth is disabled or no API key is set in the environment,
        # don't perform the check.
        return None

    if api_key == settings.API_KEY:
        return api_key
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
