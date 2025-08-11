"""
Core Service Layer for Memo Operations.

This module contains the `MemoServiceNoRaw` class, which encapsulates the
business logic for handling memos. It interacts with the embedding model
and the ChromaDB vector store to perform save, search, get, and delete
operations.

A key feature of this service is that it does not store the raw text of memos,
adhering to a privacy-first design.
"""
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
    Manages all business logic related to memos.

    This service handles the core operations of the application:
    - Loading the sentence embedding model.
    - Connecting to the ChromaDB persistent store.
    - Processing `save` requests by chunking, embedding, and storing text.
    - Handling `search` requests by embedding queries and querying the DB.
    - Retrieving and deleting memos by their ID.
    """
    def __init__(self):
        """
        Initializes the service.

        This constructor loads the sentence-transformer model and establishes a
        connection to the ChromaDB persistent client. It also sets up a
        ThreadPoolExecutor to handle blocking operations asynchronously.

        Raises:
            Exception: Propagates exceptions that occur during model loading or
                       database connection to prevent the app from starting in
                       a faulty state.
        """
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
            # In a real production app, you'd use a more robust logger.
            raise

    async def save_memo(
        self,
        session_id: str,
        memo: str,
        keywords: Optional[List[str]] = None,
        importance: float = 0.0
    ) -> SaveMemoResponse:
        """
        Saves a memo by embedding its content and storing it in ChromaDB.

        This version only accepts a 'memo' field, which is directly used for
        chunking and embedding. It also calculates and stores a TTL.

        Args:
            session_id: An identifier for the user session.
            memo: The text content of the memo to be saved and embedded.
            keywords: Optional list of keywords associated with the memo.
            importance: An optional float representing the memo's importance.

        Returns:
            A `SaveMemoResponse` object confirming the save operation.
        """
        loop = asyncio.get_running_loop()

        memo_id = str(uuid.uuid4())
        now = datetime.datetime.now(datetime.timezone.utc)
        expires_at = now + datetime.timedelta(days=settings.MEMO_TTL_DAYS)

        # The memo is the direct source for embedding
        embed_source = memo

        # Step 1: Chunk the source text
        chunks = chunk_text(embed_source, settings.MAX_CHUNK_CHARS)
        if not chunks:
            return SaveMemoResponse(
                memo_id=memo_id,
                saved_at=now,
                chroma_ids=[]
            )

        # Step 2: Embed the chunks in a thread pool
        embeddings_np = await loop.run_in_executor(
            self.executor, self.embedder.encode, chunks
        )
        embeddings = embeddings_np.tolist()

        # Step 3: Prepare data for ChromaDB
        chroma_ids = [f"{memo_id}:{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "memo_id": memo_id,
                "session_id": session_id,
                "chunk_index": i,
                "keywords": json.dumps(keywords or []),
                "importance": importance,
                "saved_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
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
            saved_at=now,
            chroma_ids=chroma_ids,
        )

    async def search(self, query: str, n_results: int = 5) -> SearchMemoResponse:
        """
        Searches for memos in ChromaDB based on a query string.

        Args:
            query: The text query to search for.
            n_results: The maximum number of results to return.

        Returns:
            A `SearchMemoResponse` object containing the query and a list of results.
        """
        loop = asyncio.get_running_loop()

        query_embedding_np = await loop.run_in_executor(
            self.executor, self.embedder.encode, [query]
        )
        query_embedding = query_embedding_np.tolist()

        query_results = await loop.run_in_executor(
            self.executor,
            lambda: self.collection.query(
                query_embeddings=query_embedding,
                n_results=n_results,
                include=["documents", "metadatas", "distances"]
            )
        )

        results = []
        if query_results and query_results['ids'][0]:
            for i, doc_id in enumerate(query_results['ids'][0]):
                results.append(SearchResultItem(
                    memo=query_results['documents'][0][i],
                    metadata=query_results['metadatas'][0][i],
                    distance=query_results['distances'][0][i]
                ))

        return SearchMemoResponse(query=query, results=results)

    async def get_memo(self, memo_id: str) -> GetMemoResponse:
        """
        Retrieves a memo's documents and metadata from ChromaDB by its ID.

        Args:
            memo_id: The unique identifier of the memo to retrieve.

        Returns:
            A `GetMemoResponse` object containing the memo's stored data.
        """
        loop = asyncio.get_running_loop()

        retrieved_data = await loop.run_in_executor(
            self.executor,
            lambda: self.collection.get(where={"memo_id": memo_id})
        )

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

        It uses a `where` filter to delete all documents whose metadata
        contains the specified `memo_id`.

        Args:
            memo_id: The unique identifier of the memo to delete.

        Returns:
            A `DeleteMemoResponse` object confirming the deletion.
        """
        loop = asyncio.get_running_loop()

        await loop.run_in_executor(
            self.executor,
            lambda: self.collection.delete(where={"memo_id": memo_id})
        )

        return DeleteMemoResponse(deleted=True, memo_id=memo_id)

    async def cleanup_expired_memos(self) -> int:
        """
        Deletes all memos that have passed their TTL.

        This method queries the database for memos where the `expires_at`
        timestamp is in the past, and then deletes them.

        Returns:
            The number of memos (i.e., groups of chunks) that were deleted.
        """
        loop = asyncio.get_running_loop()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # ChromaDB doesn't have a direct "less than" for ISO strings, so we query
        # all and filter in Python. This is not efficient for large datasets.
        # A better approach in a real production system might be to store
        # timestamps as Unix timestamps (integers or floats) for direct querying.
        # For this implementation, we'll proceed with the less efficient filter.

        all_memos = await loop.run_in_executor(
            self.executor,
            self.collection.get
        )

        expired_memo_ids = set()
        if all_memos:
            for i, metadata in enumerate(all_memos.get('metadatas', [])):
                if metadata and 'expires_at' in metadata:
                    if metadata['expires_at'] < now_iso:
                        expired_memo_ids.add(metadata['memo_id'])

        if not expired_memo_ids:
            return 0

        # Delete the expired memos by their IDs
        await loop.run_in_executor(
            self.executor,
            lambda: self.collection.delete(where={"memo_id": {"$in": list(expired_memo_ids)}})
        )

        return len(expired_memo_ids)
