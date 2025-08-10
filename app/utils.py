"""
Utility Functions.

This module provides helper functions that are used across the application,
such as text processing and hashing utilities.
"""
import hashlib

def chunk_text(text: str, max_chunk_chars: int) -> list[str]:
    """
    Splits a long text into smaller chunks based on character length.

    This is a simple chunking strategy. For more advanced use cases,
    this could be replaced with sentence-aware or paragraph-aware chunking.

    Args:
        text: The input text to be chunked.
        max_chunk_chars: The maximum number of characters for each chunk.

    Returns:
        A list of text chunks, or an empty list if the input text is empty.
    """
    if not text:
        return []
    if len(text) <= max_chunk_chars:
        return [text]

    # Simple iterative chunking
    chunks = []
    for i in range(0, len(text), max_chunk_chars):
        chunks.append(text[i:i + max_chunk_chars])
    return chunks

def get_text_hash(text: str) -> str:
    """
    Generates a SHA256 hash for a given string.

    This is used to create a unique, non-reversible identifier for the original
    raw text without storing the text itself, enhancing privacy.

    Args:
        text: The input string to hash.

    Returns:
        A string representing the SHA256 hash, prefixed with "sha256-".
    """
    return f"sha256-{hashlib.sha256(text.encode('utf-8')).hexdigest()}"
