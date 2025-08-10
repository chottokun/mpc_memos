"""
Application Entry Point.

This is the main entry point for the Uvicorn server. It uses the `create_app`
factory to build the FastAPI application instance.
"""
from .factory import create_app
from .settings import settings

# Create the FastAPI app instance by calling the factory.
# Authentication is controlled by the NO_AUTH environment variable.
app = create_app(no_auth=settings.NO_AUTH)
