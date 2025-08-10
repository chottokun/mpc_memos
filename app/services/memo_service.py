import datetime
import uuid
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List

# Third-party libraries
import chromadb
import sentence_transformers
import numpy as np

# Internal modules
from app.schemas import (
    SaveMemoResponse, SearchMemoResponse, SearchResultItem, GetMemoResponse,
    DeleteMemoResponse
)
from app.settings import settings
from app.utils import chunk_text, get_text_hash


class MemoServiceNoRaw:
    """
    Service for handling memo operations without storing raw text.
    This implementation connects to a real ChromaDB and SentenceTransformer.
    """
    def __init__(self):
        """Initializes the service, loading the embedding model and setting up the ChromaDB client."""
        try:
            self.embedder = sentence_transformers.SentenceTransformer(
                settings.EMBED_MODEL, device=settings.DEVICE
            )
            self.chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PATH)
            self.collection = self.chroma_client.get_or_create_collection(
                name="memos", metadata={"hnsw:space": "cosine"}
            )
            # A thread pool is used to run blocking I/O (like model inference and DB writes)
            # in a separate thread without blocking the main FastAPI event loop.
            self.executor = ThreadPoolExecutor(max_workers=settings.EMBED_THREAD_WORKERS)
            print("MemoServiceNoRaw initialized with real dependencies.")
        except Exception as e:
            print(f"Error during MemoServiceNoRaw initialization: {e}")
            # In a real production app, you'd use a more robust logger and possibly
            # raise the exception to prevent the app from starting in a bad state.
            raise

    async def save_memo(
        self,
        session_id: str,
        text: str,
        summary: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        importance: float = 0.0
    ) -> SaveMemoResponse:
        """
        Saves a memo by embedding its content (summary or raw text) and storing it in ChromaDB.
        """
        loop = asyncio.get_running_loop()

        memo_id = str(uuid.uuid4())
        saved_at = datetime.datetime.now(datetime.timezone.utc)

        embed_source = summary if summary else text
        used_summary = bool(summary)

        # Step 1: Chunk the source text
        chunks = chunk_text(embed_source, settings.MAX_CHUNK_CHARS)
        if not chunks:
            # Handle case where there's nothing to embed
            return SaveMemoResponse(
                memo_id=memo_id,
                saved_at=saved_at,
                chroma_ids=[],
                used_summary=used_summary
            )

        # Step 2: Embed the chunks in a thread pool
        embeddings_np = await loop.run_in_executor(
            self.executor, self.embedder.encode, chunks
        )
        embeddings = embeddings_np.tolist() # ChromaDB client expects lists, not numpy arrays

        # Step 3: Prepare data for ChromaDB
        chroma_ids = [f"{memo_id}:{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "memo_id": memo_id,
                "session_id": session_id,
                "chunk_index": i,
                "is_summary": used_summary,
                # ChromaDB metadata values must be str, int, float, or bool.
                # We serialize the list of keywords into a JSON string.
                "keywords": json.dumps(keywords or []),
                "importance": importance,
                "saved_at": saved_at.isoformat(),
                "text_hash": get_text_hash(text)
            }
            for i in range(len(chunks))
        ]

        # Step 4: Add to ChromaDB in a thread pool
        await loop.run_in_executor(
            self.executor,
            lambda: self.collection.add(
                ids=chroma_ids,
                embeddings=embeddings,
                documents=chunks,
                metadatas=metadatas
            )
        )

        return SaveMemoResponse(
            memo_id=memo_id,
            saved_at=saved_at,
            chroma_ids=chroma_ids,
            used_summary=used_summary
        )

    async def search(self, query: str, n_results: int = 5) -> SearchMemoResponse:
        """
        Searches for memos in ChromaDB based on a query string.
        """
        loop = asyncio.get_running_loop()

        # Embed the query string in a thread pool
        query_embedding_np = await loop.run_in_executor(
            self.executor, self.embedder.encode, [query]
        )
        query_embedding = query_embedding_np.tolist()

        # Query ChromaDB in a thread pool
        query_results = await loop.run_in_executor(
            self.executor,
            lambda: self.collection.query(
                query_embeddings=query_embedding,
                n_results=n_results,
                include=["documents", "metadatas", "distances"]
            )
        )

        # Format the results into the response model
        results = []
        if query_results and query_results['ids'][0]:
            for i, doc_id in enumerate(query_results['ids'][0]):
                results.append(SearchResultItem(
                    summary=query_results['documents'][0][i],
                    metadata=query_results['metadatas'][0][i],
                    distance=query_results['distances'][0][i]
                ))

        return SearchMemoResponse(query=query, results=results)

    async def get_memo(self, memo_id: str) -> GetMemoResponse:
        """
        Retrieves a memo's documents and metadata from ChromaDB by its ID.
        """
        loop = asyncio.get_running_loop()

        # Query ChromaDB for the memo by its ID in the metadata
        retrieved_data = await loop.run_in_executor(
            self.executor,
            lambda: self.collection.get(where={"memo_id": memo_id})
        )

        # Note: The 'get' method in chromadb returns a dict-like object, not a list.
        # We need to handle the case where no documents are found.
        documents = retrieved_data.get('documents') if retrieved_data else []
        metadatas = retrieved_data.get('metadatas') if retrieved_data else []

        return GetMemoResponse(
            memo_id=memo_id,
            metadata=metadatas or [],
            documents=documents or []
        )

    async def delete_memo(self, memo_id: str) -> DeleteMemoResponse:
        """
        Deletes a memo and all its associated chunks from ChromaDB.
        """
        loop = asyncio.get_running_loop()

        # Delete from ChromaDB by metadata filter in a thread pool
        await loop.run_in_executor(
            self.executor,
            lambda: self.collection.delete(where={"memo_id": memo_id})
        )

        return DeleteMemoResponse(deleted=True, memo_id=memo_id)
