import hashlib

def chunk_text(text: str, max_chunk_chars: int) -> list[str]:
    """
    Splits a long text into smaller chunks, each with a maximum size.
    This is a simple implementation that splits by character count.
    More advanced versions could split by sentences or paragraphs.

    Args:
        text: The input text to be chunked.
        max_chunk_chars: The maximum number of characters for each chunk.

    Returns:
        A list of text chunks.
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
    Generates a SHA256 hash for the given text to serve as a unique identifier
    without storing the text itself.

    Args:
        text: The input text.

    Returns:
        A string representing the SHA256 hash, prefixed with "sha256-".
    """
    return f"sha256-{hashlib.sha256(text.encode('utf-8')).hexdigest()}"
