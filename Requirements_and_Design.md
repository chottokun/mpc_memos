# 要件定義書 & 設計書（FastAPI factory 形式 + fastapi\_mcp に最適化）

以下は、あなたが提示した `create_app(...)`（Factory）構成を中心に、仕様・設計・実装ノウハウを**詳細かつ実践的**にまとめたドキュメントです。
目的は「summary は任意、raw はサーバに保存しない（プライバシー重視）」「サーバは埋め込み生成と ChromaDB 登録／検索に特化」「fastapi\_mcp で MCP ツール公開」「Factory 形式で拡張モジュールを動的登録できる設計」を満たすことです。

---

# 1. 概要 / 目的

* クライアント（LM/フロント）が送信した `text`（原文）と任意の `summary`／`keywords`／`importance` を受け取り、**原文は保存せず**、埋め込み対象（summary があれば summary、なければ text の表現的チャンク）を ChromaDB に格納する MCP サーバを提供する。
* fastapi\_mcp を利用して `/mcp` エンドポイントでツールを公開し、エージェントから操作可能にする。
* サーバのエントリポイントは `create_app(no_auth: bool=False, additional_modules: Optional[List[str]]=None)`（Factory）で、追加モジュールの動的登録と認証の有無を起動時に切替可能にする。

---

# 2. 要件（機能要件 / 非機能要件）

## 2.1 機能要件（必須）

1. `POST /rag/memo/save`（operation\_id=`save_memo`）

   * 入力：`session_id`（必須）、`text`（必須）、`summary`（任意）、`keywords`（任意）、`importance`（任意）
   * 挙動：`summary` があればそれを埋め込み対象に、なければ `text` をチャンク化して埋め込み。**raw（原文）はサーバに保存しない**（必要なら `text_hash` の保存のみ）。Chroma に `documents`, `metadatas`, `embeddings` を登録。返却：`memo_id`, `saved_at`, `chroma_ids`, `used_summary`。
2. `GET /rag/memo/search`（operation\_id=`query_memo`）

   * 入力：`query`（必須）、`n_results`（任意, default=5）
   * 挙動：クエリを埋め込み → Chroma 類似検索 → 各結果に `summary/document`, `metadata`, `distance` を返す（`raw` は返却しない）。
3. `GET /rag/memo/get`（operation\_id=`get_memo`）

   * 入力：`memo_id` → Chroma のメタ情報（`memo_id` に紐づくドキュメントの metadata と documents の断片）を返す。ただし原文は含めない。
4. `POST /rag/memo/delete`（operation\_id=`delete_memo`）

   * 入力：`memo_id` → Chroma に登録された該当ドキュメント（チャンク含む）を削除。
5. `GET /healthcheck`（operation\_id=`healthcheck`）

   * 依存サービス（Chroma 永続ストア、埋め込みライブラリロードの状況、任意で Redis/DB の接続）をチェックして HTTP 200/503 を返す。
6. fastapi\_mcp によりこれら operation\_id を `/mcp` に公開すること（`FastApiMCP(...).mount()`）。

## 2.2 非機能要件

* 永続ストア：ChromaDB `PersistentClient`（ローカル永続化）を使用。
* 埋め込みモデル：`sentence-transformers`（デフォルト `cl-nagoya/ruri-v3-30m`）、初期は CPU。GPU 切替可（env `DEVICE=cuda`）。
* プライバシー：原文はサーバ側で保持しない。必要に応じて `text_hash`（SHA256）だけ記録。
* 拡張性：create\_app の `additional_modules` によるルータ動的追加をサポート。
* 認証：`get_api_key` を `Depends` で適用可能（`no_auth=True` で無効化）。`API_KEY` 環境変数と組み合わせて起動時に有効化。
* テスト：TDD を推奨。ユニットテスト（save/search/get/delete/healthcheck）と統合テスト（Chroma 実体）を用意。
* ロギング：Factory で logger を初期化。各操作に適切な log レベルを出力。
* エラーハンドリング：外部サービス（Chroma, embedder）の例外を捕捉し意味ある HTTP ステータスで返す（400/500）。

---

# 3. システム設計（アーキテクチャ）

```mermaid
graph TD
  Client[LM / Client] -->|POST /rag/memo/save| App[FastAPI (create_app)]
  App --> |call| RagRouter[/rag router/]
  RagRouter --> MemoService[MemoService (Chroma, Embedder)]
  MemoService --> Chroma[ChromaDB PersistentClient]
  MemoService --> Embedder[SentenceTransformer]
  App --> |mount| MCP[FastApiMCP (/mcp)]
```

**ポイント**

* `MemoService` は Chroma と Embedder のラッパー。非同期 API でも内部で埋め込みや Chroma のブロッキング処理を threadpool に逃がす。
* Factory (`create_app`) は `app.include_router()` による router の登録と `FastApiMCP` の mount を担う。追加モジュールは importlib 経由で動的に登録。

---

# 4. データ設計（Chroma / metadata）

* Chroma `documents`: 埋め込み対象テキスト（`summary` があれば summary、なければ text の表現チャンク）。
* Chroma `metadatas`: JSON オブジェクト。推奨フィールド：

```json
{
  "memo_id": "uuid",
  "session_id": "string",
  "chunk_index": 0,
  "is_summary": true,
  "keywords": ["..."],
  "importance": 0.8,
  "saved_at": "ISO8601",
  "text_hash": "sha256-..."
}
```

* `text_hash` はオプション（原文非保持だが、照合用に hash を保存したい場合）。
* Chroma の id 命名規則：`memo_summary:{memo_id}` or `memo_summary:{memo_id}:{chunk_index}`。

---

# 5. API 設計（詳細）

> All routes under `/rag` prefix (create\_app registers `rag_router` with prefix `/rag`)

## 5.1 POST /rag/memo/save — operation\_id=`save_memo`

* **Request JSON**

```json
{
  "session_id": "string",            // required
  "text": "string",                  // required (原文、サーバは保存しない)
  "summary": "string|null",          // optional
  "keywords": ["string"],            // optional
  "importance": 0.0                  // optional (0..1)
}
```

* **Behavior**

  * `memo_id = uuid4()`, `saved_at = now()`
  * `embed_source = summary if summary else text`
  * chunking: if `len(embed_source) > MAX_CHUNK_CHARS` → chunk into pieces
  * generate embeddings for each chunk (threadpool)
  * `collection.add(ids, documents, metadatas, embeddings)` in Chroma
  * return `{ memo_id, saved_at, chroma_ids, used_summary }`
* **Errors**

  * 400: validation error
  * 500: embedder/Chroma error

## 5.2 GET /rag/memo/search — operation\_id=`query_memo`

* **Query params**

  * `query` (required), `n_results` (optional, default 5)
* **Behavior**

  * embed query → `collection.query(query_embeddings=[emb], n_results=n_results, include=["documents","metadatas","distances"])`
  * assemble results: `{ summary: document, metadata, distance }`
  * return `{ query, results }`
* **Notes**

  * `distance` semantics depend on Chroma config; treat smaller as more similar or invert if needed. Document this in README.

## 5.3 GET /rag/memo/get — operation\_id=`get_memo`

* **Query params**

  * `memo_id` (required)
* **Behavior**

  * retrieve Chroma entries where `metadata.memo_id == memo_id` (use `collection.get(where=...)` if supported or maintain index mapping)
  * return combined metadata + documents (chunk list)
* **Security**

  * returns no raw text, only stored documents and metadata (documents are summary / embed representation)

## 5.4 POST /rag/memo/delete — operation\_id=`delete_memo`

* **Request JSON**

  * `{ "memo_id": "uuid" }`
* **Behavior**

  * attempt to delete id prefix `memo_summary:{memo_id}` and chunk suffixes
  * return `{ deleted: true }` if success or not found (idempotent)

## 5.5 GET /healthcheck — operation\_id=`healthcheck`

* **Behavior**

  * check `SentenceTransformer` model loaded (or lazy-load status), check Chroma path accessible and client can list collections, optionally DB connections
  * return `{ status: "ok", checks: { chroma: true, embedder: true } }` or 503 with details

---

# 6. 実装設計（主要コンポーネント & コード構成）

```
project_root/
├─ app/
│  ├─ __init__.py
│  ├─ main.py           # もしくは factory を呼ぶ wsgi entrypoint
│  ├─ factory.py        # create_app(...) の実体（提示済み）
│  ├─ routers/
│  │   └─ rag.py        # router: /rag/* エンドポイント群
│  ├─ services/
│  │   └─ memo_service.py  # MemoServiceNoRaw 対応（Chroma + embed）
│  ├─ auth_helpers.py   # get_api_key 実装
│  ├─ settings.py       # pydantic BaseSettings で env 管理
│  └─ utils.py          # chunking, hashing など
├─ tests/
│  ├─ unit/
│  └─ integration/
├─ requirements.txt
├─ docker-compose.yml
└─ Dockerfile
```

## 6.1 MemoService（実装上のポイント）

* API は非同期（FastAPI）に合わせて `async def` を公開するが、`SentenceTransformer` と Chroma の多くメソッドは同期的なので threadpool (`concurrent.futures.ThreadPoolExecutor`) を利用してブロッキング処理を実行する。
* 埋め込みはバッチ化（複数チャンクを一度に `embedder.encode(list)`）して性能向上。
* Chroma の `collection.add` 呼び出しも同期なので上記スレッドプールで実行。
* `collection.query` の `include=["documents","metadatas","distances"]` を使い、distance を戻す。レスポンスで距離の意味（小さい方が近い）を README に記載。

## 6.2 Router 実装（routers/rag.py）

* すべてのエンドポイントに `operation_id` を明示（fastapi\_mcp がツールを検出するため）。
* 依存注入で `Depends(get_api_key)` を利用（Factory で `dependencies` が設定済）。
* 入力/出力は Pydantic モデルで厳密に型定義。これにより fastapi\_mcp のスキーマも整う。

## 6.3 create\_app（Factory）のポイント（提示コードへの補足）

* Factory の `additional_modules` は `module.router`, `module.prefix`, `module.tags` を要求（既に提示済） — 追加で `module.setup(app, settings)` などの初期化 hook を推奨（DI を容易にするため）。
* `auth_dependencies` の扱い：モジュール側で path operation に個別の Depends をつける場合、Factory での `dependencies` と重複しないよう注意。複数の認証ポリシーを扱う場合は configuration を整理する。
* `FastApiMCP(..., describe_all_responses=True, describe_full_response_schema=True)` は dev-friendly。プロダクションでは適宜設定をチューニング。

---

# 7. 設定（env / settings.py）

推奨は `pydantic.BaseSettings` を使う。主要環境変数：

* `API_KEY` — (optional) 認証を有効にする API トークン
* `NO_AUTH` — Factory 起動時に no\_auth フラグを設定するためのデフォルト
* `CHROMA_PATH` (default `./chroma_db`)
* `EMBED_MODEL` (default `cl-nagoya/ruri-v3-30m`)
* `DEVICE` (`cpu`/`cuda`)
* `MAX_CHUNK_CHARS` (default 2000)
* `N_RESULTS_DEFAULT` (default 5)
* `EMBED_THREAD_WORKERS` (default 2)

---

# 8. エラー処理、異常系設計

* **モデルロード失敗**：起動時に必須でロードする（早期失敗）か、遅延ロードして healthcheck に反映させるか設定可能。推奨は起動時にロードしてエラーで停止（fail-fast）。
* **Chroma IO エラー**：collection.add/query が失敗したら 503 を返すか retry（指数バックオフ）を行う。エラーは監視に送る。
* **入力不正**：Pydantic でバリデーション → 400 を返す。
* **重複検出**：保存時にオプションで近傍検索 ⇒ 類似度が閾値以上なら `409 Conflict` か `200` with `merged:true` を返す（設計で決定）。

---

# 9. テスト計画（TDD）

* **ユニットテスト**（pytest）：

  * MemoService: `_chunk_text`, `_embed_texts`（モック化）, save\_memo（summaryあり/なし）, search\_with\_raw (Chroma mock)
  * Router: 入力バリデーション、operation\_id の有無、auth の動作（get\_api\_key モック）
* **統合テスト**（docker-compose で Chroma 実体 or chroma-mock）：

  * End-to-end: POST /rag/memo/save → GET /rag/memo/search の一連検証
* **負荷テスト**：embedding スループット、同時保存回数に対するレスポンスタイム測定（locust 等）

---

# 10. デプロイ / docker-compose（概要）

* `api` コンテナ（Dockerfile で SentenceTransformer の依存を組み込む、注意: 大きい）
* Chroma はローカルファイルで永続化（volume mount）を API コンテナ内で行うか、専用 Chroma コンテナ（もし提供されれば）を使う。現状 easiest は API コンテナに ChromaDB の data path をボリュームでマウント。
* `docker-compose.yml` のサービス:

  * `api`（build: ., ports: \["8000:8000"]）
  * （オプション）`redis`：今回は raw 非保存にしたため不要（省略可）
* ボリューム: `chroma_data:/data/chroma` を推奨

---

# 11. ロギング / 監視 / Observability

* Factory で `logging.basicConfig(...)` を適切に初期化（提示コードのまま）。
* 各主要操作（save/search/delete/healthcheck）に `logger.info/debug/error` を出す。metadata のみログ出力（原文は出力しない）。
* Prometheus エクスポータ（uvicorn+prometheus）を組み込み可。`/metrics` エンドポイントでメトリクス収集。
* Sentry 等で例外トラッキングを設定することを推奨。

---

# 12. 拡張ポイント（優先度順）

1. **promote\_memo**：重要な summary を長期 DB（Postgres）に移す API。
2. **dedupe\_on\_save**：保存時に近傍検索してマージ or skip 機能。
3. **server-side summarize**：raw しか送れないクライアント向けにオプションで要約を生成（LLM 呼び出し）。
4. **Admin UI**：検索、削除、promote、TTL 管理用インターフェース。
5. **multi-collection support**：複数の Chroma コレクションを指定して検索（優先度付きブレンド検索）。

---

# 13. マイグレーション / 実装手順（ステップ）

1. Factory (`create_app`) をプロジェクトの起点にする（提示コードをベース）。
2. `routers/rag.py` を実装（Pydantic schema + endpoints + operation\_id）し、Factory で `include_router` する。
3. `services/memo_service.py`（raw 非保存）を実装。threadpool & error handling を入れる。
4. `FastApiMCP` を Factory で mount（すでに実装済み）。
5. Healthcheck を追加。
6. tests を作成（ユニット → 統合）。
7. docker-compose を作成し動作確認。
8. ドキュメント（README, Agent.md, API spec）を完成させる。

---

# 14. セキュリティ / プライバシー方針（重要）

* **データ最小化**：原文を保存しない設計でプライバシー侵害リスクを低減。
* **認証**：`API_KEY` と `get_api_key` による保護。公開 API にする際は OAuth2/JWT を推奨。
* **ログ**：ログに原文を出力しない（metadata のみ）。
* **暗号化**：Chroma データやサーバストレージの at-rest 暗号化を検討（プロダクション）。

---

# 15. 例：routers/rag.py の骨子（参考）

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from ..services.memo_service import MemoServiceNoRaw
from ..auth_helpers import get_api_key  # used in factory dependencies

router = APIRouter()

memo_svc = MemoServiceNoRaw()

class SaveReq(BaseModel):
    session_id: str
    text: str
    summary: Optional[str] = None
    keywords: Optional[List[str]] = None
    importance: float = 0.0

@router.post("/memo/save", operation_id="save_memo")
async def save_memo(req: SaveReq):
    res = await memo_svc.save_memo(req.session_id, req.text, req.summary, req.keywords, req.importance)
    return res

@router.get("/memo/search", operation_id="query_memo")
async def search_memo(query: str = Query(...), n_results: int = Query(5)):
    return await memo_svc.search(query, n_results)

# get, delete, etc...
```

---

# 16. ドキュメント・README に記載すべき点（要約）

* 起動方法（venv, pip install -r requirements.txt, uvicorn main\:app）
* Factory の使い方（`create_app(no_auth=True)` など）
* 環境変数一覧（上記）
* API サンプル（curl）
* プライバシーポリシー：原文を保存しない事、必要に応じてクライアント側で原文管理を明記

---

# 17. 設計変更履歴 (Refactoring History)

## 2025-08-10: `summary`/`text`から`memo`への移行とTTL機能の追加

ユーザーからのフィードバックに基づき、プロジェクトのコンセプトをより明確にするための大規模なリファクタリングを実施。

### 変更の背景
当初の設計では、クライアントは`text`（原文）または`summary`（要約）を送信可能だった。しかし、プライバシーを最大化し、サービスの責務を「短期的なメモの管理」に特化させるため、以下の設計変更を行った。

### 主な変更点
1.  **APIの単純化 (`summary` → `memo`)**:
    *   `POST /rag/memo/save` APIは、`text`フィールドを廃止し、必須フィールドとして`memo`のみを受け付けるように変更。これにより、サーバーはクライアントが提供したメモの内容のみを処理し、原文と要約の区別が不要になった。
    *   `SaveMemoRequest`スキーマから`text`と`summary`を削除し、`memo`を追加。
    *   `SearchResultItem`のレスポンスフィールドも`summary`から`memo`に変更し、API全体で用語を統一。

2.  **TTL (Time-To-Live) 機能の実装**:
    *   **メタデータ**: メモ保存時、`settings.MEMO_TTL_DAYS`（デフォルト30日）に基づいて`expires_at`（有効期限）タイムスタンプを計算し、メタデータとして保存する機能を追加。
    *   **クリーンアップAPI**: `POST /rag/memos/cleanup` エンドポイントを新設。このAPIを呼び出すと、`expires_at`が現在時刻を過ぎている全てのメモがデータベースから削除される。
    *   **設定**: `MEMO_TTL_DAYS`を環境変数として追加し、メモの有効期間を外部から設定可能にした。

### 設計思想の変化
この変更により、本サービスは「長期的な知識ベース」という側面から、「プライバシーを重視した短期的なメモ管理・検索サービス」という、より明確なコンセプトに移行した。
