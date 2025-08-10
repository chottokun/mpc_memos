import pytest
from fastapi.testclient import TestClient
from app.factory import create_app

@pytest.fixture(scope="module")
def client():
    """
    Create a TestClient instance for the FastAPI app.
    The `no_auth=True` flag disables authentication for testing purposes.
    The scope is 'module' so the app is created only once per test module.
    """
    # Override settings for testing if necessary
    # For now, we just disable auth
    app = create_app(no_auth=True)
    with TestClient(app) as c:
        yield c
