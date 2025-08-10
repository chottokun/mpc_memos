from fastapi import APIRouter, status
from app.schemas import HealthCheckResponse

router = APIRouter()


@router.get(
    "/healthcheck",
    operation_id="healthcheck",
    response_model=HealthCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Perform a health check"
)
async def healthcheck():
    """
    Checks the status of the service and its dependencies.
    In this skeleton version, it always returns a healthy status.
    """
    return HealthCheckResponse(
        status="ok",
        checks={"chroma": True, "embedder": True}
    )
