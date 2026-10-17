# CivilPDF-DX Integration API（カタログとサービス間認証）

- 状態: **実装済み**（`civilpdf.integration-discovery`）。ジョブ API は [CDP IF-09 契約案](cdp-if-09-contract.md) のまま **planned**。
- 決定: [ADR-0006](../architecture/ADR-0006-cross-repo-integration.md) D-2
- マニフェスト: `infra/integration/system.json`
- 実装: `src/console/backend/api/integration.py` / `src/console/backend/services/service_auth.py`

## 1. 提供エンドポイント

| メソッド | パス | 認証 | 用途 |
| --- | --- | --- | --- |
| GET | `/api/v1/integration/catalog` | なし（公開・秘密を含まない） | システム識別・実装済み IF・登録状態の discover |
| GET | `/api/v1/integration/ping` | HMAC | 署名実装の疎通確認 |

### catalog の例

```json
{
  "systemId": "civilpdf",
  "displayName": "CivilPDF-DX",
  "repository": "mirai-construction-dx/CivilPDF-DX",
  "version": "0.10.0",
  "environment": "staging",
  "interfaces": {
    "provides": [
      {"id": "civilpdf.integration-discovery", "protocol": "http", "status": "implemented"},
      {"id": "civilpdf.pdf-postprocess", "protocol": "http", "status": "planned"},
      {"id": "civilpdf.mcp", "protocol": "mcp", "status": "not-implemented"}
    ],
    "consumes": [
      {"id": "core.contracts", "protocol": "vendored-contracts", "status": "not-integrated"},
      {"id": "cdp.cde-registration", "protocol": "http", "status": "not-implemented"}
    ]
  },
  "registration": {"platformInfra": "registered", "harnessCore": "pending", "civilDocsPlatform": "pending"},
  "authentication": {
    "scheme": "hmac-sha256",
    "headers": ["X-CivilPDF-System", "X-CivilPDF-Timestamp", "X-CivilPDF-Nonce", "X-CivilPDF-Signature"],
    "clockSkewSeconds": 300,
    "contract": "docs/api/integration-api.md"
  }
}
```

> `catalog` は `infra/integration/system.json` と一致することを
> `tests/console/test_integration_api.py` が検証する。片方だけ更新すると CI が落ちる。

## 2. 署名（HMAC-SHA256）

### 2.1 ヘッダ

| ヘッダ | 値 |
| --- | --- |
| `X-CivilPDF-System` | 呼び出し元の `system_id`（例 `civil-docs-platform`） |
| `X-CivilPDF-Timestamp` | Unix epoch 秒（RFC 3339 も受理） |
| `X-CivilPDF-Nonce` | 128bit 以上のランダム hex。時計ずれ許容時間内で再利用不可 |
| `X-CivilPDF-Signature` | 下記の hex 署名（小文字） |

### 2.2 正規化文字列

UTF-8・LF 区切り・末尾改行なし:

```
METHOD
PATH
TIMESTAMP
NONCE
SHA256_HEX(BODY)
```

- `PATH` は `request.url.path`（クエリ文字列は含めない。パラメータは本文へ）
- `BODY` は生のリクエスト本文（GET は空）
- 署名 = `hex(HMAC-SHA256(secret, 正規化文字列))`

### 2.3 検証仕様

- 共有秘密は `INTEGRATION_HMAC_SECRETS`（JSON: `{"<system_id>":"<hex>"}`）で設定する。
  **未設定なら統合 API 全体が 503（fail closed）**。空文字を設定しないこと。
- 時計ずれは `INTEGRATION_CLOCK_SKEW_SECONDS`（既定 300 秒）を超えると 401。
- nonce の再利用は 401。
- 未知の `system_id`、署名不一致、ヘッダ欠落はすべて 401。

### 2.4 参照実装（Python）

```python
import hashlib, hmac, time, uuid

def sign(secret: str, method: str, path: str, body: bytes = b"") -> dict[str, str]:
    ts = str(int(time.time()))
    nonce = uuid.uuid4().hex
    canonical = f"{method}\n{path}\n{ts}\n{nonce}\n{hashlib.sha256(body).hexdigest()}"
    signature = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    return {
        "X-CivilPDF-System": "civil-docs-platform",
        "X-CivilPDF-Timestamp": ts,
        "X-CivilPDF-Nonce": nonce,
        "X-CivilPDF-Signature": signature,
    }
```

疎通確認:

```bash
curl -s http://127.0.0.1:18971/api/v1/integration/catalog | python3 -m json.tool
# 署名付き /ping は上記 sign() のヘッダを付けて呼ぶ
```

## 3. 既知の制限

- nonce の再生防止キャッシュは**プロセス内**である。uvicorn を複数 worker で動かすと、
  別 worker に届いた再生リクエストは通る可能性がある。将来のジョブ API では
  `Idempotency-Key` と DB の nonce 表で副作用を二重実行しない設計にする。
- レート制限はアプリ共通のミドルウェアに従う（サービス間呼び出し専用の別枠は未設定）。

## 4. 受入テスト

`tests/console/test_integration_api.py`:

- catalog がマニフェストと一致する
- 未設定時 503 / ヘッダ欠落・未知システム・改ざん・期限切れ・nonce 再利用・パス束縛が 401
- 正しい署名で 200（`caller` が返る）
