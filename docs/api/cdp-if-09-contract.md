# CDP IF-09 契約案 — 確定 PDF の後処理ジョブ（Civil-Docs-Platform → CivilPDF-DX）

- 状態: **PROPOSED（未実装）**。実装は `status: planned`。CivilPDF-DX 側にこの API はまだ存在しない。
- 決定: [ADR-0006](../architecture/ADR-0006-cross-repo-integration.md) D-2 / D-5
- 参照（CDP 側の要件）: `Civil-Docs-Platform` 要件定義書 IF-09（確定 PDF の PDF/A 化・電子納品処理の依頼）
- マニフェスト: `infra/integration/system.json` の `civilpdf.pdf-postprocess`

> ⚠️ 本書は**提案**であり、CDP 側の合意と受入テストが完了するまで実装しない。
> 「実装済み」と読める記述を追加しないこと（ADR-0006 D-5）。

## 1. 目的

CDP で確定した PDF を CivilPDF-DX に渡し、次の後処理を非同期で依頼する。

- `pdfa`: PDF/A 化
- `electronic-delivery`: 国交省 CALS/EC 準拠の電子納品パッケージ（INDEX.XML 含む）生成

重い処理を同期 HTTP で行わない。CDP はジョブ ID を受け取り、ポーリングまたは署名付きコールバックで完了を知る。

## 2. 認証

- 人間ユーザーの JWT は使わない。**サービス間 HMAC** を使う。
- 署名・ヘッダ・正規化文字列の正本は [Integration API](integration-api.md) §2 とする
  （`/api/v1/integration/ping` と同じ HMAC v1。system_id も署名対象、timestamp は Unix epoch 秒のみ、
  許容 skew ±300 秒、nonce 再利用は **401**。共有秘密と共有 Redis の両方が必須）。
- 共有秘密は各環境の `~/.config/<repo>/<env>.env`（0600）に置き、リポジトリへ置かない。

## 3. エンドポイント（予定）

### 3.1 ジョブ作成

`POST /api/v1/integration/pdf-jobs`

ヘッダ: `Idempotency-Key: <UUID>`（必須。同一キーの再送は同じジョブを返す）

```json
{
  "source": {
    "systemId": "civil-docs-platform",
    "documentId": "cdp-doc-0001",
    "revisionId": "cdp-rev-0003",
    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  },
  "operations": ["pdfa", "electronic-delivery"],
  "delivery": {
    "projectCode": "2026-0142",
    "documentType": "図面",
    "callbackUrl": "https://cdp.example/api/integration/pdf-jobs/callback"
  },
  "requestedAt": "2026-10-17T07:00:00Z"
}
```

応答 `202 Accepted`:

```json
{
  "jobId": "cpdf-job-0001",
  "status": "queued",
  "operations": ["pdfa", "electronic-delivery"],
  "createdAt": "2026-10-17T07:00:01Z",
  "pollUrl": "/api/v1/integration/pdf-jobs/cpdf-job-0001"
}
```

### 3.2 状態取得

`GET /api/v1/integration/pdf-jobs/{jobId}`

```json
{
  "jobId": "cpdf-job-0001",
  "status": "succeeded",
  "sourceSha256": "e3b0c44...",
  "outputs": [
    {"kind": "pdfa", "sha256": "...", "sizeBytes": 123456},
    {"kind": "electronic-delivery", "sha256": "...", "sizeBytes": 2345678}
  ],
  "failure": null,
  "updatedAt": "2026-10-17T07:05:00Z"
}
```

`status` は `queued` / `running` / `succeeded` / `failed` / `cancelled` のいずれか。
`failed` のときだけ `failure: {code, message}` を持つ。

## 4. エラー

| HTTP | code | 意味 |
| --- | --- | --- |
| 400 | `invalid_request` | 必須項目欠落・`operations` 空 |
| 401 | `invalid_signature` | HMAC 不一致 |
| 409 | `idempotency_conflict` | 同一 `Idempotency-Key` で本文が異なる |
| 413 | `payload_too_large` | `MAX_FILE_SIZE_MB` 超過 |
| 422 | `unsupported_operation` | 未知の `operations` |
| 503 | `ai_disabled` | 管理者 stop switch 等で後処理が止まっている |

## 5. 非機能要件

- **冪等**: `Idempotency-Key` と `source.sha256` の組で一意。再送は副作用なし。
- **監査**: 作成・状態遷移・成果物 SHA-256 を既存の監査ハッシュチェーンに記録する。
- **保持**: 電子帳簿保存法 7 年保持の対象。ジョブと成果物の削除は保持ポリシーに従う。
- **分離**: CDP から見えるのは自システムのジョブのみ。他システムのジョブ ID を指定しても 404。
- **タイムアウト**: CDP 側のポーリングは指数バックオフ（5s→300s）。コールバックは 3 回まで再試行。

## 6. 受入テスト（実装時に追加する）

1. 正常系: 作成 → ポーリング → `succeeded`、成果物 SHA-256 が入力と整合
2. 冪等: 同一キー再送で同一 `jobId`、`409` は本文差し替え時のみ
3. 認証: 署名不正・timestamp 古い・nonce 再利用で 401/409
4. 越権: 他システムのジョブは 404
5. 障害: 後処理失敗時に `failed` と `failure.code` が返り、監査に残る

## 7. 未決事項

- CDP 側 outbox の再試行間隔と最大回数
- コールバックを受けない運用（ポーリングのみ）を許容するか
- PDF/A 変換エンジンの選定（Ghostscript / pikepdf 等）
