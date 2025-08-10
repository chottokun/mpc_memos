# MCP Memo Service

## 1. Overview

This project is a FastAPI application that provides a privacy-focused RAG (Retrieval-Augmented Generation) Memo Service. It allows clients (like AI agents or frontends) to save, search, and manage textual memos.

The core design principle is **privacy by design**: the server **does not store the original raw text** of the memos. Instead, it generates and stores vector embeddings from either a user-provided summary or from chunks of the original text. This allows for powerful semantic search capabilities without holding sensitive raw data.

The API is also exposed as a set of tools for AI agents using `fastapi-mcp`.

## 2. Features

- **Privacy-First**: Raw text is never persisted on the server.
- **Semantic Search**: Save text or summaries and search for them based on meaning using vector embeddings.
- **Flexible Content**: Use a pre-generated `summary` for higher accuracy and privacy, or send the raw `text` and let the server handle chunking and embedding.
- **Agent-Ready**: Endpoints are exposed as tools via `/mcp` for easy integration with AI agents.
- **Standard API**: A simple and clean RESTful API for managing memos (`save`, `search`, `get`, `delete`).
- **Containerized**: Comes with a `Dockerfile` and `docker-compose.yml` for easy and reproducible deployment.
- **Configurable**: Uses environment variables for configuration, including optional API key authentication.

## 3. Privacy Policy

**The server is designed to not store the original, raw `text` that is sent to the `/rag/memo/save` endpoint.**

- If a `summary` is provided in the request, only the summary is used for embedding and storage.
- If no `summary` is provided, the `text` is chunked, and those chunks are used for embedding and storage.
- In both cases, the original `text` is discarded after the request is processed.

For verification purposes, a `text_hash` (SHA256) of the original text is stored in the metadata. This hash cannot be used to recover the original text.

**It is the client's responsibility to store and manage the original raw text if it needs to be retrieved later.** This service acts as a searchable index, not a primary data store for raw content.

## 4. API Endpoints

All endpoints are available under the `/rag` prefix.

| Method | Endpoint              | Operation ID  | Description                                        |
|--------|-----------------------|---------------|----------------------------------------------------|
| `POST` | `/memo/save`          | `save_memo`   | Saves a new memo.                                  |
| `GET`  | `/memo/search`        | `query_memo`  | Searches for memos by a query string.              |
| `GET`  | `/memo/get`           | `get_memo`    | Retrieves stored documents and metadata for a memo.|
| `POST` | `/memo/delete`        | `delete_memo` | Deletes a memo and its associated data.            |

An additional healthcheck endpoint is also available:

| Method | Endpoint       | Operation ID  | Description                               |
|--------|----------------|---------------|-------------------------------------------|
| `GET`  | `/healthcheck` | `healthcheck` | Checks the operational status of the service. |

For detailed request/response schemas, please refer to the OpenAPI documentation at `/docs`.

## 5. Setup and Installation

You can run the service either locally using a Python virtual environment or with Docker.

### 5.1. Docker (Recommended)

This is the easiest way to get the service running with its dependencies.

1.  **Prerequisites**: Docker and Docker Compose must be installed.
2.  **Build and Run**:
    ```bash
    docker-compose up --build
    ```
3.  The API will be available at `http://localhost:8000`.

### 5.2. Local Python Environment

1.  **Prerequisites**: Python 3.11+ and `pip`.
2.  **Create a virtual environment**:
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```
3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
4.  **Run the application**:
    ```bash
    uvicorn app.main:app --host 0.0.0.0 --port 8000
    ```
5.  The API will be available at `http://localhost:8000`.

## 6. Configuration (Environment Variables)

The application can be configured using a `.env` file in the project root or by setting environment variables.

| Variable                 | Description                                                              | Default Value            |
|--------------------------|--------------------------------------------------------------------------|--------------------------|
| `API_KEY`                | If set, enables API key authentication. Clients must send this key in the `X-API-KEY` header. | `None`                   |
| `NO_AUTH`                | Set to `True` to disable authentication, even if `API_KEY` is set.       | `False`                  |
| `CHROMA_PATH`            | The local filesystem path to store the ChromaDB database.                | `./chroma_db`            |
| `EMBED_MODEL`            | The name of the `sentence-transformers` model to use for embeddings.     | `cl-nagoya/ruri-v3-30m`  |
| `DEVICE`                 | The device to run the embedding model on (`cpu` or `cuda`).              | `cpu`                    |
| `MAX_CHUNK_CHARS`        | The maximum number of characters per chunk when embedding raw text.      | `2000`                   |
| `N_RESULTS_DEFAULT`      | The default number of results to return for search queries.              | `5`                      |
| `EMBED_THREAD_WORKERS`   | The number of threads to use for running blocking tasks like embedding.  | `2`                      |

**Example `.env` file:**
```
# For development, you might disable auth
NO_AUTH=True

# To enable auth, comment out NO_AUTH and set an API_KEY
# API_KEY="my-secret-api-key"

CHROMA_PATH="./chroma_db_data"
```

## 7. Usage Examples (curl)

These examples assume the service is running on `localhost:8000` with authentication disabled (`NO_AUTH=True`).

### Save a Memo

```bash
curl -X 'POST' \
  'http://localhost:8000/rag/memo/save' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "session_id": "curl-session-1",
  "text": "The quick brown fox jumps over the lazy dog.",
  "summary": "A sentence about a fox and a dog.",
  "keywords": ["animal", "fox", "dog"],
  "importance": 0.7
}'
```

### Search for Memos

```bash
curl -X 'GET' \
  'http://localhost:8000/rag/memo/search?query=what%20did%20the%20fox%20do' \
  -H 'accept: application/json'
```

### Get a Memo by ID

(Replace `your-memo-id` with an actual ID from a `save` response)
```bash
curl -X 'GET' \
  'http://localhost:8000/rag/memo/get?memo_id=your-memo-id' \
  -H 'accept: application/json'
```

### Delete a Memo by ID

(Replace `your-memo-id` with an actual ID)
```bash
curl -X 'POST' \
  'http://localhost:8000/rag/memo/delete' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "memo_id": "your-memo-id"
}'
```
