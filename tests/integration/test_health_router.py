from fastapi.testclient import TestClient

def test_healthcheck_fails_initially(client: TestClient):
    """
    Tests the healthcheck endpoint. This will fail initially with a 404 Not Found error
    because the endpoint has not been implemented yet.
    """
    response = client.get("/healthcheck")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["checks"]["chroma"] is True
    assert data["checks"]["embedder"] is True
