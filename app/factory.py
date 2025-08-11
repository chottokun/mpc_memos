"""
Application Factory.

This module contains the `create_app` factory function, which is the primary
entry point for constructing and configuring the FastAPI application instance.
Using a factory makes the application's setup modular and easy to test.
"""
import logging
from typing import Optional, List
from fastapi import FastAPI, Depends

from .settings import settings
from .auth_helpers import get_api_key
from .routers import rag, health
from fastapi_mcp import FastApiMCP

def create_app(no_auth: bool = False, additional_modules: Optional[List[str]] = None) -> FastAPI:
    """
    Constructs and configures a new FastAPI application instance.

    This factory handles:
    - Initializing the FastAPI app with metadata.
    - Setting up logging.
    - Configuring API key authentication based on settings.
    - Mounting the `fastapi_mcp` tool server.
    - Including all necessary API routers (e.g., for RAG and health checks).

    Args:
        no_auth: If True, disables authentication for the created app instance,
                 which is useful for testing. Defaults to False.
        additional_modules: A placeholder for dynamically loading other
                            router modules in the future. Not currently used.

    Returns:
        A fully configured FastAPI application instance.
    """
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Determine auth dependencies based on the NO_AUTH flag in settings or the function parameter.
    use_auth = not (no_auth or settings.NO_AUTH)
    auth_dependencies = [Depends(get_api_key)] if use_auth else []

    app = FastAPI(
        title="MCP Memo Service",
        description="A service to save and retrieve memos for RAG, with a focus on privacy.",
        version="0.1.0",
        dependencies=auth_dependencies,
    )

    # Mount MCP for exposing tools to agents
    mcp = FastApiMCP(fastapi=app)
    mcp.mount()

    # Include core routers
    app.include_router(rag.router, prefix="/rag", tags=["RAG Memo"])
    app.include_router(health.router, tags=["Health"])
    logger.info("Included RAG and Health routers.")

    # Placeholder for dynamic module loading as specified in the design
    if additional_modules:
        logger.warning("Dynamic module loading is not yet implemented.")

    @app.get("/", tags=["Root"])
    async def read_root():
        """A simple root endpoint to confirm the service is running."""
        return {"message": "Welcome to the MCP Memo Service. Visit /docs or /mcp for more info."}

    logger.info(f"FastAPI app created. Authentication is {'ENABLED' if use_auth else 'DISABLED'}.")

    return app
