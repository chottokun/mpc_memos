"""
API Router for RAG (Retrieval-Augmented Generation) Memo Endpoints.

This module defines the API routes for all memo-related operations,
including saving, searching, retrieving, and deleting memos. It uses the
`MemoServiceNoRaw` to handle the business logic for each endpoint.
"""
from fastapi import APIRouter, Depends, Query
from ..schemas import (
    SaveMemoRequest, SaveMemoResponse, SearchMemoResponse, GetMemoResponse,
    DeleteMemoRequest, DeleteMemoResponse, CleanupResponse
)
from ..services.memo_service import MemoServiceNoRaw
from ..settings import settings

router = APIRouter()

# Instantiate the service. For a simple service like this, a module-level
# instance is fine. For more complex scenarios with state or dependencies,
# FastAPI's dependency injection (`Depends`) would be a better choice.
memo_service = MemoServiceNoRaw()

@router.post(
    "/memo/save",
    operation_id="save_memo",
    response_model=SaveMemoResponse,
    status_code=200,
    summary="Save a new memo"
)
async def save_memo(req: SaveMemoRequest):
    """
    Saves a memo's content for semantic search.

    This endpoint takes a memo's content, generates vector embeddings from it,
    and stores them in the database along with a Time-to-Live (TTL).

    Args:
        req: A `SaveMemoRequest` object containing the memo data.

    Returns:
        A `SaveMemoResponse` object with details of the saved memo.
    """
    res = await memo_service.save_memo(
        session_id=req.session_id,
        memo=req.memo,
        keywords=req.keywords,
        importance=req.importance
    )
    return res


@router.get(
    "/memo/search",
    operation_id="query_memo",
    response_model=SearchMemoResponse,
    summary="Search for memos by query"
)
async def search_memo(
    query: str = Query(..., min_length=1, description="The search query string."),
    n_results: int = Query(
        default=settings.N_RESULTS_DEFAULT,
        ge=1,
        le=50,
        description="The number of results to return."
    )
):
    """
    Searches for semantically similar memos based on a query string.

    Args:
        query: The text query to search for.
        n_results: The maximum number of results to return.

    Returns:
        A `SearchMemoResponse` object containing the original query and a
        list of search results.
    """
    return await memo_service.search(query=query, n_results=n_results)


@router.get(
    "/memo/get",
    operation_id="get_memo",
    response_model=GetMemoResponse,
    summary="Get a memo by its ID"
)
async def get_memo(memo_id: str = Query(..., description="The ID of the memo to retrieve.")):
    """
    Retrieves the stored documents and metadata for a given memo ID.

    This endpoint fetches all the chunks and their associated metadata that
    were stored for a specific memo. It does not return the original raw text.

    Args:
        memo_id: The unique identifier of the memo to retrieve.

    Returns:
        A `GetMemoResponse` object with the memo's data.
    """
    return await memo_service.get_memo(memo_id=memo_id)


@router.post(
    "/memo/delete",
    operation_id="delete_memo",
    response_model=DeleteMemoResponse,
    summary="Delete a memo by its ID"
)
async def delete_memo(req: DeleteMemoRequest):
    """
    Deletes all documents and chunks associated with a given memo ID.

    This is an idempotent operation; it will succeed even if the memo does
    not exist.

    Args:
        req: A `DeleteMemoRequest` object containing the memo_id.

    Returns:
        A `DeleteMemoResponse` confirming the deletion.
    """
    return await memo_service.delete_memo(memo_id=req.memo_id)


@router.post(
    "/memos/cleanup",
    operation_id="cleanup_expired_memos",
    response_model=CleanupResponse,
    summary="Cleanup expired memos"
)
async def cleanup_expired_memos():
    """
    Triggers a cleanup process to delete all memos that have passed their TTL.
    This is an administrative endpoint.
    """
    deleted_count = await memo_service.cleanup_expired_memos()
    return CleanupResponse(deleted_count=deleted_count)
