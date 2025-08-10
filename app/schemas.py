"""
Pydantic Models for API Data Validation.

This module defines the data structures used for validating API requests and
serializing API responses. These Pydantic models ensure that data conforms to
the expected schema and provide clear, automatic documentation for the API.
"""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import datetime

# === Request Models ===

class SaveMemoRequest(BaseModel):
    """Request model for the `save_memo` endpoint."""
    session_id: str
    text: str
    summary: Optional[str] = None
    keywords: Optional[List[str]] = None
    importance: float = 0.0

class DeleteMemoRequest(BaseModel):
    """Request model for the `delete_memo` endpoint."""
    memo_id: str

# === Response Models ===

class SaveMemoResponse(BaseModel):
    """Response model for a successful `save_memo` operation."""
    memo_id: str
    saved_at: datetime.datetime
    chroma_ids: List[str]
    used_summary: bool

class SearchResultItem(BaseModel):
    """Represents a single search result item."""
    summary: str  # The document content (summary or chunk)
    metadata: Dict[str, Any]
    distance: float

class SearchMemoResponse(BaseModel):
    """Response model for a `query_memo` operation."""
    query: str
    results: List[SearchResultItem]

class GetMemoResponse(BaseModel):
    """Response model for a `get_memo` operation."""
    memo_id: str
    metadata: List[Dict[str, Any]]
    documents: List[str]

class DeleteMemoResponse(BaseModel):
    """Response model for a successful `delete_memo` operation."""
    deleted: bool
    memo_id: str

class HealthCheckResponse(BaseModel):
    """Response model for the `healthcheck` endpoint."""
    status: str
    checks: Dict[str, bool]
