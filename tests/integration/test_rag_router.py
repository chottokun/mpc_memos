from fastapi.testclient import TestClient

def test_save_memo_returns_valid_response(client: TestClient):
    """
    Tests that the save_memo endpoint returns a successful response with the expected structure.
    """
    response = client.post(
        "/rag/memo/save",
        json={
            "session_id": "test-session-123",
            "text": "This is a test memo for the save endpoint.",
            "summary": "Test memo summary.",
            "keywords": ["test", "tdd"],
            "importance": 0.8
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "memo_id" in data
    assert "saved_at" in data
    assert "chroma_ids" in data

def test_search_memo_fails_initially(client: TestClient):
    """
    Tests the search_memo endpoint. This will fail initially with a 404 Not Found error
    because the endpoint has not been implemented yet.
    """
    response = client.get("/rag/memo/search?query=nonexistent")
    assert response.status_code == 200
    assert "results" in response.json()


def test_get_memo_fails_initially(client: TestClient):
    """
    Tests the get_memo endpoint. This will fail initially with a 404 Not Found error.
    It first creates a memo to ensure a valid memo_id exists.
    """
    # ARRANGE: Create a memo to get a valid ID
    save_response = client.post(
        "/rag/memo/save",
        json={"session_id": "test-for-get", "text": "This is the text for the get test."}
    )
    assert save_response.status_code == 200
    memo_id = save_response.json()["memo_id"]
    assert memo_id is not None

    # ACT: Attempt to retrieve the memo
    get_response = client.get(f"/rag/memo/get?memo_id={memo_id}")

    # ASSERT: This will fail until the endpoint is implemented
    assert get_response.status_code == 200
    assert get_response.json()["memo_id"] == memo_id


def test_delete_memo_fails_initially(client: TestClient):
    """
    Tests the delete_memo endpoint. This will fail initially with a 404 Not Found error.
    """
    # ARRANGE: Create a memo to have something to delete
    save_response = client.post(
        "/rag/memo/save",
        json={"session_id": "test-for-delete", "text": "This memo will be deleted."}
    )
    assert save_response.status_code == 200
    memo_id = save_response.json()["memo_id"]
    assert memo_id is not None

    # ACT: Call the delete endpoint, which doesn't exist yet
    delete_response = client.post("/rag/memo/delete", json={"memo_id": memo_id})

    # ASSERT: This will fail
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True
