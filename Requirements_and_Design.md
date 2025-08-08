# 1. 要求仕様書

## 1.1 目的

クライアント（LM／フロント）が送信した会話やメモの「原文（text）」と任意の「summary」「keywords」を受け取り、**summary（存在すれば）またはtext（summaryが無ければ）** を埋め込み対象として ChromaDB に登録。raw は Redis に TTL（デフォルト 24h）で保存。検索時はクエリを埋め込み化して ChromaDB で類似検索し、検索結果（summary, metadata, score, raw（存在する場合））を返す。

## 1.2 API（主要）

* `POST /memo/save` — operation\_id=`save_memo`
  Body (JSON):

  ```json
  {
    "session_id": "string",
    "text": "原文（必須）",
    "summary": "任意の要約または null",
    "keywords": ["任意"],
    "importance": 0.0
  }
  ```

  Response: `{ memo_id, saved_at, chroma_ids: [..], used_summary: bool }`

* `GET /memo/search` — operation\_id=`query_memo`
  Params: `query` (必須), `n_results` (optional, default=5)
  Response: `{ query, results: [{ summary, metadata, distance, raw (may be null) }, ...] }`

* `GET /memo/get` — operation\_id=`get_memo`
  Params: `memo_id` → returns raw+metadata (or 404 if expired)

* `POST /memo/delete` — operation\_id=`delete_memo`
  Body: `{ memo_id }` → deletes Redis raw and Chroma entries

* `POST /memo/clear_expired` — operation\_id=`clear_expired`（管理用、SQLite/ファイルバックアップ等がある場合の掃除用）

## 1.3 挙動ルール（重要）

* `summary` があれば **summary を埋め込み対象** にする。なければ `text`（raw）を埋め込み対象にする。
* `text` が大きすぎる（設定 `MAX_CHUNK_CHARS` を超える）場合はサーバ側で**チャンク分割**し、各チャンクを個別の Chroma ドキュメントとして登録する（metadata に `chunk_index` を付与）。Redis には raw 全体をひとつのエントリで保存する。
* Redis は TTL 管理（デフォルト 24時間）。summary（Chroma）は TTL が無い限り長期残る（運用で promote など可能）。
* 重複対策（オプション）：保存時に埋め込みを近傍検索して、類似度が閾値を超える既存 summary があったら **新規追加 or マージ** を選べる（初版ではマージはオプション機能）。

# 2. 設計書

## 2.1 全体アーキテクチャ（簡略）

```
クライアント(LLM) -> POST /memo/save  (text + optional summary)
                                  |
                               FastAPI (/mcp)
                                  |
                             MemoService
                               /     \
                          Redis       ChromaDB
                     (raw, TTL)   (summary embeddings)
                                  |
                      GET /memo/search -> Chroma query -> get raw from Redis
```

## 2.2 コンポーネント

### MemoService

* 設定:

  * `REDIS_URL`（例: redis\://redis:6379/0）
  * `CHROMA_PATH`（ローカルディレクトリ）
  * `EMBED_MODEL`（例: cl-nagoya/ruri-v3-30m）
  * `MEMO_TTL_SECONDS`（デフォルト 86400）
  * `MAX_CHUNK_CHARS`（分割閾値、例 2000）
  * `N_RESULTS_DEFAULT`（検索デフォルト 5）

* メソッド:

  * `save_memo(session_id, text, summary=None, keywords=None, importance=0.0)`

    * generate memo\_id, saved\_at
    * store raw → Redis key `memo:{memo_id}` (hash), EXPIRE ttl
    * determine embed\_source = summary or text
    * if embed\_source length > MAX\_CHUNK\_CHARS => chunk -> create multiple embeddings and chroma docs with ids `memo_summary:{memo_id}:{i}`
    * else create single embedding and chroma doc `memo_summary:{memo_id}`
    * return metadata

  * `search(query, n_results=5)`

    * embed query, chroma.query -> obtain documents/metadatas/distances
    * for each result, get `memo_id` from metadata, load raw from Redis (may be expired)
    * return list of results

  * `get_memo(memo_id)` — return Redis hash or 404

  * `delete_memo(memo_id)` — delete Redis key & chroma doc(s)

### Data model (Chroma metadata)

```json
{
  "memo_id": "uuid",
  "session_id": "...",
  "chunk_index": 0,           // chunked の場合
  "is_summary": true/false,
  "keywords": [...],
  "importance": 0.0,
  "saved_at": "ISO8601"
}
```

## 2.3 非機能要件

* **性能**: embedding は CPU/GPU によるが、API は `embed` 呼び出しをスレッドプールで回す（非ブロッキング）。
* **信頼性**: Redis 接続失敗時はフェイルバック（エラーを返すかローカルDB保存のオプション）。
* **保守性**:設定は env で。MemoService はバックエンド切替可能。
* **セキュリティ**: `HTTPBearer` 等で認証。監査ログは将来的に追加。

# 3. サンプル実装

下記は **フルの動作例** です。ファイル群をそのままプロジェクトに置けば動作ができるように考えています。（必要パッケージは `requirements.txt` に記載）。実行はローカル or Docker Compose を推奨。


---

## 3.1 requirements.txt

```
fastapi
uvicorn[standard]
fastapi_mcp
chromadb
sentence-transformers
redis[asyncio]
python-multipart
pydantic
```

---

## 3.2 memo\_service.py

```python
# memo_service.py
import os
import uuid
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import asyncio
from concurrent.futures import ThreadPoolExecutor

import chromadb
from sentence_transformers import SentenceTransformer

# 設定（env で上書き可能）
CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")
EMBED_MODEL = os.getenv("EMBED_MODEL", "cl-nagoya/ruri-v3-30m")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
MEMO_TTL_SECONDS = int(os.getenv("MEMO_TTL_SECONDS", str(24 * 3600)))
MAX_CHUNK_CHARS = int(os.getenv("MAX_CHUNK_CHARS", "2000"))
N_RESULTS_DEFAULT = int(os.getenv("N_RESULTS_DEFAULT", "5"))

def now_iso():
    return datetime.now(timezone.utc).isoformat()

class MemoService:
    def __init__(self, redis_client=None):
        # chroma client (sync)
        self.chroma = chromadb.PersistentClient(path=CHROMA_PATH)
        self.collection = self.chroma.get_or_create_collection(name="memo_summaries")
        # embedder (sync)
        self.embedder = SentenceTransformer(EMBED_MODEL, device=os.getenv("DEVICE", "cpu"))
        # redis (async)
        import redis.asyncio as redis
        self.redis = redis_client or redis.from_url(REDIS_URL)
        self.ttl = MEMO_TTL_SECONDS
        # executor for blocking ops
        self._executor = ThreadPoolExecutor(max_workers=int(os.getenv("EMBED_THREAD_WORKERS","2")))

    # --- helper: chunk text by characters ---
    def _chunk_text(self, text: str, chunk_size: int = MAX_CHUNK_CHARS) -> List[str]:
        if len(text) <= chunk_size:
            return [text]
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append(text[start:end])
            start = end
        return chunks

    # embed in threadpool (blocking call)
    async def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, lambda: self.embedder.encode(texts).tolist())

    # chroma add in threadpool (sync)
    async def _chroma_add(self, ids, documents, metadatas, embeddings):
        loop = asyncio.get_running_loop()
        def _add():
            self.collection.add(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
        await loop.run_in_executor(self._executor, _add)

    # chroma query in threadpool (sync)
    async def _chroma_query(self, embedding, n_results):
        loop = asyncio.get_running_loop()
        def _query():
            return self.collection.query(query_embeddings=[embedding], n_results=n_results, include=["documents","metadatas","distances"])
        return await loop.run_in_executor(self._executor, _query)

    # --- public APIs ---
    async def save_memo(self, session_id: str, text: str, summary: Optional[str] = None, keywords: Optional[List[str]] = None, importance: float = 0.0) -> Dict[str, Any]:
        memo_id = str(uuid.uuid4())
        saved_at = now_iso()
        # store raw in redis as hash
        rkey = f"memo:{memo_id}"
        raw_payload = {
            "memo_id": memo_id,
            "session_id": session_id,
            "text": text,
            "saved_at": saved_at,
            "keywords": keywords or [],
            "importance": importance
        }
        # hset mapping requires strings
        mapping = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in raw_payload.items()}
        await self.redis.hset(rkey, mapping=mapping)
        await self.redis.expire(rkey, self.ttl)

        # choose embed source
        embed_source = summary if summary else text
        is_summary = bool(summary)

        # chunk if too large
        chunks = self._chunk_text(embed_source, MAX_CHUNK_CHARS)
        ids = []
        docs = []
        metas = []
        # create embeddings
        embeddings = await self._embed_texts(chunks)

        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            chroma_id = f"memo_summary:{memo_id}"
            if len(chunks) > 1:
                chroma_id = f"{chroma_id}:{i}"
            meta = {
                "memo_id": memo_id,
                "session_id": session_id,
                "chunk_index": i if len(chunks) > 1 else 0,
                "is_summary": is_summary,
                "keywords": keywords or [],
                "importance": importance,
                "saved_at": saved_at
            }
            ids.append(chroma_id)
            docs.append(chunk)
            metas.append(meta)

        # add to chroma
        await self._chroma_add(ids=ids, documents=docs, metadatas=metas, embeddings=embeddings)

        return {"memo_id": memo_id, "saved_at": saved_at, "chroma_ids": ids, "used_summary": is_summary}

    async def get_raw(self, memo_id: str) -> Optional[Dict[str, Any]]:
        rkey = f"memo:{memo_id}"
        exists = await self.redis.exists(rkey)
        if not exists:
            return None
        h = await self.redis.hgetall(rkey)
        # decode hash
        out = {}
        for k, v in h.items():
            key = k.decode()
            val = v.decode()
            if key in ("keywords",):
                try:
                    out[key] = json.loads(val)
                except Exception:
                    out[key] = []
            else:
                out[key] = val
        return out

    async def search_with_raw(self, query: str, n_results: int = N_RESULTS_DEFAULT) -> Dict[str, Any]:
        # embed query
        emb_list = await self._embed_texts([query])
        q_emb = emb_list[0]
        # query chroma
        res = await self._chroma_query(q_emb, n_results)
        results = []
        # result arrays may be empty
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for doc, meta, dist in zip(docs, metas, dists):
            memo_id = meta.get("memo_id")
            raw = await self.get_raw(memo_id)
            results.append({
                "summary": doc,
                "metadata": meta,
                "distance": dist,
                "raw": raw  # may be None if expired
            })
        return {"query": query, "results": results}

    async def delete_memo(self, memo_id: str) -> bool:
        # delete redis key
        await self.redis.delete(f"memo:{memo_id}")
        # delete chroma ids that match prefix
        prefix = f"memo_summary:{memo_id}"
        # fetch all ids (simple approach: try to delete id and chunk ids up to some number)
        # safer way: collection.get(include=['ids']) isn't always supported; so best to attempt delete by pattern up to N chunks
        # We'll attempt delete for prefix and prefix:0..99
        ids_to_try = [prefix] + [f"{prefix}:{i}" for i in range(0, 100)]
        try:
            self.collection.delete(ids=ids_to_try)
        except Exception:
            # ignore if not found
            pass
        return True
```

---

## 3.3 main.py (FastAPI + fastapi\_mcp)

```python
# main.py
import uvicorn
from fastapi import FastAPI, HTTPException, Depends, Body
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from fastapi_mcp import FastApiMCP

from memo_service import MemoService

app = FastAPI(title="Memo MCP (summary optional)")

# simple auth - production should use stronger mechanism
auth = HTTPBearer()

memo_svc = MemoService()

mcp = FastApiMCP(app, name="Memo MCP Service", description="Store raw + optional summary as embeddings")
mcp.mount()

class SaveReq(BaseModel):
    session_id: str
    text: str
    summary: str = None
    keywords: list = None
    importance: float = 0.0

@app.post("/memo/save", operation_id="save_memo", summary="保存: text と任意 summary")
async def save_memo(req: SaveReq, token=Depends(auth)):
    if not req.session_id or not req.text:
        raise HTTPException(status_code=400, detail="session_id and text are required")
    res = await memo_svc.save_memo(req.session_id, req.text, req.summary, req.keywords, req.importance)
    return res

@app.get("/memo/search", operation_id="query_memo", summary="検索: クエリで Chroma 類似検索")
async def search_memo(query: str, n_results: int = 5, token=Depends(auth)):
    if not query:
        raise HTTPException(status_code=400, detail="query required")
    res = await memo_svc.search_with_raw(query, n_results)
    return res

@app.get("/memo/get", operation_id="get_memo", summary="取得: memo_id で raw を取得")
async def get_memo(memo_id: str, token=Depends(auth)):
    raw = await memo_svc.get_raw(memo_id)
    if not raw:
        raise HTTPException(status_code=404, detail="memo not found or expired")
    return raw

@app.post("/memo/delete", operation_id="delete_memo", summary="削除: memo_id で削除")
async def delete_memo(payload: dict = Body(...), token=Depends(auth)):
    memo_id = payload.get("memo_id")
    if not memo_id:
        raise HTTPException(status_code=400, detail="memo_id required")
    await memo_svc.delete_memo(memo_id)
    return {"deleted": True}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(__import__("os").environ.get("PORT", "8000")))
```

---

## 3.4 Dockerfile（API コンテナ用・参考）

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# system deps for sentence-transformers, chromadb may require build tools; adjust as needed
RUN apt-get update && apt-get install -y build-essential git ffmpeg libsndfile1 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

---

## 3.5 docker-compose.yml（Redis + API, Chroma uses a mounted folder inside API）

```yaml
version: "3.8"
services:
  redis:
    image: redis:7
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data

  api:
    build: .
    environment:
      - REDIS_URL=redis://redis:6379/0
      - CHROMA_PATH=/data/chroma
      - MEMO_TTL_SECONDS=86400
      - MAX_CHUNK_CHARS=2000
      - EMBED_MODEL=cl-nagoya/ruri-v3-30m
    ports:
      - "8000:8000"
    volumes:
      - ./chroma_data:/data/chroma
    depends_on:
      - redis

volumes:
  redis-data:
```

---

## 3.6 実行手順（ローカル）

1. 必要パッケージのインストール（仮想環境推奨）

   ```
   pip install -r requirements.txt
   ```
2. Redis を起動（ローカルまたは Docker）

   ```
   docker run -p 6379:6379 --name redis -d redis:7
   ```
3. API を起動

   ```
   uvicorn main:app --reload
   ```
4. Swagger UI: `http://127.0.0.1:8000/docs`
   MCP: `http://127.0.0.1:8000/mcp`

---

## 3.7 curl 実行例

```bash
# 保存（Authorization header は HTTPBearer の検証に合わせて設定）
curl -X POST "http://127.0.0.1:8000/memo/save" \
 -H "Content-Type: application/json" \
 -H "Authorization: Bearer <TOKEN>" \
 -d '{
   "session_id":"sess-1",
   "text":"これは保存したい長文の原文です...",
   "summary":"（任意）要点：〜〜",
   "keywords":["手順","注意"],
   "importance":0.8
 }'

# 検索
curl -G "http://127.0.0.1:8000/memo/search" --data-urlencode "query=要点" -H "Authorization: Bearer <TOKEN>"

# 取得
curl -G "http://127.0.0.1:8000/memo/get" --data-urlencode "memo_id=<memo_id>" -H "Authorization: Bearer <TOKEN>"
```

# 4. 運用・拡張提案（短く）

* **Promote 機能**：重要な summary を長期保存 DB（Postgres）に移す `promote_memo` を実装すると、知恵袋的なナレッジベースになる。
* **重複除去**：`save_memo` の最初に summary/text 埋め込みで近傍検索し、類似度 > 0.95 の既存があればマージ or スキップするフラグを提供。
* **品質向上**：クライアント用に「要約プロンプト（日本語）」テンプレートを用意すると summary の品質が均一化する。
* **非同期化**：埋め込みや Chroma 登録を BackgroundTasks にして即時レスポンス + 後処理にすると UX が良くなる（ただし整合性が必要）。
* **監査ログ**：誰がいつ memo を保存/削除したかのログを残す（GDPR/ログ追跡要件対応）。

# 5. テスト計画（短く）

* ユニット: save\_memo（summaryあり/なし）、get\_raw、search（expected count, distance）、delete。
* 統合: Redis + Chroma 実体での検索ワークフロー（短い summary と長い raw の両方）。
* ストレス: 同期埋め込み負荷、複数同時保存でのスループット測定。

