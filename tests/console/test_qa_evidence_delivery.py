"""QA: 証跡（タイムスタンプ・監査ログ）／電子納品／保存期限と削除／AI 補助の品質テスト.

方針:
- 仕様（docs/requirements.md・README.md）と実装が食い違う箇所は、期待値を実装に
  合わせて緩めず、仕様どおりの期待値で ``xfail(strict=True)`` とし reason に
  DEFECT-ID・仕様ID・現状・実装根拠を書く。
- 仕様に Phase 2 等の明記があり、予定どおり未実装のものは通常テストで現状挙動を
  記録し、docstring に「既知の未実装」と書く。
- 法令適合（電子帳簿保存法・e-文書法など）の判定はしない。
- 外部接続は行わない: Anthropic は ``api.ai._get_anthropic_client`` をスタブ、
  TSA は ``TSA_URL`` を空にしてローカル HMAC 経路のみ。
- 時刻依存の処理は対象モジュールの ``datetime`` を固定値クラスに差し替え、
  実行日時に依存しないようにする。
"""

import csv
import hashlib
import io
import json
import re
import zipfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from models.audit_log import AuditLog
from models.document import Document, DocumentStatus, DocumentType
from models.user import Project, User

API = "/api/v1"
PDF_BYTES = b"%PDF-1.4\n% civilpdf qa synthetic document\n1 0 obj<<>>endobj\n%%EOF\n"


# ─── helpers ────────────────────────────────────────────────────────────────


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@contextmanager
def _frozen_now(module_path: str, fixed: datetime):
    """Replace ``datetime`` inside *module_path* so ``datetime.now()`` is fixed."""

    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: D401 - mimic datetime.now
            return fixed if tz is None else fixed.astimezone(tz)

    with patch(f"{module_path}.datetime", _FixedDateTime):
        yield


def _make_project(db, code: str = "QA-ED-001", name: str = "QA 検証工事") -> Project:
    project = Project(name=name, code=code, description="QA synthetic project")
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _add_member(db, project_id: str, user_id: str) -> None:
    project = db.query(Project).filter(Project.id == project_id).first()
    user = db.query(User).filter(User.id == user_id).first()
    project.members.append(user)
    db.commit()


def _upload(
    client: TestClient,
    token: str,
    project_id: str,
    *,
    title: str = "QA 図面",
    content: bytes = PDF_BYTES,
    document_type: str = "drawing",
    filename: str = "qa.pdf",
) -> dict:
    resp = client.post(
        f"{API}/documents/",
        headers=_hdr(token),
        data={"project_id": project_id, "title": title, "document_type": document_type},
        files={"file": (filename, content, "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _chain_logs(db) -> list[AuditLog]:
    db.expire_all()
    return (
        db.query(AuditLog)
        .filter(AuditLog.sequence_number.isnot(None))
        .order_by(AuditLog.sequence_number.asc())
        .all()
    )


def _make_doc(
    db,
    *,
    project_id: str,
    owner_id: str,
    document_type: DocumentType = DocumentType.OTHER,
    file_path: str | None = None,
    deletion_requested_at: datetime | None = None,
    retention_expires_at: datetime | None = None,
    created_at: datetime | None = None,
) -> Document:
    doc = Document(
        title="QA synthetic",
        document_type=document_type,
        status=DocumentStatus.DRAFT,
        filename="qa.pdf",
        file_path=file_path,
        file_size=len(PDF_BYTES),
        project_id=project_id,
        owner_id=owner_id,
        deletion_requested_at=deletion_requested_at,
        retention_expires_at=retention_expires_at,
        tags=[],
        extra_data={},
    )
    if created_at is not None:
        doc.created_at = created_at
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@pytest.fixture
def local_tsa_only(monkeypatch):
    """RFC 3161 TSA を使わずローカル HMAC 経路のみを通す（外部接続禁止）."""
    monkeypatch.setenv("TSA_URL", "")
    monkeypatch.setattr("services.timestamp_service.TSA_URL", "")


# ═══════════════════════════════════════════════════════════════════════════
# A. 証跡（タイムスタンプ／監査ログ）
# ═══════════════════════════════════════════════════════════════════════════


class TestTimestampReproducibility:
    def test_same_bytes_give_identical_sha256_and_local_hmac_token_type(
        self, client, admin_token, db_session, local_tsa_only
    ):
        """仕様: README.md 行103（e-文書法: 電子タイムスタンプによる真正性証明）.

        期待: 同一バイト列なら file_hash は決定的に同じ SHA-256。POST
        /documents/{id}/timestamp を2回実行しても file_hash は不変。
        記録: token_type は ``local_hmac``、tsa_url は空（RFC 3161 トークンでは
        ない。services/timestamp_service.py:44-45, 119-123）。
        """
        project = _make_project(db_session)
        d1 = _upload(client, admin_token, project.id, title="A")
        d2 = _upload(client, admin_token, project.id, title="B")
        expected = hashlib.sha256(PDF_BYTES).hexdigest()

        r1 = client.post(
            f"{API}/documents/{d1['id']}/timestamp", headers=_hdr(admin_token)
        )
        r1b = client.post(
            f"{API}/documents/{d1['id']}/timestamp", headers=_hdr(admin_token)
        )
        r2 = client.post(
            f"{API}/documents/{d2['id']}/timestamp", headers=_hdr(admin_token)
        )
        assert r1.status_code == r1b.status_code == r2.status_code == 200
        assert r1.json()["file_hash"] == r1b.json()["file_hash"] == expected
        assert r2.json()["file_hash"] == expected
        for body in (r1.json(), r1b.json(), r2.json()):
            assert body["token_type"] == "local_hmac"  # NOT rfc3161
            assert body["tsa_url"] == ""
            assert body["token_present"] is True

        v = client.get(
            f"{API}/documents/{d1['id']}/timestamp/verify", headers=_hdr(admin_token)
        )
        assert v.status_code == 200
        assert v.json()["valid"] is True
        assert v.json()["file_hash"] == expected

    def test_local_token_is_deterministic_only_when_time_is_fixed(self, local_tsa_only):
        """仕様: README.md 行103 / 再現性の記録.

        期待（記録）: ローカル HMAC トークンはペイロードに生成時刻を含むため、
        時刻を固定すれば同一入力で token_b64 がバイト一致し、時刻が異なれば
        file_hash は同じでも token_b64 は変わる（時刻依存値）。
        根拠: services/timestamp_service.py:47-56。
        """
        from services import timestamp_service as ts

        t0 = datetime(2001, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        with _frozen_now("services.timestamp_service", t0):
            a = ts.generate_timestamp(PDF_BYTES, "qa.pdf")
            b = ts.generate_timestamp(PDF_BYTES, "qa.pdf")
        with _frozen_now("services.timestamp_service", t0 + timedelta(seconds=1)):
            c = ts.generate_timestamp(PDF_BYTES, "qa.pdf")

        assert a["token_type"] == b["token_type"] == c["token_type"] == "local_hmac"
        assert a["file_hash"] == b["file_hash"] == c["file_hash"]
        assert a["token_b64"] == b["token_b64"]
        assert a["verified_at"] == "2001-01-01T00:00:00+00:00"
        assert c["token_b64"] != a["token_b64"]  # 時刻依存
        assert ts.verify_file_against_timestamp(
            PDF_BYTES, a["file_hash"], a["token_b64"]
        )

    def test_one_byte_change_fails_verification(
        self, client, admin_token, db_session, local_tsa_only
    ):
        """仕様: README.md 行103（真正性証明）.

        期待: 保存ファイルを1バイト改変すると verify は valid=false。
        トークンの署名を1文字改変しても valid=false。
        """
        project = _make_project(db_session)
        d = _upload(client, admin_token, project.id)
        doc = db_session.query(Document).filter(Document.id == d["id"]).first()
        path = Path(doc.file_path)
        original = path.read_bytes()
        tampered = bytearray(original)
        tampered[-2] ^= 0x01
        path.write_bytes(bytes(tampered))

        v = client.get(
            f"{API}/documents/{d['id']}/timestamp/verify", headers=_hdr(admin_token)
        )
        assert v.status_code == 200
        assert v.json()["valid"] is False

        # 署名改変
        path.write_bytes(original)
        import base64

        token = json.loads(base64.b64decode(doc.timestamp_token))
        token["signature"] = ("0" if token["signature"][0] != "0" else "1") + token[
            "signature"
        ][1:]
        doc.timestamp_token = base64.b64encode(json.dumps(token).encode()).decode()
        db_session.commit()
        v2 = client.get(
            f"{API}/documents/{d['id']}/timestamp/verify", headers=_hdr(admin_token)
        )
        assert v2.json()["valid"] is False

    def test_restamp_after_tamper_keeps_old_hash_in_chain(
        self, client, admin_token, db_session, local_tsa_only
    ):
        """仕様: requirements.md v1.1.0 決定 D-1（再付与は許可し、旧ハッシュを監査ログに残す）.

        期待: ファイル改変後に POST /timestamp を再実行すると、Document の
        タイムスタンプ欄（単一）は上書きされ verify は valid=true に戻る（再付与は許可）。
        ただし改変前のハッシュは監査チェーンに残る:
        - document.uploaded の detail.file_hash が初回ハッシュ
        - document.timestamped の detail.previous_file_hash が上書き前のハッシュで、
          hash_changed=true
        さらに、この記録を含めて監査チェーンの検証が valid のまま。
        """
        project = _make_project(db_session)
        d = _upload(client, admin_token, project.id)
        original_hash = hashlib.sha256(PDF_BYTES).hexdigest()
        doc = db_session.query(Document).filter(Document.id == d["id"]).first()
        Path(doc.file_path).write_bytes(PDF_BYTES + b"% tampered\n")

        assert (
            client.get(
                f"{API}/documents/{d['id']}/timestamp/verify", headers=_hdr(admin_token)
            ).json()["valid"]
            is False
        )
        r = client.post(
            f"{API}/documents/{d['id']}/timestamp", headers=_hdr(admin_token)
        )
        assert r.status_code == 200
        assert r.json()["file_hash"] != original_hash
        assert (
            client.get(
                f"{API}/documents/{d['id']}/timestamp/verify", headers=_hdr(admin_token)
            ).json()["valid"]
            is True
        )
        logs = _chain_logs(db_session)
        uploaded = [
            json.loads(x.detail)
            for x in logs
            if x.action == "document.uploaded" and x.resource_id == d["id"]
        ]
        assert [u["file_hash"] for u in uploaded] == [original_hash]
        stamped = [
            json.loads(x.detail)
            for x in logs
            if x.action == "document.timestamped" and x.resource_id == d["id"]
        ]
        assert len(stamped) == 1
        assert stamped[0]["previous_file_hash"] == original_hash
        assert stamped[0]["file_hash"] == r.json()["file_hash"]
        assert stamped[0]["hash_changed"] is True
        assert stamped[0]["previous_verified_at"]
        verify = client.get(f"{API}/audit-logs/verify", headers=_hdr(admin_token))
        assert verify.json()["chain_valid"] is True

    def test_restamp_without_change_is_not_flagged(
        self, client, admin_token, db_session, local_tsa_only
    ):
        """決定 D-1: 内容が変わっていない再付与は hash_changed=false で記録する."""
        project = _make_project(db_session)
        d = _upload(client, admin_token, project.id)
        original_hash = hashlib.sha256(PDF_BYTES).hexdigest()
        r = client.post(
            f"{API}/documents/{d['id']}/timestamp", headers=_hdr(admin_token)
        )
        assert r.status_code == 200
        stamped = [
            json.loads(x.detail)
            for x in _chain_logs(db_session)
            if x.action == "document.timestamped" and x.resource_id == d["id"]
        ]
        assert stamped[-1]["previous_file_hash"] == original_hash
        assert stamped[-1]["file_hash"] == original_hash
        assert stamped[-1]["hash_changed"] is False


class TestAuditChain:
    def test_chain_valid_after_operations_and_detail_tamper_is_detected(
        self, client, admin_token, db_session, local_tsa_only
    ):
        """仕様: WEB-AUDIT-006（行298: 追記専用 + SHA-256 ハッシュチェーン）.

        期待: 複数操作（ログイン・アップロード・更新・タイムスタンプ・削除）後に
        GET /audit-logs/verify は chain_valid=true。DB 上で1レコードの detail を
        書き換えると chain_valid=false かつ first_broken_sequence が当該番号。
        """
        project = _make_project(db_session)
        d = _upload(client, admin_token, project.id)
        client.patch(
            f"{API}/documents/{d['id']}",
            headers=_hdr(admin_token),
            json={"title": "QA2"},
        )
        client.post(f"{API}/documents/{d['id']}/timestamp", headers=_hdr(admin_token))
        client.delete(f"{API}/documents/{d['id']}", headers=_hdr(admin_token))

        logs = _chain_logs(db_session)
        assert len(logs) >= 5
        assert [x.sequence_number for x in logs] == list(range(1, len(logs) + 1))
        ok = client.get(f"{API}/audit-logs/verify", headers=_hdr(admin_token)).json()
        assert ok["chain_valid"] is True
        assert ok["records_checked"] == len(logs)

        victim = logs[2]
        victim.detail = (victim.detail or "") + " (tampered)"
        db_session.commit()
        ng = client.get(f"{API}/audit-logs/verify", headers=_hdr(admin_token)).json()
        assert ng["chain_valid"] is False
        assert ng["first_broken_sequence"] == victim.sequence_number

    def test_tamper_beyond_default_verify_window_is_detected(
        self, client, admin_token, db_session
    ):
        """仕様: WEB-AUDIT-006（行298）、エンドポイント説明「chain_valid=true の場合、
        ログが改ざんされていないことを確認できます」（api/audit_logs.py:176-177）.

        期待: 1002件のチェーンの末尾（1001件目以降）を改ざんしたら、既定の
        GET /audit-logs/verify は chain_valid=false を返す。limit 指定時は
        records_checked < total_records かつ complete=false で部分検証と分かる。
        修正済み: DEFECT-AUD-01（既定で全件をバッチ検証）。
        """
        from services.audit_chain_service import _compute_record_hash, _normalize_dt

        last = _chain_logs(db_session)[-1]  # admin_token のログイン記録
        prev_hash, seq = last.record_hash, last.sequence_number
        created = datetime(2001, 1, 1, tzinfo=timezone.utc)
        rows = []
        for i in range(seq + 1, 1003):
            detail = f"synthetic {i}"
            h = _compute_record_hash(
                prev_hash=prev_hash,
                sequence_number=i,
                user_id=None,
                action="qa.synthetic",
                resource_type="qa",
                resource_id=None,
                detail=detail,
                ip_address=None,
                created_at_iso=_normalize_dt(created),
            )
            rows.append(
                {
                    "id": f"qa-{i:05d}",
                    "action": "qa.synthetic",
                    "resource_type": "qa",
                    "detail": detail,
                    "created_at": created,
                    "sequence_number": i,
                    "prev_hash": prev_hash,
                    "record_hash": h,
                }
            )
            prev_hash = h
        db_session.bulk_insert_mappings(AuditLog, rows)
        db_session.commit()
        full = client.get(f"{API}/audit-logs/verify", headers=_hdr(admin_token)).json()
        assert full["chain_valid"] is True
        assert full["records_checked"] == full["total_records"] == 1002
        assert full["complete"] is True

        tail = db_session.query(AuditLog).filter(AuditLog.sequence_number == 1002).one()
        tail.detail = "tampered"
        db_session.commit()
        res = client.get(f"{API}/audit-logs/verify", headers=_hdr(admin_token)).json()
        assert res["chain_valid"] is False
        assert res["first_broken_sequence"] == 1002

        partial = client.get(
            f"{API}/audit-logs/verify",
            params={"limit": 1000},
            headers=_hdr(admin_token),
        ).json()
        # 部分検証: 先頭1000件に破損はないが、全件ではないことが明示される
        assert partial["chain_valid"] is True
        assert partial["records_checked"] == 1000
        assert partial["total_records"] == 1002
        assert partial["complete"] is False

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "DEFECT-AUD-02: 未決（ユーザー判断待ち） §5.4（行458）/WEB-AUDIT-006 削除の技術的禁止 — DB 上で末尾"
            "レコードを DELETE でき、チェーン検証も valid のまま（末尾切り詰め未検知）。"
            "DB トリガ/権限による禁止はマイグレーションに見当たらない 根拠: "
            "migrations/versions/b669f56cdac7_add_audit_logs_table.py:22-66, "
            "services/audit_chain_service.py:160-222（試験環境は SQLite）"
        ),
    )
    def test_deleting_tail_record_is_prevented_or_detected(
        self, client, admin_token, db_session
    ):
        """仕様: §5.4（行458: 追記専用、変更・削除を技術的に禁止）, WEB-AUDIT-006（行298）.

        期待: 監査ログ末尾レコードの DB 削除は拒否される、または検証で検知される。
        注: PostgreSQL 本番での DB 権限設定は資料で確認できず「未確認」。
        """
        project = _make_project(db_session)
        _upload(client, admin_token, project.id)
        tail = _chain_logs(db_session)[-1]
        deleted = True
        try:
            db_session.delete(tail)
            db_session.commit()
        except Exception:
            db_session.rollback()
            deleted = False
        res = client.get(f"{API}/audit-logs/verify", headers=_hdr(admin_token)).json()
        assert (not deleted) or res["chain_valid"] is False


class TestAuditApi:
    @pytest.mark.parametrize("method", ["put", "patch", "delete"])
    def test_collection_endpoint_rejects_modification_with_405(
        self, client, admin_token, method
    ):
        """仕様: AT-AUDIT-003（行725: 変更・削除しようとして HTTP 405/403）.

        期待: /audit-logs/ ・ /audit-logs/verify ・ /audit-logs/export.csv への
        PUT/PATCH/DELETE は 405（admin でも）。
        """
        for path in ("/audit-logs/", "/audit-logs/verify", "/audit-logs/export.csv"):
            resp = getattr(client, method)(f"{API}{path}", headers=_hdr(admin_token))
            assert resp.status_code in (403, 405), (path, resp.status_code)

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "DEFECT-AUD-03: 未決（ユーザー判断待ち） AT-AUDIT-003 個別ログ /audit-logs/{id} への PUT/PATCH/DELETE "
            "が 405/403 ではなく 404（ルート未定義）。改変自体は不可 根拠: "
            "api/audit_logs.py:33,79,171（{id} ルートなし）"
        ),
    )
    def test_item_endpoint_rejects_modification_with_405_or_403(
        self, client, admin_token, db_session
    ):
        """仕様: AT-AUDIT-003（行725）.

        期待: 既存ログ id を指定した PUT/PATCH/DELETE は 405 または 403 で、
        レコードは不変。
        """
        log = _chain_logs(db_session)[0]
        before = (log.detail, log.record_hash)
        statuses = []
        for method in ("put", "patch", "delete"):
            resp = getattr(client, method)(
                f"{API}/audit-logs/{log.id}",
                headers=_hdr(admin_token),
                **({} if method == "delete" else {"json": {"detail": "x"}}),
            )
            statuses.append(resp.status_code)
        db_session.expire_all()
        after = db_session.query(AuditLog).filter(AuditLog.id == log.id).one()
        assert (after.detail, after.record_hash) == before  # 改変されていない
        assert all(s in (403, 405) for s in statuses), statuses

    def test_login_success_is_recorded_with_user_and_ip(
        self, client, admin_user, db_session
    ):
        """仕様: AT-AUDIT-001（行723）, §5.4（行466 ip_address）.

        期待: ログイン成功で監査ログが記録され、操作者ID と IP が入る。
        記録: action 名は §5.4 の enum ``LOGIN`` ではなく ``auth.login_success``
        （api/auth.py:219-227）。命名差の扱いは人の判断事項。
        """
        resp = client.post(
            f"{API}/auth/token",
            data={"username": "admin@example.com", "password": "Admin1234!"},
        )
        assert resp.status_code == 200
        logs = [x for x in _chain_logs(db_session) if x.action == "auth.login_success"]
        assert len(logs) == 1
        assert logs[0].user_id == admin_user.id
        assert logs[0].ip_address == "testclient"  # TestClient の client.host

    def test_document_view_is_audited_with_user_and_ip(
        self, client, admin_token, admin_user, db_session
    ):
        """仕様: AT-AUDIT-002（requirements.md v1.1.0、2026-10-03 決定 D-3b: 閲覧は今すぐ記録）.

        期待: GET /documents/{id} が成功すると document.viewed が操作者・IP・
        文書 ID とともに改ざん検知チェーンに 1 件記録される。チェーンは valid。
        """
        project = _make_project(db_session)
        d = _upload(client, admin_token, project.id)
        n_before = len(_chain_logs(db_session))
        assert (
            client.get(
                f"{API}/documents/{d['id']}", headers=_hdr(admin_token)
            ).status_code
            == 200
        )
        logs = _chain_logs(db_session)
        assert len(logs) == n_before + 1
        viewed = logs[-1]
        assert viewed.action == "document.viewed"
        assert viewed.user_id == admin_user.id
        assert viewed.resource_type == "document"
        assert viewed.resource_id == d["id"]
        assert viewed.ip_address == "testclient"
        verify = client.get(f"{API}/audit-logs/verify", headers=_hdr(admin_token))
        assert verify.json()["chain_valid"] is True

    def test_denied_or_trashed_view_is_not_audited(
        self, client, admin_token, engineer_token, db_session
    ):
        """D-3b: 閲覧できなかった要求（他案件 404・ごみ箱 404）は document.viewed を残さない."""
        project = _make_project(db_session)
        d = _upload(client, admin_token, project.id)
        n_before = len(_chain_logs(db_session))
        denied = client.get(f"{API}/documents/{d['id']}", headers=_hdr(engineer_token))
        assert denied.status_code == 404
        assert len(_chain_logs(db_session)) == n_before

        client.delete(f"{API}/documents/{d['id']}", headers=_hdr(admin_token))
        n_after_delete = len(_chain_logs(db_session))
        trashed = client.get(f"{API}/documents/{d['id']}", headers=_hdr(admin_token))
        assert trashed.status_code == 404
        logs = _chain_logs(db_session)
        assert len(logs) == n_after_delete
        assert not any(x.action == "document.viewed" for x in logs)

    def test_document_operation_logs_include_client_ip(
        self, client, admin_token, db_session
    ):
        """仕様: §5.4（行466）, WEB-AUDIT-002（行294）.

        期待: 文書アップロード・更新・削除の監査ログに IP（TestClient では
        ``testclient``）が記録される。
        修正済み: DEFECT-AUD-04（AuditMiddleware が IP を contextvar に設定し、
        create_chained_audit_log が ip_address=None のとき補完）。
        """
        project = _make_project(db_session)
        d = _upload(client, admin_token, project.id)
        client.delete(f"{API}/documents/{d['id']}", headers=_hdr(admin_token))
        doc_logs = [x for x in _chain_logs(db_session) if x.resource_type == "document"]
        assert doc_logs
        assert all(x.ip_address == "testclient" for x in doc_logs), [
            (x.action, x.ip_address) for x in doc_logs
        ]

    def test_ip_follows_proxy_rule_and_jobs_without_request_stay_none(
        self, client, admin_token, db_session, monkeypatch
    ):
        """仕様: §5.4（行466 ip_address）／IP 取得規則は api/auth.py:_client_ip と同じ.

        期待:
        - trust_proxy_headers=false（既定）では X-Forwarded-For を無視し接続元
          （testclient）を記録する（ヘッダ偽装で IP を詐称できない）。
        - trust_proxy_headers=true のときだけ X-Forwarded-For の先頭を記録する。
        - HTTP リクエスト外（バッチジョブ）では ip_address は None のまま。
        修正済み: DEFECT-AUD-04。
        """
        from config import settings
        from services.audit_chain_service import create_chained_audit_log

        xff = {"X-Forwarded-For": "203.0.113.7, 10.0.0.1"}
        project = _make_project(db_session)
        r = client.patch(
            f"{API}/documents/{_upload(client, admin_token, project.id)['id']}",
            headers={**_hdr(admin_token), **xff},
            json={"title": "spoof"},
        )
        assert r.status_code == 200
        monkeypatch.setattr(settings, "trust_proxy_headers", True)
        r2 = client.post(
            f"{API}/projects/",
            headers={**_hdr(admin_token), **xff},
            json={"name": "QA proxy", "code": "QA-PROXY-01"},
        )
        assert r2.status_code == 201
        monkeypatch.setattr(settings, "trust_proxy_headers", False)

        logs = _chain_logs(db_session)
        updated = [x for x in logs if x.action == "document.updated"]
        created = [x for x in logs if x.action == "project.created"]
        assert [x.ip_address for x in updated] == ["testclient"]
        assert [x.ip_address for x in created] == ["203.0.113.7"]

        job = create_chained_audit_log(db_session, user_id=None, action="qa.job")
        assert job.ip_address is None

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "DEFECT-AUD-05: 未決（ユーザー判断待ち） §5.4（行467,471,472）user_agent / request_id / result 列が"
            "監査ログモデルに存在しない（WEB-AUDIT-002 は「結果」を含み実装済と記載）"
            " 根拠: models/audit_log.py:21-39"
        ),
    )
    def test_audit_log_has_spec_fields(self):
        """仕様: §5.4（行460-473）, WEB-AUDIT-002（行294）.

        期待: 監査ログに user_agent / request_id / result が存在する。
        """
        cols = set(AuditLog.__table__.columns.keys())
        assert {"user_agent", "request_id", "result"} <= cols, sorted(cols)


@pytest.fixture
def seeded_logs(db_session, manager_user, engineer_user):
    """固定日時（2001年）の非チェーン監査ログ3件（検索・CSV 用）."""
    rows = [
        (manager_user.id, "qa.op", datetime(2001, 1, 10, tzinfo=timezone.utc)),
        (engineer_user.id, "qa.op", datetime(2001, 2, 10, tzinfo=timezone.utc)),
        (manager_user.id, "qa.op", datetime(2001, 3, 10, tzinfo=timezone.utc)),
    ]
    for uid, action, ts in rows:
        db_session.add(
            AuditLog(
                user_id=uid,
                action=action,
                resource_type="qa",
                detail=str(ts.date()),
                created_at=ts,
            )
        )
    db_session.commit()
    return rows


class TestAuditSearchAndExport:
    def test_search_by_operator(self, client, admin_token, seeded_logs, manager_user):
        """仕様: AT-AUDIT-004（行726）, WEB-AUDIT-003（行295）.

        期待: user_id 指定でその操作者のログのみ返る。
        """
        resp = client.get(
            f"{API}/audit-logs/",
            params={"user_id": manager_user.id, "action": "qa.op"},
            headers=_hdr(admin_token),
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 2
        assert {x["user_id"] for x in items} == {manager_user.id}

    def test_search_by_date_range(self, client, admin_token, seeded_logs):
        """仕様: AT-AUDIT-004（行726）, WEB-AUDIT-003（行295）.

        期待: 2001-02-01〜2001-02-28 で絞ると 2001-02-10 の1件だけ返る。
        境界は両端を含む（CSV エクスポートと同じ）。
        修正済み: DEFECT-AUD-06。
        """
        resp = client.get(
            f"{API}/audit-logs/",
            params={
                "action": "qa.op",
                "date_from": "2001-02-01T00:00:00Z",
                "date_to": "2001-02-28T23:59:59Z",
            },
            headers=_hdr(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert [x["detail"] for x in resp.json()["items"]] == ["2001-02-10"]

        inclusive = client.get(
            f"{API}/audit-logs/",
            params={
                "action": "qa.op",
                "date_from": "2001-02-10T00:00:00Z",
                "date_to": "2001-03-10T00:00:00Z",
            },
            headers=_hdr(admin_token),
        )
        assert inclusive.json()["total"] == 2

    def test_csv_export_with_period_admin_only(self, client, admin_token, seeded_logs):
        """仕様: AT-AUDIT-005（行727）, WEB-AUDIT-004（行296: 期間指定・管理者限定）.

        期待: 管理者は期間指定 CSV を取得でき、期間外のログは含まれない。
        エクスポート自体も監査ログ（audit.exported）に記録される。
        """
        resp = client.get(
            f"{API}/audit-logs/export.csv",
            params={
                "action": "qa.op",
                "date_from": "2001-02-01T00:00:00Z",
                "date_to": "2001-03-31T23:59:59Z",
            },
            headers=_hdr(admin_token),
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        text = resp.content.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text)))
        assert rows[0][:4] == ["sequence_number", "created_at", "user_id", "action"]
        dates = sorted(r[1][:10] for r in rows[1:])
        assert dates == ["2001-02-10", "2001-03-10"]

        logs = client.get(
            f"{API}/audit-logs/",
            params={"action": "audit.exported"},
            headers=_hdr(admin_token),
        ).json()
        assert logs["total"] == 1

    @pytest.mark.parametrize("who", ["manager_token", "engineer_token", "viewer_token"])
    def test_csv_export_forbidden_for_non_admin(self, client, request, who):
        """仕様: WEB-AUDIT-004（行296: 管理者限定）, §5.2（行441）.

        期待: 非管理者の CSV エクスポートは 403。
        """
        token = request.getfixturevalue(who)
        resp = client.get(f"{API}/audit-logs/export.csv", headers=_hdr(token))
        assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# B. 電子納品
# ═══════════════════════════════════════════════════════════════════════════

FIXED_DELIVERY_TIME = datetime(2001, 4, 1, 12, 0, 0, tzinfo=timezone.utc)


def _strip_creation_date(xml: str) -> str:
    return re.sub(r"<作成日>\d{8}</作成日>", "<作成日/>", xml)


class TestElectronicDelivery:
    def _setup(self, client, db, admin_token, manager_user):
        project = _make_project(db, code="QA-ED-001")
        _add_member(db, project.id, manager_user.id)
        _upload(client, admin_token, project.id, title="図面1", document_type="drawing")
        _upload(
            client,
            admin_token,
            project.id,
            title="写真1",
            document_type="photo",
            content=PDF_BYTES + b"% photo\n",
        )
        _upload(
            client,
            admin_token,
            project.id,
            title="図面2",
            document_type="drawing",
            content=PDF_BYTES + b"% drawing2\n",
        )
        return project

    def test_two_generations_are_reproducible_except_time(
        self, client, admin_token, manager_token, manager_user, db_session
    ):
        """仕様: README.md 行104（INDEX.XML・フォルダ構成）／再現性の記録.

        期待: 同一入力で2回 ZIP を生成すると、ファイル名一覧・各エントリ内容・
        INDEX.XML（作成日を除く）が一致する。
        記録（時刻依存部分）: ルートフォルダ名 ``{CODE}_{YYYYMMDD}``、INDEX.XML の
        ``作成日``、Content-Disposition のファイル名は生成日時由来
        （services/electronic_delivery_service.py:44,134,210-213）。ZIP エントリの
        date_time は ``zipfile.writestr`` が壁時計から付与するため generated_at を
        固定しても制御されず、ZIP バイト列の完全一致は保証されない。
        """
        project = self._setup(client, db_session, admin_token, manager_user)
        url = f"{API}/projects/{project.id}/electronic-delivery"
        with _frozen_now("services.electronic_delivery_service", FIXED_DELIVERY_TIME):
            r1 = client.post(url, headers=_hdr(manager_token))
            r2 = client.post(url, headers=_hdr(manager_token))
        assert r1.status_code == r2.status_code == 200
        assert 'filename="QA_ED_001_20010401.zip"' in r1.headers["content-disposition"]

        z1 = zipfile.ZipFile(io.BytesIO(r1.content))
        z2 = zipfile.ZipFile(io.BytesIO(r2.content))
        names = z1.namelist()
        assert names == z2.namelist()
        assert names == [
            "QA_ED_001_20010401/INDEX.XML",
            "QA_ED_001_20010401/DRAWINGS/DRAW_0001.PDF",
            "QA_ED_001_20010401/DRAWINGS/DRAW_0002.PDF",
            "QA_ED_001_20010401/PHOTO/PHOT_0001.PDF",
        ]
        for n in names:
            assert z1.read(n) == z2.read(n), n
        index = z1.read(names[0]).decode("utf-8")
        assert "<作成日>20010401</作成日>" in index
        assert _strip_creation_date(index) == _strip_creation_date(
            z2.read(names[0]).decode("utf-8")
        )
        # ZIP エントリの時刻は generated_at（2001年）ではなく壁時計由来
        assert all(info.date_time[0] != 2001 for info in z1.infolist())

    def test_creation_date_changes_with_generation_date(
        self, client, admin_token, manager_token, manager_user, db_session
    ):
        """仕様: README.md 行104 / 再現性の記録.

        期待（記録）: 生成日が異なるとルートフォルダ名と INDEX.XML の作成日のみが
        変わり、それ以外の INDEX.XML 内容とエントリ内容は一致する。
        """
        project = self._setup(client, db_session, admin_token, manager_user)
        url = f"{API}/projects/{project.id}/electronic-delivery"
        with _frozen_now("services.electronic_delivery_service", FIXED_DELIVERY_TIME):
            r1 = client.post(url, headers=_hdr(manager_token))
        with _frozen_now(
            "services.electronic_delivery_service",
            FIXED_DELIVERY_TIME + timedelta(days=1),
        ):
            r2 = client.post(url, headers=_hdr(manager_token))
        z1 = zipfile.ZipFile(io.BytesIO(r1.content))
        z2 = zipfile.ZipFile(io.BytesIO(r2.content))
        strip = [n.split("/", 1)[1] for n in z1.namelist()]
        assert strip == [n.split("/", 1)[1] for n in z2.namelist()]
        assert z1.namelist()[0].startswith("QA_ED_001_20010401/")
        assert z2.namelist()[0].startswith("QA_ED_001_20010402/")
        x1 = z1.read(z1.namelist()[0]).decode("utf-8")
        x2 = z2.read(z2.namelist()[0]).decode("utf-8")
        assert x1 != x2
        assert _strip_creation_date(x1) == _strip_creation_date(x2)

    @pytest.mark.parametrize("who", ["engineer_token", "viewer_token"])
    def test_non_manager_cannot_generate(
        self, client, request, admin_token, db_session, who
    ):
        """仕様: §5.2（行426-443）/ api/electronic_delivery.py:57（require_manager）.

        期待: engineer / viewer は案件メンバーでも生成不可（403）。readiness 確認は可。
        """
        project = _make_project(db_session)
        token = request.getfixturevalue(who)
        uid = "engineer_user" if who == "engineer_token" else "viewer_user"
        _add_member(db_session, project.id, request.getfixturevalue(uid).id)
        _upload(client, admin_token, project.id)
        resp = client.post(
            f"{API}/projects/{project.id}/electronic-delivery", headers=_hdr(token)
        )
        assert resp.status_code == 403
        check = client.get(
            f"{API}/projects/{project.id}/electronic-delivery/check",
            headers=_hdr(token),
        )
        assert check.status_code == 200

    def test_non_member_engineer_gets_404_on_check(
        self, client, admin_token, engineer_token, db_session
    ):
        """仕様: WEB-DOC-010（行272: メンバー以外はアクセス不可・404 秘匿）.

        期待: 非メンバー engineer の readiness 確認は 404、存在しない案件も 404。
        """
        project = _make_project(db_session)
        r = client.get(
            f"{API}/projects/{project.id}/electronic-delivery/check",
            headers=_hdr(engineer_token),
        )
        assert r.status_code == 404
        r2 = client.get(
            f"{API}/projects/no-such-project/electronic-delivery/check",
            headers=_hdr(engineer_token),
        )
        assert r2.status_code == 404

    def test_manager_unknown_project_is_404(self, client, manager_token):
        """仕様: WEB-DOC-010（行272）.

        期待: manager が存在しない案件に生成要求すると 404。
        """
        resp = client.post(
            f"{API}/projects/no-such-project/electronic-delivery",
            headers=_hdr(manager_token),
        )
        assert resp.status_code == 404

    def test_manager_can_generate_any_project_but_engineer_cannot(
        self, client, admin_token, manager_token, engineer_token, db_session
    ):
        """仕様: §5.2 v1.1.0（manager のプロジェクト参照・文書参照は「全て」）.

        決定 A-1（2026-10-03 ユーザー確定）により、manager は所属していない
        案件も閲覧でき、電子納品も生成できる（旧 DEFECT-ED-01 は仕様どおり）。
        一方、engineer は電子納品の生成権限がない（require_manager）ため 403、
        案件メンバーでない engineer からは案件の存在も見えない（404 秘匿）。
        """
        other = _make_project(db_session, code="QA-OTHER-01", name="他案件")
        _upload(client, admin_token, other.id)
        resp = client.post(
            f"{API}/projects/{other.id}/electronic-delivery",
            headers=_hdr(manager_token),
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"

        resp = client.post(
            f"{API}/projects/{other.id}/electronic-delivery",
            headers=_hdr(engineer_token),
        )
        assert resp.status_code == 403
        resp = client.get(
            f"{API}/projects/{other.id}/electronic-delivery/check",
            headers=_hdr(engineer_token),
        )
        assert resp.status_code == 404

    def test_readiness_boundaries(
        self, client, admin_token, manager_token, manager_user, db_session
    ):
        """仕様: README.md 行104 / api/electronic_delivery.py:30-43（readiness）.

        期待:
        - 文書0件: ready=false、警告「文書が1件もありません」、生成は 409
          （E-1 ユーザー確定: 0件なら生成拒否。allow_partial=true でも 409）。
        - ごみ箱に入れた文書のみ: document_count=0（納品対象外）、生成は 409。
        - ファイル欠損: ready=false、生成は 409、allow_partial=true で生成し
          X-CivilPDF-Omitted-Documents=1。
        - 全件欠損: allow_partial=true でも 409（空パッケージにしない）。
        生成拒否時は監査ログ electronic_delivery.generated を残さない。
        """
        project = _make_project(db_session)
        _add_member(db_session, project.id, manager_user.id)
        check_url = f"{API}/projects/{project.id}/electronic-delivery/check"
        gen_url = f"{API}/projects/{project.id}/electronic-delivery"

        empty = client.get(check_url, headers=_hdr(manager_token)).json()
        assert empty["ready"] is False and empty["document_count"] == 0
        assert any("1件もありません" in w for w in empty["warnings"])
        r0 = client.post(gen_url, headers=_hdr(manager_token))
        assert r0.status_code == 409
        assert "1件もない" in r0.json()["detail"]
        r0p = client.post(
            gen_url, params={"allow_partial": "true"}, headers=_hdr(manager_token)
        )
        assert r0p.status_code == 409

        d = _upload(client, admin_token, project.id)
        client.delete(f"{API}/documents/{d['id']}", headers=_hdr(admin_token))
        trashed = client.get(check_url, headers=_hdr(manager_token)).json()
        assert trashed["document_count"] == 0 and trashed["ready"] is False
        assert client.post(gen_url, headers=_hdr(manager_token)).status_code == 409

        only_missing = _upload(client, admin_token, project.id, title="唯一欠損")
        only_path = Path(
            db_session.query(Document)
            .filter(Document.id == only_missing["id"])
            .one()
            .file_path
        )
        only_path.unlink()
        all_unreadable = client.post(
            gen_url, params={"allow_partial": "true"}, headers=_hdr(manager_token)
        )
        assert all_unreadable.status_code == 409
        assert "読み取れる文書が1件もない" in all_unreadable.json()["detail"]
        assert not [
            x
            for x in _chain_logs(db_session)
            if x.action == "electronic_delivery.generated"
        ]
        client.delete(
            f"{API}/documents/{only_missing['id']}", headers=_hdr(admin_token)
        )

        d2 = _upload(client, admin_token, project.id, title="欠損")
        _upload(
            client, admin_token, project.id, title="正常", content=PDF_BYTES + b"%ok\n"
        )
        Path(
            db_session.query(Document).filter(Document.id == d2["id"]).one().file_path
        ).unlink()
        missing = client.get(check_url, headers=_hdr(manager_token)).json()
        assert missing["ready"] is False
        assert [u["id"] for u in missing["unreadable_documents"]] == [d2["id"]]
        assert client.post(gen_url, headers=_hdr(manager_token)).status_code == 409
        partial = client.post(
            gen_url, params={"allow_partial": "true"}, headers=_hdr(manager_token)
        )
        assert partial.status_code == 200
        assert partial.headers["x-civilpdf-omitted-documents"] == "1"

    def test_generation_is_audited_with_ip(
        self, client, admin_token, manager_token, manager_user, db_session
    ):
        """仕様: WEB-AUDIT-001（行293）, §5.4（行466）.

        期待: 生成は electronic_delivery.generated として操作者・IP 付きで監査記録
        される（DEFECT-AUD-04 修正により ip_address は接続元 testclient）。
        """
        project = self._setup(client, db_session, admin_token, manager_user)
        assert (
            client.post(
                f"{API}/projects/{project.id}/electronic-delivery",
                headers=_hdr(manager_token),
            ).status_code
            == 200
        )
        logs = [
            x
            for x in _chain_logs(db_session)
            if x.action == "electronic_delivery.generated"
        ]
        assert len(logs) == 1
        assert logs[0].user_id == manager_user.id
        assert json.loads(logs[0].detail)["document_count"] == 3
        assert logs[0].ip_address == "testclient"


# ═══════════════════════════════════════════════════════════════════════════
# C. 保存期限と削除
# ═══════════════════════════════════════════════════════════════════════════

NOW = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
_JST = timezone(timedelta(hours=9))


def _jst(y, mo, d, h=0, mi=0, sec=0) -> datetime:
    return datetime(y, mo, d, h, mi, sec, tzinfo=_JST)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class TestRetentionCalculation:
    def test_default_map_and_seeded_policies_per_type(self, db_session, admin_user):
        """仕様: requirements.md v1.1.0 決定 B-2（2026-10-03）.

        期待（アップロード日 2025-04-01 固定、アップロード日起算）:
        - 契約書は7年、図面は10年。フォールバック表（ポリシー未投入）と
          既定ポリシー投入後のどちらでも同じ値（以前は契約書10年/7年、図面永久で不一致）。
        - それ以外の種別（inspection/safety/report/photo/correction/other）は未決のため
          従来の値を記録する。report・other はフォールバック表と既定ポリシーで
          まだ食い違う（report 7/15、other 7/0）。
        期限は暦年（同月同日同時刻）で計算されることも合わせて確認する（RET-01）。
        """
        from services.retention_service import (
            apply_retention_policy,
            seed_default_policies,
        )

        project = _make_project(db_session)
        created = datetime(2025, 4, 1, tzinfo=timezone.utc)

        def expiry(doc_type):
            doc = Document(
                title="r",
                filename="r.pdf",
                file_size=1,
                document_type=doc_type,
                project_id=project.id,
                owner_id=admin_user.id,
                created_at=created,
            )
            apply_retention_policy(db_session, doc)
            return doc.retention_expires_at

        def years(dt):
            """Calendar years between created and expiry (same month/day/time)."""
            if dt is None:
                return None
            dt = _as_utc(dt)
            assert (dt.month, dt.day, dt.time()) == (
                created.month,
                created.day,
                created.time(),
            ), dt
            return dt.year - created.year

        fallback = {t.value: years(expiry(t)) for t in DocumentType}
        assert fallback == {
            "contract": 7,
            "inspection": 10,
            "drawing": 10,
            "safety": 3,
            "report": 7,
            "photo": 5,
            "correction": 3,
            "other": 7,
        }
        assert seed_default_policies(db_session) == 6
        seeded = {t.value: years(expiry(t)) for t in DocumentType}
        assert seeded == {
            "contract": 7,
            "inspection": 10,
            "drawing": 10,
            "safety": 3,
            "report": 15,
            "photo": 5,
            "correction": 3,
            "other": 0,
        }

    def test_permanent_and_zero_year_semantics(self):
        """仕様: models/retention_policy.py:40（-1=永続, 0=目的達成後に破棄）.

        期待: retention_years=-1 または is_permanent=True は None（期限なし）、
        0 は作成日時そのもの。
        """
        from services.retention_service import calculate_expiry

        created = datetime(2025, 4, 1, tzinfo=timezone.utc)
        assert calculate_expiry(created, -1) is None
        assert calculate_expiry(created, 7, is_permanent=True) is None
        assert calculate_expiry(created, 0) == created

    def test_seven_years_is_calendar_years_across_leap_days(self):
        """仕様: README.md 行105（7 年保持）.

        期待: 2025-04-01 作成の7年保持の期限は暦上の 2032-04-01（以降）。
        修正済み: DEFECT-RET-01（修正前は 2032-03-30。うるう日分2日短かった）。
        """
        from services.retention_service import calculate_expiry

        created = datetime(2025, 4, 1, tzinfo=timezone.utc)
        assert calculate_expiry(created, 7) >= created.replace(year=2032)
        assert calculate_expiry(created, 7) == datetime(2032, 4, 1, tzinfo=timezone.utc)

    @pytest.mark.parametrize(
        "created, years, expected",
        [
            # 2/29 起点で対象年にうるう日がない → 3/1（暦年より短くしない）
            (
                datetime(2024, 2, 29, 15, 30, tzinfo=timezone.utc),
                7,
                datetime(2031, 3, 1, 15, 30, tzinfo=timezone.utc),
            ),
            # 2/29 起点で対象年もうるう年 → 2/29
            (
                datetime(2024, 2, 29, tzinfo=timezone.utc),
                4,
                datetime(2028, 2, 29, tzinfo=timezone.utc),
            ),
            # 2/28 起点はそのまま 2/28
            (
                datetime(2023, 2, 28, tzinfo=timezone.utc),
                5,
                datetime(2028, 2, 28, tzinfo=timezone.utc),
            ),
            # 年末・時刻・タイムゾーン（JST 表現）を保持
            (
                datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone(timedelta(hours=9))),
                10,
                datetime(2035, 12, 31, 23, 59, 59, tzinfo=timezone(timedelta(hours=9))),
            ),
        ],
        ids=["leap-to-nonleap", "leap-to-leap", "feb28", "year-end-jst"],
    )
    def test_calendar_year_edge_cases(self, created, years, expected):
        """仕様: README.md 行105（種別別の年数保持）／RET-01 修正の境界.

        期待: 期限は暦年加算。2/29 起点で対象年に 2/29 がなければ 3/1
        （services/retention_service.py の calculate_expiry docstring に明記）。
        """
        from services.retention_service import calculate_expiry

        assert calculate_expiry(created, years) == expected

    def test_archive_dry_run_changes_nothing(self, db_session, admin_user):
        """仕様: services/retention_service.py:96-108（dry_run は書込みなし）.

        期待: 期限切れ文書があっても dry_run=True は件数のみ返し、DB を変更しない。
        続けて本実行すると ARCHIVED になり、再実行では0件（冪等）。
        """
        from services.retention_service import archive_expired_documents

        project = _make_project(db_session)
        doc = _make_doc(
            db_session,
            project_id=project.id,
            owner_id=admin_user.id,
            retention_expires_at=datetime(2001, 1, 1, tzinfo=timezone.utc),
        )
        assert archive_expired_documents(db_session, dry_run=True) == 1
        db_session.expire_all()
        fresh = db_session.query(Document).filter(Document.id == doc.id).one()
        assert fresh.is_archived is False and fresh.status == DocumentStatus.DRAFT
        assert archive_expired_documents(db_session) == 1
        assert archive_expired_documents(db_session) == 0
        db_session.expire_all()
        assert db_session.query(Document).filter(
            Document.id == doc.id
        ).one().status == (DocumentStatus.ARCHIVED)


class TestDeletionJob:
    @pytest.mark.parametrize(
        "now_jst, requested_jst, expected_deleted",
        [
            # 実行 2026-03-01 09:00 JST。要求日 D の D+30 日（30日目）から削除対象。
            (_jst(2026, 3, 1, 9), _jst(2026, 1, 31, 0, 0, 0), False),  # 29日目
            (_jst(2026, 3, 1, 9), _jst(2026, 1, 31, 23, 59, 59), False),  # 29日目
            (_jst(2026, 3, 1, 9), _jst(2026, 1, 30, 0, 0, 0), True),  # 30日目
            (_jst(2026, 3, 1, 9), _jst(2026, 1, 30, 23, 59, 59), True),  # 30日目
            (_jst(2026, 3, 1, 9), _jst(2026, 1, 29, 12, 0, 0), True),  # 31日目
            # 実行時刻が 30日目の 00:00 JST ちょうど／その1秒前
            (_jst(2026, 3, 1, 0, 0, 0), _jst(2026, 1, 30, 23, 59, 59), True),
            (_jst(2026, 2, 28, 23, 59, 59), _jst(2026, 1, 30, 0, 0, 0), False),
            # UTC では 1/30 だが JST では 1/31 の要求 → JST 基準で29日目
            (
                _jst(2026, 3, 1, 9),
                datetime(2026, 1, 30, 15, 30, tzinfo=timezone.utc),
                False,
            ),
            # UTC では 3/1 前だが JST では 3/1（30日目）の実行
            (
                datetime(2026, 2, 28, 15, 0, tzinfo=timezone.utc),
                _jst(2026, 1, 30, 12),
                True,
            ),
        ],
        ids=[
            "day29-start",
            "day29-end",
            "day30-start",
            "day30-end",
            "day31",
            "now-exactly-day30-midnight",
            "now-1s-before-day30",
            "request-utc-vs-jst-date",
            "run-utc-vs-jst-date",
        ],
    )
    def test_grace_period_boundary_jst(
        self, db_session, admin_user, tmp_path, now_jst, requested_jst, expected_deleted
    ):
        """仕様: WEB-DOC-005（行267: 論理削除、30日後物理削除）／B-3（ユーザー確定）.

        期待: 「30日経過後」は30日目を含み、日付は JST 基準。削除要求の JST 日付
        D に対し、JST 日付 D+30（30日目）の 00:00 JST から物理削除対象、D+29
        （29日目）までは保持。要求時刻（時分秒）は判定に影響しない。
        時刻はすべて固定値（run_deletion_job の now 引数）。
        """
        from services.deletion_job import run_deletion_job

        project = _make_project(db_session)
        f = tmp_path / "doc.pdf"
        f.write_bytes(PDF_BYTES)
        doc = _make_doc(
            db_session,
            project_id=project.id,
            owner_id=admin_user.id,
            file_path=str(f),
            # SQLite の DateTime はタイムゾーンを保持しないため UTC で保存する
            # （本番 PostgreSQL timestamptz と同じ瞬間を表す）。
            deletion_requested_at=requested_jst.astimezone(timezone.utc),
        )
        result = run_deletion_job(db_session, grace_days=30, now=now_jst)
        db_session.expire_all()
        fresh = db_session.query(Document).filter(Document.id == doc.id).one()
        assert result["processed"] == (1 if expected_deleted else 0)
        assert f.exists() is (not expected_deleted)
        assert (fresh.file_path is None) is expected_deleted

    @pytest.mark.parametrize(
        "elapsed, expected_deleted",
        [
            (timedelta(days=29), False),
            (timedelta(days=30) - timedelta(seconds=1), True),
            (timedelta(days=30), True),
            (timedelta(days=31), True),
        ],
        ids=["29d", "30d-1s", "30d-exact", "31d"],
    )
    def test_grace_period_boundary(
        self, db_session, admin_user, tmp_path, elapsed, expected_deleted
    ):
        """仕様: WEB-DOC-005（行267）／B-3（30日目を含む・JST 日付基準）.

        期待: 既定の現在時刻経路（datetime.now を固定値 NOW=2026-03-01T00:00Z
        ＝09:00 JST に差し替え）でも JST 日付で判定される。
        NOW-(30日-1秒) は JST 1/30 09:00:01 の要求＝30日目なので削除対象
        （修正前は経過秒数比較で保持されていた）。
        """
        from services.deletion_job import run_deletion_job

        project = _make_project(db_session)
        f = tmp_path / "doc.pdf"
        f.write_bytes(PDF_BYTES)
        doc = _make_doc(
            db_session,
            project_id=project.id,
            owner_id=admin_user.id,
            file_path=str(f),
            deletion_requested_at=NOW - elapsed,
        )
        with _frozen_now("services.deletion_job", NOW):
            result = run_deletion_job(db_session, grace_days=30)
        db_session.expire_all()
        fresh = db_session.query(Document).filter(Document.id == doc.id).one()
        assert result["processed"] == (1 if expected_deleted else 0)
        assert f.exists() is (not expected_deleted)
        assert (fresh.file_path is None) is expected_deleted

    def test_dry_run_changes_nothing(self, db_session, admin_user, tmp_path):
        """仕様: services/deletion_job.py:35-36（dry_run は何も変更しない）.

        期待: 対象があっても dry_run=True ではファイル・DB・監査ログが不変で、
        candidate_ids に対象 id が返る。
        """
        from services.deletion_job import run_deletion_job

        project = _make_project(db_session)
        f = tmp_path / "doc.pdf"
        f.write_bytes(PDF_BYTES)
        doc = _make_doc(
            db_session,
            project_id=project.id,
            owner_id=admin_user.id,
            file_path=str(f),
            deletion_requested_at=NOW - timedelta(days=31),
        )
        n_logs = db_session.query(AuditLog).count()
        with _frozen_now("services.deletion_job", NOW):
            result = run_deletion_job(db_session, grace_days=30, dry_run=True)
        assert result["dry_run"] is True and result["candidate_ids"] == [doc.id]
        assert result["deleted_files"] == 0
        db_session.expire_all()
        fresh = db_session.query(Document).filter(Document.id == doc.id).one()
        assert f.exists() and fresh.file_path == str(f) and fresh.archived_at is None
        assert db_session.query(AuditLog).count() == n_logs

    def test_physical_deletion_is_audited_in_chain(
        self, db_session, admin_user, tmp_path
    ):
        """仕様: services/deletion_job.py:5（監査ログは保持）, WEB-AUDIT-006（行298）.

        期待: 物理削除で gdpr_physical_deletion がチェーンに1件記録され、チェーンは valid。
        """
        from services.audit_chain_service import verify_chain
        from services.deletion_job import run_deletion_job

        project = _make_project(db_session)
        f = tmp_path / "doc.pdf"
        f.write_bytes(PDF_BYTES)
        doc = _make_doc(
            db_session,
            project_id=project.id,
            owner_id=admin_user.id,
            file_path=str(f),
            deletion_requested_at=NOW - timedelta(days=31),
        )
        with _frozen_now("services.deletion_job", NOW):
            run_deletion_job(db_session, grace_days=30)
        logs = [
            x for x in _chain_logs(db_session) if x.action == "gdpr_physical_deletion"
        ]
        assert [x.resource_id for x in logs] == [doc.id]
        assert verify_chain(db_session)["chain_valid"] is True

    def test_rerun_does_not_process_twice(self, db_session, admin_user, tmp_path):
        """仕様: WEB-DOC-005（行267: 30日後物理削除はバッチ委譲）— バッチの冪等性.

        期待: 翌日にもう一度実行しても2回目は processed=0（dry_run の候補にも
        出ない）、archived_at は初回の値、gdpr_physical_deletion 監査ログは1件のみ。
        修正済み: DEFECT-DEL-01。
        """
        from services.deletion_job import run_deletion_job

        project = _make_project(db_session)
        f = tmp_path / "doc.pdf"
        f.write_bytes(PDF_BYTES)
        doc = _make_doc(
            db_session,
            project_id=project.id,
            owner_id=admin_user.id,
            file_path=str(f),
            deletion_requested_at=NOW - timedelta(days=31),
        )
        with _frozen_now("services.deletion_job", NOW):
            run_deletion_job(db_session, grace_days=30)
        db_session.expire_all()
        first_archived = (
            db_session.query(Document).filter(Document.id == doc.id).one().archived_at
        )
        with _frozen_now("services.deletion_job", NOW + timedelta(days=1)):
            preview = run_deletion_job(db_session, grace_days=30, dry_run=True)
            second = run_deletion_job(db_session, grace_days=30)
        assert preview["candidate_ids"] == []
        db_session.expire_all()
        fresh = db_session.query(Document).filter(Document.id == doc.id).one()
        logs = [
            x for x in _chain_logs(db_session) if x.action == "gdpr_physical_deletion"
        ]
        assert second["processed"] == 0
        assert fresh.archived_at == first_archived
        assert len(logs) == 1

    def test_retention_period_does_not_block_physical_deletion(
        self, db_session, admin_user, tmp_path
    ):
        """仕様矛盾候補の記録: WEB-DOC-005（行267: 30日後物理削除）と
        README.md 行105（電子帳簿保存法: 書類種別別 7 年保持）.

        記録: 保存期限が未来（2033年）の契約書、および永久保存（期限 None）の
        図面であっても、削除要求から30日経過すれば物理削除される
        （deletion_job は retention_expires_at / RetentionPolicy を参照しない:
        services/deletion_job.py:43-50）。法令適合の判定はしない。どちらを優先
        するかは人の判断事項。
        """
        from services.deletion_job import run_deletion_job

        project = _make_project(db_session)
        paths, ids = [], []
        for doc_type, expires in (
            (DocumentType.CONTRACT, datetime(2033, 1, 1, tzinfo=timezone.utc)),
            (DocumentType.DRAWING, None),
        ):
            f = tmp_path / f"{doc_type.value}.pdf"
            f.write_bytes(PDF_BYTES)
            paths.append(f)
            ids.append(
                _make_doc(
                    db_session,
                    project_id=project.id,
                    owner_id=admin_user.id,
                    document_type=doc_type,
                    file_path=str(f),
                    deletion_requested_at=NOW - timedelta(days=31),
                    retention_expires_at=expires,
                ).id
            )
        with _frozen_now("services.deletion_job", NOW):
            result = run_deletion_job(db_session, grace_days=30)
        assert result["deleted_files"] == 2
        assert not any(p.exists() for p in paths)
        db_session.expire_all()
        docs = db_session.query(Document).filter(Document.id.in_(ids)).all()
        assert all(d.file_path is None for d in docs)
        contract = next(d for d in docs if d.document_type == DocumentType.CONTRACT)
        assert _as_utc(contract.retention_expires_at) > NOW


# ═══════════════════════════════════════════════════════════════════════════
# D. AI 補助
# ═══════════════════════════════════════════════════════════════════════════


def _ai_doc(db, owner_id: str, project_id: str) -> Document:
    doc = _make_doc(
        db, project_id=project_id, owner_id=owner_id, document_type=DocumentType.DRAWING
    )
    doc.ocr_text = "平面図 1:100 合成テキスト（QA 用。実データではない）"
    doc.tags = ["既存タグ"]
    db.commit()
    db.refresh(doc)
    return doc


def _mock_client(payload: dict | str):
    text = (
        payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    )
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    client = MagicMock()
    client.messages.create.return_value = msg
    return client


@pytest.fixture
def ai_enabled(db_session):
    from services import ai_settings as ai_settings_service

    ai_settings_service.update_ai_setting(db_session, enabled=True)


CLASSIFY_RESULT = {
    "drawing_type": "平面図",
    "project_type": "建築",
    "confidence": 0.91,
    "reasoning": "QA",
}


class TestAiAssist:
    @pytest.mark.parametrize("path", ["classify", "extract", "summary"])
    def test_disabled_returns_503_without_calling_client(
        self, client, admin_token, admin_user, db_session, path
    ):
        """仕様: §6.4（行535: 組織単位オン/オフ）.

        期待: AI 無効（既定）では 503、Anthropic クライアント取得・SDK 生成とも呼ばれない。
        """
        project = _make_project(db_session)
        doc = _ai_doc(db_session, admin_user.id, project.id)
        method = client.get if path == "summary" else client.post
        with (
            patch("api.ai._get_anthropic_client") as factory,
            patch("anthropic.Anthropic") as sdk,
        ):
            resp = method(
                f"{API}/ai/documents/{doc.id}/{path}", headers=_hdr(admin_token)
            )
        assert resp.status_code == 503
        factory.assert_not_called()
        sdk.assert_not_called()

    @pytest.mark.parametrize("path", ["classify", "extract", "summary"])
    def test_invisible_document_is_404_without_calling_client(
        self, client, engineer_token, admin_user, db_session, ai_enabled, path
    ):
        """仕様: WEB-DOC-010（行272: 非メンバーは 404 秘匿）.

        期待: 非メンバー engineer の AI 要求は 404 で、AI は呼ばれない。
        """
        project = _make_project(db_session)
        doc = _ai_doc(db_session, admin_user.id, project.id)
        method = client.get if path == "summary" else client.post
        with patch("api.ai._get_anthropic_client") as factory:
            resp = method(
                f"{API}/ai/documents/{doc.id}/{path}", headers=_hdr(engineer_token)
            )
        assert resp.status_code == 404
        factory.assert_not_called()

    def test_classification_does_not_change_status_or_type_and_is_audited(
        self, client, admin_token, admin_user, db_session, ai_enabled
    ):
        """仕様: §6.2（行519: 自動分類は提案）, §6.4（行538: 送信ログ）.

        期待: 分類は文書の status（DRAFT）と document_type を変更しない。
        AI 呼出しは ai.document_classified として文書 id・操作者・IP 付きで監査記録
        される（DEFECT-AUD-04 修正により ip_address は接続元 testclient）。
        """
        project = _make_project(db_session)
        doc = _ai_doc(db_session, admin_user.id, project.id)
        with patch(
            "api.ai._get_anthropic_client", return_value=_mock_client(CLASSIFY_RESULT)
        ) as f:
            resp = client.post(
                f"{API}/ai/documents/{doc.id}/classify", headers=_hdr(admin_token)
            )
        assert resp.status_code == 200
        f.return_value.messages.create.assert_called_once()
        db_session.expire_all()
        fresh = db_session.query(Document).filter(Document.id == doc.id).one()
        assert fresh.status == DocumentStatus.DRAFT
        assert fresh.document_type == DocumentType.DRAWING
        logs = [
            x for x in _chain_logs(db_session) if x.action == "ai.document_classified"
        ]
        assert len(logs) == 1
        assert logs[0].resource_id == doc.id and logs[0].user_id == admin_user.id
        assert logs[0].ip_address == "testclient"

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "DEFECT-AI-01: 未決（ユーザー判断待ち） §6.2（行519: 自動分類は提案として表示しユーザーが承認/修正）— "
            "分類結果を承認なしで文書 tags と extra_data に即時保存する 根拠: api/ai.py:203-219"
        ),
    )
    def test_classification_is_only_a_proposal(
        self, client, admin_token, admin_user, db_session, ai_enabled
    ):
        """仕様: §6.2（行519）.

        期待: ユーザー承認前の分類結果は文書のタグを変更しない（提案のみ）。
        """
        project = _make_project(db_session)
        doc = _ai_doc(db_session, admin_user.id, project.id)
        with patch(
            "api.ai._get_anthropic_client", return_value=_mock_client(CLASSIFY_RESULT)
        ):
            client.post(
                f"{API}/ai/documents/{doc.id}/classify", headers=_hdr(admin_token)
            )
        db_session.expire_all()
        fresh = db_session.query(Document).filter(Document.id == doc.id).one()
        assert fresh.tags == ["既存タグ"], fresh.tags

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "DEFECT-AI-02: 未決（ユーザー判断待ち） §6.1（行510）/§6.4（行536）文書単位「AI送信禁止」フラグが "
            "Document モデルに存在せず、AI エンドポイントも参照しない 根拠: "
            "models/document.py:44-123, api/ai.py:145-167"
        ),
    )
    def test_document_has_ai_prohibition_flag(self):
        """仕様: §6.1（行510: 機密フラグ付き文書は AI 送信禁止）, §6.4（行536）.

        期待: 文書に AI 送信禁止（機密）フラグ列が存在する。
        """
        cols = set(Document.__table__.columns.keys())
        assert any(
            re.search(r"confidential|ai_(prohibit|block|disabled|opt)|no_ai", c)
            for c in cols
        ), sorted(cols)

    @pytest.mark.parametrize("path", ["classify", "extract", "summary"])
    def test_send_is_logged_even_when_ai_call_fails(
        self, admin_token, admin_user, db_session, ai_enabled, path
    ):
        """仕様: §6.4（行538: どの文書を AI に送信したかをログに記録）.

        期待: 文書テキストを AI に送信した後で応答エラーになっても、送信の事実
        （文書 id・操作者・IP・モデル・失敗種別）が監査チェーンに残る。本文
        （プロンプト・文書テキスト・例外メッセージ）は記録しない。応答は 502、
        文書の tags / extra_data は変更されない。
        修正済み: DEFECT-AI-03。
        """
        project = _make_project(db_session)
        doc = _ai_doc(db_session, admin_user.id, project.id)
        failing = MagicMock()
        failing.messages.create.side_effect = RuntimeError("synthetic upstream error")
        tc = TestClient(app, raise_server_exceptions=False)
        method = tc.get if path == "summary" else tc.post
        with patch("api.ai._get_anthropic_client", return_value=failing):
            resp = method(
                f"{API}/ai/documents/{doc.id}/{path}", headers=_hdr(admin_token)
            )
        assert resp.status_code == 502
        failing.messages.create.assert_called_once()  # 送信は発生している
        logs = [
            x
            for x in _chain_logs(db_session)
            if x.action.startswith("ai.") and x.resource_id == doc.id
        ]
        assert [x.action for x in logs] == [f"ai.document_{path}_failed"]
        assert logs[0].user_id == admin_user.id
        assert logs[0].ip_address == "testclient"
        detail = json.loads(logs[0].detail)
        assert detail["sent"] is True and detail["error_type"] == "RuntimeError"
        assert detail["operation"] == path
        assert "synthetic upstream error" not in logs[0].detail
        assert "平面図" not in logs[0].detail  # 文書本文を記録しない
        db_session.expire_all()
        fresh = db_session.query(Document).filter(Document.id == doc.id).one()
        assert fresh.tags == ["既存タグ"] and fresh.extra_data == {}
