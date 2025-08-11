import pytest
import asyncio
import datetime
from unittest.mock import patch, MagicMock
from app.schemas import SaveMemoRequest
from app.services.memo_service import MemoServiceNoRaw

@pytest.fixture
def memo_service_with_mocks():
    """
    Provides a MemoServiceNoRaw instance with its external dependencies mocked
    for unit testing.
    """
    with patch('app.services.memo_service.sentence_transformers') as mock_st, \
         patch('app.services.memo_service.chromadb') as mock_chromadb, \
         patch('asyncio.get_running_loop') as mock_get_loop:

        mock_embedder_instance = MagicMock()
        mock_embedder_instance.encode.return_value = MagicMock(tolist=lambda: [[0.1, 0.2, 0.3]])
        mock_st.SentenceTransformer.return_value = mock_embedder_instance

        mock_collection = MagicMock()
        mock_chroma_client = MagicMock()
        mock_chroma_client.get_or_create_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_chroma_client

        mock_loop = MagicMock()
        async def run_in_executor_mock(executor, func, *args):
            return func(*args)
        mock_loop.run_in_executor.side_effect = run_in_executor_mock
        mock_get_loop.return_value = mock_loop

        service = MemoServiceNoRaw()
        yield service, mock_collection, mock_embedder_instance

@pytest.mark.asyncio
async def test_save_memo_logic(memo_service_with_mocks):
    """
    Tests that save_memo correctly processes a request, adds TTL,
    and calls the database with the correct data.
    """
    service, mock_collection, mock_embedder = memo_service_with_mocks

    req = SaveMemoRequest(
        session_id="test-session",
        memo="This is the memo content.",
        keywords=["test"],
        importance=0.9
    )

    response = await service.save_memo(
        session_id=req.session_id,
        memo=req.memo,
        keywords=req.keywords,
        importance=req.importance
    )

    mock_embedder.encode.assert_called_once_with(["This is the memo content."])
    mock_collection.add.assert_called_once()

    args, kwargs = mock_collection.add.call_args
    assert kwargs["documents"] == ["This is the memo content."]
    metadata = kwargs["metadatas"][0]
    assert "expires_at" in metadata
    assert "saved_at" in metadata
    assert response.memo_id == metadata["memo_id"]

@pytest.mark.asyncio
async def test_search_memo_logic(memo_service_with_mocks):
    """
    Tests that the search method correctly embeds the query and calls the
    database's query method.
    """
    service, mock_collection, mock_embedder = memo_service_with_mocks

    mock_collection.query.return_value = {
        'ids': [['test-id:0']], 'distances': [[0.123]],
        'metadatas': [[{'memo_id': 'test-id'}]], 'documents': [['doc1']],
    }

    await service.search(query="test query", n_results=10)

    mock_embedder.encode.assert_called_once_with(["test query"])
    mock_collection.query.assert_called_once()
    _, kwargs = mock_collection.query.call_args
    assert kwargs["n_results"] == 10

@pytest.mark.asyncio
async def test_get_memo_logic(memo_service_with_mocks):
    """
    Tests that the get_memo method calls the database with the correct filter.
    """
    service, mock_collection, _ = memo_service_with_mocks
    await service.get_memo(memo_id="test-get-id")
    mock_collection.get.assert_called_once_with(where={"memo_id": "test-get-id"})

@pytest.mark.asyncio
async def test_delete_memo_logic(memo_service_with_mocks):
    """
    Tests that the delete_memo method calls the database's delete method.
    """
    service, mock_collection, _ = memo_service_with_mocks
    await service.delete_memo(memo_id="test-delete-id")
    mock_collection.delete.assert_called_once_with(where={"memo_id": "test-delete-id"})

@pytest.mark.asyncio
async def test_cleanup_expired_memos(memo_service_with_mocks):
    """
    Tests the logic for cleaning up expired memos.
    """
    service, mock_collection, _ = memo_service_with_mocks

    now = datetime.datetime.now(datetime.timezone.utc)
    yesterday = now - datetime.timedelta(days=1)
    tomorrow = now + datetime.timedelta(days=1)

    # Mock the return of collection.get() to simulate one expired and one valid memo
    mock_collection.get.return_value = {
        'ids': ['expired:0', 'valid:0'],
        'metadatas': [
            {'memo_id': 'expired', 'expires_at': yesterday.isoformat()},
            {'memo_id': 'valid', 'expires_at': tomorrow.isoformat()}
        ]
    }

    deleted_count = await service.cleanup_expired_memos()

    # Assert that get was called to fetch all memos
    mock_collection.get.assert_called_once()
    # Assert that delete was called only with the expired ID
    mock_collection.delete.assert_called_once_with(where={"memo_id": {"$in": ["expired"]}})
    # Assert the method returns the correct count
    assert deleted_count == 1
