import logging
from typing import Optional, List
from fastapi import FastAPI, Depends
from fastapi_mcp import FastApiMCP
from .settings import settings
from .auth_helpers import get_api_key

# Import the routers that we will populate in later steps
from .routers import rag, health

def create_app(no_auth: bool = False, additional_modules: Optional[List[str]] = None) -> FastAPI:
    """
    Application factory.
    - Initializes FastAPI app.
    - Sets up logging.
    - Configures authentication.
    - Mounts MCP.
    - Includes routers.
    """
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Determine auth dependencies based on the NO_AUTH flag in settings or the function parameter.
    # The `get_api_key` dependency will be applied to all routes.
    use_auth = not (no_auth or settings.NO_AUTH)
    auth_dependencies = [Depends(get_api_key)] if use_auth else []

    app = FastAPI(
        title="MCP Memo Service",
        description="A service to save and retrieve memos for RAG, with a focus on privacy.",
        version="0.1.0",
        dependencies=auth_dependencies,
    )

    # Mount MCP for exposing tools to agents
    # The FastApiMCP constructor requires the FastAPI app instance.
    # The mount() method is deprecated, so we use mount_http() instead.
    mcp = FastApiMCP(fastapi=app)
    mcp.mount_http(mount_path="/mcp")

    # Include core routers
    app.include_router(rag.router, prefix="/rag", tags=["RAG Memo"])
    app.include_router(health.router, tags=["Health"])
    logger.info("Included RAG and Health routers.")

    # Placeholder for dynamic module loading as specified in the design
    if additional_modules:
        logger.warning("Dynamic module loading is not yet implemented.")

    @app.get("/", tags=["Root"])
    async def read_root():
        return {"message": "Welcome to the MCP Memo Service. Visit /docs or /mcp for more info."}

    logger.info(f"FastAPI app created. Authentication is {'ENABLED' if use_auth else 'DISABLED'}.")

    return app
