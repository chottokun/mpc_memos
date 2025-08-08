# プロジェクト概要

このリポジトリは、**FastAPI + fastapi\_mcp + ChromaDB + SentenceTransformer (デフォルト: `cl-nagoya/ruri-v3-30m`) + Redis** を組み合わせた MCP サーバの実装サンプルです。
クライアント（LM/フロント）が送った会話・メモ（`text`）と任意の `summary`／`keywords` を受け取り、**summary があれば summary を、無ければ raw (`text`) を埋め込み対象**として ChromaDB に登録します。raw は短期 TTL（デフォルト 24 時間）で Redis に保存され、検索時は Chroma の類似検索結果に対して raw（存在すれば）を付与して返却します。

この Agent.md は実装者（開発者・運用者）向けに設計方針、API、動作フロー、運用上の注意点、優先タスクを整理したドキュメントです。

---

# 目的

* クライアント生成の要点（summary）を任意としつつ、**サーバ側は埋め込み生成と保存／検索に専念**するシンプルで拡張可能な設計を示す。
* MCP（fastapi\_mcp）を通じてツールを公開し、エージェントから直接利用できるようにする。
* ChromaDB によるベクトルストア管理と Redis による raw（短期）保持の組合せで、知恵袋的検索（RAG）を提供する。

---

# 主要特徴（まとめ）

* `summary` は **任意**。ある場合は summary を埋め込み、ない場合は `text`（raw）を埋め込み対象とする。
* raw は Redis に TTL で保存（デフォルト 24h）。summary（もしくは raw を埋め込みした Chroma ドキュメント）は長期保持（Chroma に残る）を基本とする。
* 長いテキストはチャンク分割して複数ドキュメントとして保存（`MAX_CHUNK_CHARS` による切分）。
* 重複対策（オプション）として、保存時に類似度検出→マージ/スキップを実装可能。
* operation\_id を明示した FastAPI エンドポイントで MCP に公開。

---

# 制約

* FastAPI + fastapi\_mcp を使用する。
* ChromaDB は `PersistentClient`（ローカル永続化）で利用する。
* 埋め込み生成は `sentence-transformers` 経由（デフォルト CPU）。GPU 利用は設定で切替可。
* Redis は raw 一時保存のバックエンド（非必須だが推奨）。
* 外部ライブラリは pip インストール可能なものに限定。
* 認証は `HTTPBearer` によるトークン式をサポート（オン／オフ可能）。
* Docker / docker-compose での動作を想定した構成を提供。

---

# アーキテクチャ（概要）

```
クライアント (LM/フロント)
   └─ POST /memo/save  (text + optional summary)
         ↓
     FastAPI (/mcp)
         ↓
     MemoService
       ├─ Redis (raw, TTL)
       └─ ChromaDB (summary/raw embeddings, metadata)
         ↑
   GET /memo/search  ←─ embedding(query) ← MemoService
```

---

# 設定（環境変数）

* `REDIS_URL` (default: `redis://localhost:6379/0`)
* `CHROMA_PATH` (default: `./chroma_db`) — Chroma 永続化パス
* `EMBED_MODEL` (default: `cl-nagoya/ruri-v3-30m`)
* `DEVICE` (`cpu`/`cuda`)
* `MEMO_TTL_SECONDS` (default: `86400`) — raw の TTL
* `MAX_CHUNK_CHARS` (default: `2000`) — 埋め込み対象を分割する閾値
* `N_RESULTS_DEFAULT` (default: `5`) — 検索時のデフォルト件数

---

# データモデル

**Redis: raw（hash）** — key: `memo:{memo_id}`

```json
{
  "memo_id": "<uuid>",
  "session_id": "<string>",
  "text": "<原文>",
  "saved_at": "<ISO8601>",
  "keywords": ["..."],
  "importance": 0.8
}
```

**Chroma: document / metadata / embedding**

* `documents` は埋め込み対象テキスト（summary または raw chunk）
* `metadatas` には以下を含める:

```json
{
  "memo_id": "<uuid>",
  "session_id": "<string>",
  "chunk_index": 0,
  "is_summary": true|false,
  "keywords": [...],
  "importance": 0.0,
  "saved_at": "<ISO8601>"
}
```

---

# API（operation\_id を明示したエンドポイント）

> すべてのエンドポイントは `fastapi_mcp` を通じて `/mcp` に登録され、エージェントから検出可能。

## 1. `POST /memo/save` — `operation_id="save_memo"`

**用途**: raw (`text`) と任意の `summary` を送信して保存する。
**Input (JSON)**:

```json
{
  "session_id": "sess-1",
  "text": "保存したい原文（必須）",
  "summary": "任意の要約（nullable）",
  "keywords": ["任意"],
  "importance": 0.8
}
```

**挙動**:

1. `memo_id` を生成、`saved_at` を付与。
2. Redis に `memo:{memo_id}` として raw を保存し TTL を設定。
3. `embed_source = summary if summary else text`。`embed_source` を `MAX_CHUNK_CHARS` に基づいてチャンク化（必要時）。
4. 各チャンクの埋め込みを生成（`SentenceTransformer`）し、Chroma に `ids`, `documents`, `metadatas`, `embeddings` を追加。
   **Return**:

```json
{ "memo_id": "<uuid>", "saved_at": "<ISO8601>", "chroma_ids": ["memo_summary:<id>", ...], "used_summary": true|false }
```

## 2. `GET /memo/search` — `operation_id="query_memo"`

**用途**: クエリを埋め込み化して Chroma で類似検索し、上位 `n_results` を返す（default 5）。
**Params**: `query` (必須), `n_results` (任意)
**挙動**:

1. クエリを embedding 生成。
2. Chroma に `query_embeddings` で検索。
3. 結果の `metadatas` から `memo_id` を取り、Redis から raw を取得（存在すれば付与）。
4. 各結果には `summary`（Chroma に登録された document）, `metadata`, `distance`（score）および `raw`（nullable）を返却。
   **Return**:

```json
{
  "query": "〜",
  "results": [
    {
      "summary": "...",
      "metadata": {...},
      "distance": 0.12,
      "raw": { "memo_id": "...", "text": "...", ... }   // null の可能性あり
    },
    ...
  ]
}
```

## 3. `GET /memo/get` — `operation_id="get_memo"`

**用途**: `memo_id` で Redis に保存された raw を取得（TTL 切れなら 404）。
**Params**: `memo_id`
**Return**: raw hash

## 4. `POST /memo/delete` — `operation_id="delete_memo"`

**用途**: `memo_id` で Redis raw と Chroma の該当ドキュメント（`memo_summary:<memo_id>` とチャンク）を削除。
**Input**: `{ "memo_id": "<uuid>" }`
**Return**: `{ "deleted": true }`

## 5. `POST /memo/clear_expired` — `operation_id="clear_expired"`（管理用）

**用途**: SQLite 等のバックアップストアを使う場合、期限切れの後処理を実行するための管理 API（Redis を利用している限り自動 TTL に依存するため任意）。

---

# 動作フロー（例）

## 保存フロー（summary 提供あり）

1. クライアントが `POST /memo/save` に `text + summary + keywords` を送る。
2. サーバは Redis に raw を保存（TTL）。
3. サーバは summary の埋め込みを作成して Chroma に登録（metadata に memo\_id を含む）。
4. サーバは `memo_id` を返す。

## 保存フロー（summary 無し）

1. クライアントが `POST /memo/save` に `text` のみを送る。
2. サーバは Redis に raw を保存（TTL）。
3. サーバは `text` を埋め込み対象にして（長ければチャンク化して）Chroma に登録。
4. `memo_id` を返す。

## 検索フロー

1. クライアントが `GET /memo/search?query=...&n_results=5` を呼ぶ。
2. サーバはクエリの埋め込みを作成 → Chroma に問い合わせ。
3. Chroma が返した summary/metadata/distance を組み立て、各 `memo_id` について Redis から raw を付与（無ければ `null`）。
4. 結果を返す（JSON）。

---

# 実装ファイル（想定）

* `main.py` — FastAPI アプリ、fastapi\_mcp マウント、エンドポイント定義、簡易認証（HTTPBearer）
* `memo_service.py` — MemoService の実装（Redis 接続、Chroma 接続、埋め込み生成、分割ロジック、保存・検索・削除ロジック）
* `requirements.txt` — 依存パッケージ
* `Dockerfile` — API コンテナの定義
* `docker-compose.yml` — redis + api（Chroma は API 内の永続フォルダに保存）
* `tests/` — ユニットテスト（save/get/search/delete など、TDD を推奨）
* `README.md` — 実行手順（Agent.md を元に生成）

---

# 優先タスク（実装オーダー）

1. **save\_memo: summary 任意対応実装**（チャンク/埋め込みの分岐含む） — 既実装済みの `memo_service.save_memo` を summary optional にすること（最優先）。
2. **search に distance（スコア）を返す** — Chroma の `distances` をレスポンスに含める。
3. **/healthcheck エンドポイント追加** — `GET /healthcheck` : 依存サービス（Redis, Chroma）に接続できるか確認する簡易チェック。
4. **TDD の整備** — `tests/` に save/get/search/delete のテストケースを作成（mock Redis/Chroma or 集約テスト）。
5. **Docker Compose & docs** — `docker-compose.yml` と `README.md`（起動手順、env 設定）を用意する。

---

# 運用上の注意事項・ベストプラクティス

* **長文（raw）の扱い**: モデルの入力長制限に注意。`text` が長い場合はサーバ側で `MAX_CHUNK_CHARS` によるチャンク化を行う（チャンクごとに Chroma ドキュメントを作る）。検索時は関連チャンクを結合してコンテキストを作るか、複数チャンクの上位を渡す。
* **summary の推奨**: クライアント側で summary を生成する運用（推奨）。品質を上げるためにクライアント用の要約プロンプトテンプレートを配布する。
* **重複検出**: 大量の同趣旨メモが発生する場合、保存時に Chroma で近傍検索して高類似度（例 0.95）であればマージする戦略を検討する。
* **セキュリティ**: 本番では `HTTPBearer` の代わりに OAuth2 / JWT / API Gateway を導入し、監査ログを残す。
* **TTL ポリシー**: raw は短期（24h）で良いが、プロダクションでは法令・コンプライアンスに応じた保持ポリシーを策定する。
* **バックアップ**: Chroma のデータと Redis の永続化設定（RDB/AOF）を運用ポリシーに沿って設定する。

