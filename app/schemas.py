from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import datetime

# === Request Models ===

class SaveMemoRequest(BaseModel):
    session_id: str
    text: str
    summary: Optional[str] = None
    keywords: Optional[List[str]] = None
    importance: float = 0.0

class DeleteMemoRequest(BaseModel):
    memo_id: str

# === Response Models ===

class SaveMemoResponse(BaseModel):
    memo_id: str
    saved_at: datetime.datetime
    chroma_ids: List[str]
    used_summary: bool

class SearchResultItem(BaseModel):
    summary: str # The document content (summary or chunk)
    metadata: Dict[str, Any]
    distance: float

class SearchMemoResponse(BaseModel):
    query: str
    results: List[SearchResultItem]

class GetMemoResponse(BaseModel):
    memo_id: str
    metadata: List[Dict[str, Any]]
    documents: List[str]

class DeleteMemoResponse(BaseModel):
    deleted: bool
    memo_id: str

class HealthCheckResponse(BaseModel):
    status: str
    checks: Dict[str, bool]
