# Agent.md — Memo MCP サービス

---

# プロジェクト概要

FastAPI + `fastapi_mcp` + ChromaDB + `sentence-transformers`（デフォルト: `cl-nagoya/ruri-v3-30m`）を用いた MCP サーバ実装。
クライアント（LM/フロント）が送る `text`（原文）と任意の `summary`／`keywords`／`importance` を受け、**原文はサーバに保存せず**、要約または表現チャンクを埋め込み対象として ChromaDB に登録することで、プライバシーに配慮した RAG（知恵袋的検索）を提供する。

---

# 目的

* クライアント側で生成した要点（summary）があればそれを、無ければ原文の表現チャンクを埋め込み化して保存する。
* 原文をサーバに残さないことでプライバシーを保ちつつ検索可能な知識ベースを構築する。
* `fastapi_mcp` により `/mcp` でツール公開し、エージェントから利用できるようにする。
* Factory 形式 `create_app(no_auth=False, additional_modules=None)` を起点に拡張・モジュール追加が容易な設計とする。

---

# 要点（短く）

* `summary` は任意（あればそれを埋め込み、なければ `text` をチャンク化して埋め込み）。
* **raw（原文）は保存しない**。メタに `text_hash`（オプション）を残すのみ。
* 検索は Chroma の類似検索で行い、結果には `summary/document`、`metadata`、`distance` を返す（`raw` は返さない）。
* Factory で動的ルータ登録、`FastApiMCP(...).mount()` による MCP 公開。

---

# アーキテクチャ（概略）

```
Client (LM) -- POST /rag/memo/save --> FastAPI (create_app)
                                         └─ routers/rag.py
                                            └─ MemoService (Chroma + Embedder)
                                                 ├─ ChromaDB (PersistentClient)
                                                 └─ SentenceTransformer (embed)
/mcp (FastApiMCP) で operation_id を公開
```

---

# 主要 API（operation\_id 明示）

* `POST /rag/memo/save` — **operation\_id="save\_memo"**
  入力: `session_id` (必須), `text` (必須), `summary` (任意), `keywords` (任意), `importance` (任意)
  出力: `{ memo_id, saved_at, chroma_ids, used_summary }`
  挙動: summary があればそれを埋め込み対象、無ければ text をチャンク化して埋め込み。原文は保存しない（`text_hash` はオプションで保存可）。

* `GET /rag/memo/search` — **operation\_id="query\_memo"**
  クエリ: `query` (必須), `n_results` (任意, default=5)
  出力: `{ query, results: [{ summary, metadata, distance }, ...] }`

* `GET /rag/memo/get` — **operation\_id="get\_memo"**
  パラメータ: `memo_id`
  出力: Chroma に格納された document/chunk と metadata（原文は含まない）

* `POST /rag/memo/delete` — **operation\_id="delete\_memo"**
  入力: `{ memo_id }` → 該当 Chroma ドキュメント（チャンク含む）を削除

* `GET /healthcheck` — **operation\_id="healthcheck"**
  Chroma・埋め込みモデルロード等のヘルスを返す

> すべて `/rag` プレフィックス下に配置し、`create_app` で router を include する。

---

# データモデル（Chroma metadata 例）

`documents` は保存した要約またはチャンク化された表現テキスト。`metadatas` は最小限のメタ情報。

```json
{
  "memo_id": "uuid-xxxx",
  "session_id": "sess-1",
  "chunk_index": 0,
  "is_summary": true,
  "keywords": ["API","MCP"],
  "importance": 0.9,
  "saved_at": "2025-08-10T12:34:56Z",
  "text_hash": "sha256-..."  // オプション（原文はサーバに残さない）
}
```

検索結果アイテム例：

```json
{
  "summary": "要点：/memo/save が保存エンドポイントです。",
  "metadata": { ... },
  "distance": 0.123
}
```

---

# 設計方針（重要点）

* **プライバシー優先**：原文はサーバに残さない。必要なら `text_hash`（照合用、非復元）だけ保持。
* **シンプルなサーバ責務**：テキスト生成はクライアント側に任せ、サーバは埋め込み生成・Chroma 登録・検索に特化。
* **長文対応**：`MAX_CHUNK_CHARS` を定め、埋め込み対象が長い場合はチャンク化して複数ドキュメントとして登録。
* **同期処理の扱い**：`SentenceTransformer` と Chroma の多くメソッドは同期的なため、FastAPI 内では threadpool で実行して非ブロッキング化する。
* **Factory 形式**：`create_app(no_auth=False, additional_modules=None)` により認証のオン/オフとモジュール追加を起動時に設定可能。

---

# 環境変数 / 設定（主なもの）

* `CHROMA_PATH` (default `./chroma_db`)
* `EMBED_MODEL` (default `cl-nagoya/ruri-v3-30m`)
* `DEVICE` (`cpu`/`cuda`)
* `MAX_CHUNK_CHARS` (default `2000`)
* `N_RESULTS_DEFAULT` (default `5`)
* `EMBED_THREAD_WORKERS` (default `2`)
* `API_KEY`（optional、`create_app` の認証に利用）

---

# セキュリティ / プライバシー

* `API_KEY` + `Depends(get_api_key)` による簡易認証をサポート（Factory の `no_auth` で無効化可）。
* ログに原文を出力しない（metadata のみログ）。
* 必要に応じて OAuth2/JWT への移行を推奨。
* 原文を保存しないため、監査要件で原文保管が必要な場合は別途方針を確定する。

---

# 運用上の注意

* **要約（summary）をクライアント側で作ることを推奨**：検索精度と匿名性が向上する。
* **重複検出**：保存時に近傍検索で類似度閾値を超える既存があればマージ/スキップするオプションを検討。
* **バックアップ**：Chroma 永続ディレクトリのバックアップを用意（データの永続性）。
* **モデルサイズ／起動時間**：SentenceTransformer のロードや依存インストールが時間/容量を使うため Docker イメージ設計に注意。

---

# 実行手順（簡易）

1. 必要パッケージをインストール: `pip install -r requirements.txt`
2. 環境変数を設定（`CHROMA_PATH` や `EMBED_MODEL`、`API_KEY` など）
3. アプリ起動: `uvicorn app.factory:create_app --reload`（factory を適切に呼ぶコマンドに適合させる）
4. Swagger: `http://127.0.0.1:8000/docs`、MCP: `http://127.0.0.1:8000/mcp`

（運用では Docker Compose で Chroma データ用ボリュームをマウントすることを推奨）

---

# 優先タスク（開発順）

1. `routers/rag.py` と Pydantic スキーマ実装（operation\_id を明示）
2. `services/memo_service.py`（raw 非保存版）実装：チャンク化・埋め込み・Chroma 登録・検索（distance を返す）
3. Factory (`create_app`) によるルータ登録と `FastApiMCP.mount()` の確認
4. `GET /healthcheck` 実装（Chroma 接続・モデルロードチェック含む）
5. ユニット & 統合テスト（save/search/get/delete/healthcheck）
6. README, Docker Compose, テスト CI の整備

---

# 参考実装スニペット（要旨）

* Factory（あなた提示の `create_app`）を起点に使用。
* Router の例（骨子）:

```python
@router.post("/memo/save", operation_id="save_memo")
async def save_memo(req: SaveReq):
    return await memo_svc.save_memo(req.session_id, req.text, req.summary, req.keywords, req.importance)
```

* MemoService の特徴:

  * `embed_source = summary if summary else text`
  * `chunks = chunk_text(embed_source, MAX_CHUNK_CHARS)`
  * `embeddings = await run_in_threadpool(embedder.encode, chunks)`
  * `collection.add(ids, documents=chunks, metadatas=..., embeddings=embeddings)`

---
