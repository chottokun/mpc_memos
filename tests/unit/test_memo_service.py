import pytest
import asyncio
from unittest.mock import patch, MagicMock
from app.schemas import SaveMemoRequest
from app.services.memo_service import MemoServiceNoRaw

@pytest.fixture
def memo_service_with_mocks():
    """
    Provides a MemoServiceNoRaw instance with its external dependencies mocked
    for unit testing. This version correctly mocks the asyncio event loop.
    """
    with patch('app.services.memo_service.sentence_transformers') as mock_st, \
         patch('app.services.memo_service.chromadb') as mock_chromadb, \
         patch('asyncio.get_running_loop') as mock_get_loop:

        # --- Mock external libraries ---
        mock_embedder_instance = MagicMock()
        mock_embedder_instance.encode.return_value = MagicMock(tolist=lambda: [[0.1, 0.2, 0.3]])
        mock_st.SentenceTransformer.return_value = mock_embedder_instance

        mock_collection = MagicMock()
        mock_chroma_client = MagicMock()
        mock_chroma_client.get_or_create_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_chroma_client

        # --- Mock asyncio behavior ---
        # Mock the event loop and its run_in_executor method to execute synchronously
        # for the test.
        mock_loop = MagicMock()
        async def run_in_executor_mock(executor, func, *args):
            return func(*args)
        mock_loop.run_in_executor.side_effect = run_in_executor_mock
        mock_get_loop.return_value = mock_loop

        # --- Instantiate the service ---
        # The __init__ will now use the mocked libraries and loop
        service = MemoServiceNoRaw()

        yield service, mock_collection, mock_embedder_instance

@pytest.mark.asyncio
async def test_save_memo_with_summary(memo_service_with_mocks):
    """
    Tests that save_memo correctly processes a request with a summary.
    It should embed the summary, not the raw text.
    """
    service, mock_collection, mock_embedder = memo_service_with_mocks

    req = SaveMemoRequest(
        session_id="test-session-summary",
        text="This is raw text, it should not be embedded.",
        summary="This is the summary, it should be embedded.",
        keywords=["test", "summary"],
        importance=0.9
    )

    # Call the method under test
    response = await service.save_memo(
        session_id=req.session_id,
        text=req.text,
        summary=req.summary,
        keywords=req.keywords,
        importance=req.importance
    )

    # 1. Assert that the embedder was called with the summary
    mock_embedder.encode.assert_called_once_with(["This is the summary, it should be embedded."])

    # 2. Assert that the collection's add method was called
    mock_collection.add.assert_called_once()

    # 3. Verify the contents of the 'add' call
    args, kwargs = mock_collection.add.call_args
    assert "documents" in kwargs
    assert kwargs["documents"] == ["This is the summary, it should be embedded."]
    assert "metadatas" in kwargs
    metadata = kwargs["metadatas"][0]
    assert metadata["is_summary"] is True
    assert metadata["session_id"] == "test-session-summary"
    assert "text_hash" in metadata
    # Check that keywords were correctly serialized
    import json
    assert metadata["keywords"] == json.dumps(["test", "summary"])

    # 4. Check the response object
    assert response.used_summary is True
    assert response.memo_id is not None
    assert len(response.chroma_ids) == 1


@pytest.mark.asyncio
async def test_search_memo_logic(memo_service_with_mocks):
    """
    Tests that the search method correctly embeds the query and calls the
    database's query method with the correct parameters.
    This test will fail until the real implementation is in place.
    """
    service, mock_collection, mock_embedder = memo_service_with_mocks

    # Mock the return value of the collection's query method to simulate a find
    mock_collection.query.return_value = {
        'ids': [['test-id:0']],
        'distances': [[0.123]],
        'metadatas': [[{'memo_id': 'test-id', 'chunk_index': 0, 'is_summary': True}]],
        'documents': [['This is a test document.']],
        'embeddings': None,
        'uris': None,
        'data': None,
    }

    query_text = "test query"
    n_results = 10

    # This call will fail the assertions below because the skeleton implementation
    # does not call the mocks.
    await service.search(query=query_text, n_results=n_results)

    # Assert that the embedder was called with the query
    mock_embedder.encode.assert_called_once_with([query_text])

    # Assert that the collection's query method was called correctly
    mock_collection.query.assert_called_once()
    args, kwargs = mock_collection.query.call_args
    assert "query_embeddings" in kwargs
    assert len(kwargs["query_embeddings"]) == 1
    assert "n_results" in kwargs
    assert kwargs["n_results"] == n_results


@pytest.mark.asyncio
async def test_get_memo_logic(memo_service_with_mocks):
    """
    Tests that the get_memo method calls the database with the correct filter.
    This test will fail until the real implementation is in place.
    """
    service, mock_collection, _ = memo_service_with_mocks
    memo_id = "test-get-id-123"

    # Mock the return value of the collection's get method
    mock_collection.get.return_value = {
        'ids': [f'{memo_id}:0'],
        'metadatas': [{'memo_id': memo_id, 'chunk_index': 0}],
        'documents': ['Test document content.'],
        'embeddings': None,
        'uris': None,
        'data': None,
    }

    # This call will fail the assertion below
    await service.get_memo(memo_id=memo_id)

    # Assert that the collection's get method was called with the correct filter
    mock_collection.get.assert_called_once_with(where={"memo_id": memo_id})


@pytest.mark.asyncio
async def test_delete_memo_logic(memo_service_with_mocks):
    """
    Tests that the delete_memo method calls the database's delete method
    with the correct filter. This test will fail until the real logic is implemented.
    """
    service, mock_collection, _ = memo_service_with_mocks
    memo_id = "test-delete-id-456"

    # This call will fail the assertion below
    await service.delete_memo(memo_id=memo_id)

    # Assert that the collection's delete method was called with the correct filter
    mock_collection.delete.assert_called_once_with(where={"memo_id": memo_id})
