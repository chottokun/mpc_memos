# MCP Memo Service

## 1. Overview

This project is a FastAPI application that provides a privacy-focused, ephemeral Memo Service. It allows clients (like AI agents or frontends) to save, search, and manage textual memos with a configurable Time-to-Live (TTL).

The core design principle is **minimalism**: the server primarily focuses on the `memo` content, which enables powerful semantic search capabilities for short-term notes.

The API is also exposed as a set of tools for AI agents using `fastapi-mcp`.

## 2. Features

- **Ephemeral Memos**: Memos automatically expire after a configurable Time-to-Live (TTL), defaulting to 30 days.
- **Semantic Search**: Search for memos based on meaning using vector embeddings.
- **Agent-Ready**: Endpoints are exposed as tools via `/mcp` for easy integration with AI agents.
- **Standard API**: A simple and clean RESTful API for managing memos (`save`, `search`, `get`, `delete`, `cleanup`).
- **Containerized**: Includes a `Dockerfile` and `docker-compose.yml` for easy and reproducible deployment.
- **Configurable**: Uses environment variables for configuration, including optional API key authentication and memo TTL.

## 3. API Endpoints

| Method | Endpoint              | Operation ID            | Description                                        |
|--------|-----------------------|-------------------------|----------------------------------------------------|
| `POST` | `/rag/memo/save`      | `save_memo`             | Saves a new memo with a TTL.                       |
| `GET`  | `/rag/memo/search`    | `query_memo`            | Searches for memos by a query string.              |
| `GET`  | `/rag/memo/get`       | `get_memo`              | Retrieves the content and metadata for a specific memo. |
| `POST` | `/rag/memo/delete`    | `delete_memo`           | Deletes a specific memo by its ID.                 |
| `POST` | `/rag/memos/cleanup`  | `cleanup_expired_memos` | Deletes all memos that have passed their TTL.      |
| `GET`  | `/healthcheck`        | `healthcheck`           | Checks the operational status of the service.      |

For detailed request/response schemas, please refer to the OpenAPI documentation at `/docs`.

## 4. Setup and Installation

You can run the service either locally using a Python virtual environment or with Docker.

### 4.1. Docker (Recommended)

1.  **Prerequisites**: Docker and Docker Compose must be installed.
2.  **Build and Run**:
    ```bash
    docker-compose up --build
    ```
3.  The API will be available at `http://localhost:8000`.

### 4.2. Local Python Environment

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

## 5. Configuration (Environment Variables)

The application can be configured using a `.env` file in the project root or by setting environment variables.

| Variable                 | Description                                                              | Default Value            |
|--------------------------|--------------------------------------------------------------------------|--------------------------|
| `API_KEY`                | If set, enables API key authentication. Clients must send this key in the `X-API-KEY` header. | `None`                   |
| `NO_AUTH`                | Set to `True` to disable authentication, even if `API_KEY` is set.       | `False`                  |
| `CHROMA_PATH`            | The local filesystem path to store the ChromaDB database.                | `./chroma_db`            |
| `EMBED_MODEL`            | The name of the `sentence-transformers` model to use for embeddings.     | `cl-nagoya/ruri-v3-30m`  |
| `DEVICE`                 | The device to run the embedding model on (`cpu` or `cuda`).              | `cpu`                    |
| `MAX_CHUNK_CHARS`        | The maximum number of characters per chunk when embedding a memo.        | `2000`                   |
| `N_RESULTS_DEFAULT`      | The default number of results to return for search queries.              | `5`                      |
| `EMBED_THREAD_WORKERS`   | The number of worker threads for background tasks like embedding.        | `2`                      |
| `MEMO_TTL_DAYS`          | The number of days after which a memo is considered expired.             | `30`                     |


**Example `.env` file:**
```
# For development, you might disable auth
NO_AUTH=True
MEMO_TTL_DAYS=7

# To enable auth, comment out NO_AUTH and set an API_KEY
# API_KEY="my-secret-api-key"
```

## 6. Usage Examples (curl)

These examples assume the service is running on `localhost:8000` with authentication disabled (`NO_AUTH=True`).

### Save a Memo

```bash
curl -X 'POST' \
  'http://localhost:8000/rag/memo/save' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "session_id": "curl-session-1",
  "memo": "This is a new memo about the project status.",
  "keywords": ["project", "status", "update"],
  "importance": 0.9
}'
```

### Search for Memos

```bash
curl -X 'GET' \
  'http://localhost:8000/rag/memo/search?query=project%20status' \
  -H 'accept: application/json'
```

### Cleanup Expired Memos

```bash
curl -X 'POST' \
  'http://localhost:8000/rag/memos/cleanup' \
  -H 'accept: application/json'
```

## 7. Acknowledgements

This project was made possible by the `fastapi_mcp` library. Our thanks go to its developers and contributors.
https://github.com/tadata-org/fastapi_mcp
