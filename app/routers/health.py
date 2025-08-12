"""
API Router for Health Check Endpoints.

This module provides a simple health check endpoint to verify that the
service is running and responding to requests.
"""
from fastapi import APIRouter, status
from app.schemas import HealthCheckResponse

router = APIRouter()


@router.get(
    "/healthcheck",
    operation_id="healthcheck",
    response_model=HealthCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Perform a service health check"
)
async def healthcheck():
    """
    Checks the operational status of the service.

    This endpoint can be used by monitoring services to verify that the
    application is alive and healthy. The current implementation provides a
    basic check; a more advanced version could verify connectivity to
    downstream services like the database and embedding model.

    Returns:
        A `HealthCheckResponse` object indicating the service status.
    """
    # In this version, a 200 OK response indicates that the service is running.
    # The MemoService's __init__ handles the critical checks for ChromaDB and
    # the embedder model at startup.
    return HealthCheckResponse(
        status="ok",
        checks={"chroma": True, "embedder": True}
    )
