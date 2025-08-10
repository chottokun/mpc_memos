from fastapi import APIRouter, Depends, Query
from ..schemas import (
    SaveMemoRequest, SaveMemoResponse, SearchMemoResponse, GetMemoResponse,
    DeleteMemoRequest, DeleteMemoResponse
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
    Saves a memo.

    - The raw `text` is used for embedding if no `summary` is provided, but it is **not** stored on the server.
    - If a `summary` is provided, it will be used as the source for embedding.
    - Returns a confirmation with the generated memo ID.
    """
    res = await memo_service.save_memo(
        session_id=req.session_id,
        text=req.text,
        summary=req.summary,
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
    Searches for memos based on a query string, returning the most relevant results.
    """
    return await memo_service.search(query=query, n_results=n_results)


# Other endpoints (get, delete) will be added in subsequent steps.


@router.get(
    "/memo/get",
    operation_id="get_memo",
    response_model=GetMemoResponse,
    summary="Get a memo by its ID"
)
async def get_memo(memo_id: str = Query(..., description="The ID of the memo to retrieve.")):
    """
    Retrieves the stored documents and metadata for a given memo_id.
    This does not return the original raw text.
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
    Deletes all documents and chunks associated with a given memo_id from the database.
    """
    return await memo_service.delete_memo(memo_id=req.memo_id)
