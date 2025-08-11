import datetime
from unittest.mock import patch
from fastapi.testclient import TestClient

def test_save_memo_returns_valid_response(client: TestClient):
    """
    Tests that the refactored save_memo endpoint (using 'memo' field)
    returns a successful response.
    """
    response = client.post(
        "/rag/memo/save",
        json={
            "session_id": "test-session-123",
            "memo": "This is the new memo content.",
            "keywords": ["test", "refactor"],
            "importance": 0.8
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "memo_id" in data
    assert "saved_at" in data
    assert "chroma_ids" in data

def test_search_and_get_flow(client: TestClient):
    """
    Tests a full user flow: save a memo, search for it, and get it by ID.
    """
    # 1. SAVE the memo
    memo_content = "Integration test about a specific blue elephant."
    save_response = client.post(
        "/rag/memo/save",
        json={"session_id": "test-flow", "memo": memo_content}
    )
    assert save_response.status_code == 200
    memo_id = save_response.json()["memo_id"]

    # 2. SEARCH for the memo
    search_response = client.get("/rag/memo/search?query=blue%20elephant")
    assert search_response.status_code == 200
    search_data = search_response.json()
    assert len(search_data["results"]) > 0
    assert search_data["results"][0]["memo"] == memo_content

    # 3. GET the memo by ID
    get_response = client.get(f"/rag/memo/get?memo_id={memo_id}")
    assert get_response.status_code == 200
    get_data = get_response.json()
    assert get_data["memo_id"] == memo_id
    assert get_data["documents"][0] == memo_content

def test_delete_flow(client: TestClient):
    """
    Tests that a memo can be saved and then successfully deleted.
    """
    # 1. SAVE the memo
    memo_content = "This memo is destined for deletion."
    save_response = client.post(
        "/rag/memo/save",
        json={"session_id": "delete-flow", "memo": memo_content}
    )
    assert save_response.status_code == 200
    memo_id = save_response.json()["memo_id"]

    # 2. DELETE the memo
    delete_response = client.post("/rag/memo/delete", json={"memo_id": memo_id})
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True

    # 3. VERIFY it's gone
    get_response = client.get(f"/rag/memo/get?memo_id={memo_id}")
    assert get_response.status_code == 200
    assert len(get_response.json()["documents"]) == 0

def test_cleanup_expired_memos_endpoint(client: TestClient):
    """
    Tests the cleanup endpoint by mocking the TTL setting to make a memo expire instantly.
    """
    # 1. SAVE a memo with a TTL of 0 days, making it instantly "expired"
    with patch("app.services.memo_service.settings.MEMO_TTL_DAYS", -1):
        save_response = client.post(
            "/rag/memo/save",
            json={"session_id": "ttl-test", "memo": "This memo should expire."}
        )
        assert save_response.status_code == 200
        expired_memo_id = save_response.json()["memo_id"]

    # 2. SAVE another memo with a normal TTL
    save_response_valid = client.post(
        "/rag/memo/save",
        json={"session_id": "ttl-test", "memo": "This memo should NOT expire."}
    )
    assert save_response_valid.status_code == 200
    valid_memo_id = save_response_valid.json()["memo_id"]

    # 3. TRIGGER the cleanup process
    cleanup_response = client.post("/rag/memos/cleanup")
    assert cleanup_response.status_code == 200
    assert cleanup_response.json()["deleted_count"] == 1

    # 4. VERIFY the expired memo is gone
    get_expired_response = client.get(f"/rag/memo/get?memo_id={expired_memo_id}")
    assert get_expired_response.status_code == 200
    assert len(get_expired_response.json()["documents"]) == 0

    # 5. VERIFY the valid memo still exists
    get_valid_response = client.get(f"/rag/memo/get?memo_id={valid_memo_id}")
    assert get_valid_response.status_code == 200
    assert len(get_valid_response.json()["documents"]) == 1
