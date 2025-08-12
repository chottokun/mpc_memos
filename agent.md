# Agent.md — Ephemeral Memo MCP Service

---

# Project Overview

This is a FastAPI service for managing **ephemeral memos** with a Time-to-Live (TTL). It uses `fastapi_mcp` to expose tools for saving and searching short-term notes. The core concept is privacy-first and simplicity: the server only accepts `memo` content, generates vector embeddings, and stores them in ChromaDB until they expire.

---

# Core Concepts

- **Memo-Only**: The API only accepts a `memo` field. It does not handle raw text or summaries separately.
- **Time-to-Live (TTL)**: All memos are saved with an expiration date (default: 30 days). Expired memos can be cleaned up.
- **Privacy**: The service is designed to handle only the direct memo content, minimizing data exposure.

---

# Key API Endpoints (Operation IDs)

- `POST /rag/memo/save` — **`save_memo`**
  - **Input**: `session_id` (required), `memo` (required), `keywords` (optional), `importance` (optional).
  - **Behavior**: Embeds the `memo` content and saves it to ChromaDB with an `expires_at` timestamp.

- `GET /rag/memo/search` — **`query_memo`**
  - **Input**: `query` (required), `n_results` (optional).
  - **Behavior**: Performs a semantic search against the stored memos.

- `POST /rag/memos/cleanup` — **`cleanup_expired_memos`**
  - **Input**: None.
  - **Behavior**: Deletes all memos from the database that have passed their TTL.

- `GET /healthcheck` — **`healthcheck`**
  - Checks the operational status of the service.

---

# Data Model (ChromaDB Metadata)

When a memo is saved, its metadata will include:
```json
{
  "memo_id": "uuid-xxxx",
  "session_id": "sess-1",
  "saved_at": "2025-08-10T12:34:56Z",
  "expires_at": "2025-09-09T12:34:56Z",
  "keywords": "[\"project\", \"update\"]",
  "importance": 0.9
}
```

---

# Key Environment Variables

- `MEMO_TTL_DAYS`: The number of days a memo should live before expiring. Default is `30`.
- `API_KEY`: Optional API key for authentication.
- `CHROMA_PATH`: Path to the ChromaDB data directory.
- `EMBED_MODEL`: The sentence-transformer model to use.

---

# Development Flow

1.  The client provides a `memo` to the `save_memo` tool.
2.  The service embeds the memo and stores it with a calculated `expires_at` date.
3.  The client can use `query_memo` to search for relevant memos.
4.  Periodically, an administrator or automated process can call `cleanup_expired_memos` to purge old data.
