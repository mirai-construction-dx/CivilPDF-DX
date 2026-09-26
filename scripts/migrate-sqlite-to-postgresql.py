#!/usr/bin/env python3
"""SQLite -> PostgreSQL データ移行スクリプト（CivilPDF-DX 用）。

Neon 専用ではなく、任意の PostgreSQL（ローカル PostgreSQL を含む）へ移行できる。
接続先は DATABASE_URL で指定する。

前提:
  - 対象 PostgreSQL には `alembic upgrade head` でスキーマ作成済み
  - 監査ログのハッシュチェーンを壊さないため、audit_logs は
    created_at / sequence_number 昇順で再投入する
  - SQLite FTS5 仮想テーブル（documents_fts 等）は移行しない

使い方:
  DATABASE_URL='postgresql://...' python3 scripts/migrate-sqlite-to-postgresql.py \
    --sqlite src/console/backend/civilpdf_dev.db [--verify-only]

安全のため本番適用前には必ずバックアップと検証（--verify-only）を実施すること。
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from sqlalchemy import MetaData, create_engine, select, func, text


EXCLUDE_TABLES = {"alembic_version"}


def _normalize_datetime(value):
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def convert_value(value, col_type):
    """SQLite の値をターゲット列型へ変換する（汎用・最小限）。"""
    if value is None:
        return None
    type_name = str(col_type).lower()
    if "bool" in type_name:
        return bool(value)
    if "timestamp" in type_name or "datetime" in type_name:
        return _normalize_datetime(value)
    if "json" in type_name:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value
    if "bigint" in type_name or "integer" in type_name:
        if isinstance(value, str) and value.strip():
            return int(value)
        return value
    return value


def table_rows(conn, table_name, order_columns):
    cols = [c.name for c in order_columns] if order_columns else None
    stmt = select("*").select_from(table_name)
    if cols:
        stmt = stmt.order_by(*[table_name.c[c] for c in cols])
    return conn.execute(stmt).mappings().all()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", default="src/console/backend/civilpdf_dev.db")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    target_url = os.environ.get("DATABASE_URL")
    if not target_url:
        print("error: DATABASE_URL が設定されていません", file=sys.stderr)
        sys.exit(2)

    src_engine = create_engine(f"sqlite:///{args.sqlite}")
    dst_engine = create_engine(target_url)

    src_meta = MetaData()
    src_meta.reflect(bind=src_engine)
    dst_meta = MetaData()
    dst_meta.reflect(bind=dst_engine)

    src_tables = {
        name: t for name, t in src_meta.tables.items() if name not in EXCLUDE_TABLES
    }
    dst_tables = {
        name: t for name, t in dst_meta.tables.items() if name not in EXCLUDE_TABLES
    }

    report = []
    with src_engine.connect() as src_conn, dst_engine.begin() as dst_conn:
        for name in sorted(src_tables):
            src_table = src_tables[name]
            if name not in dst_tables:
                report.append((name, "SKIP", "target table missing", 0))
                continue
            dst_table = dst_tables[name]
            order_cols = [
                c
                for c in dst_table.columns
                if c.name in ("created_at", "sequence_number", "id")
            ]
            rows = table_rows(src_conn, src_table, order_cols)
            if not args.verify_only and rows:
                converted = []
                for row in rows:
                    values = {}
                    for col in dst_table.columns:
                        if col.name not in row:
                            continue
                        values[col.name] = convert_value(row[col.name], col.type)
                    converted.append(values)
                dst_conn.execute(dst_table.insert(), converted)

                # 整数 PK（serial/identity）のシーケンスを同期
                for col in dst_table.primary_key.columns:
                    if (
                        "integer" in str(col.type).lower()
                        and col.autoincrement is not False
                    ):
                        seq = dst_conn.execute(
                            text("SELECT pg_get_serial_sequence(:t, :c)"),
                            {"t": name, "c": col.name},
                        ).scalar()
                        if seq:
                            max_id = dst_conn.execute(
                                select(func.max(col)).select_from(dst_table)
                            ).scalar()
                            next_val = (max_id or 0) + 1
                            dst_conn.execute(
                                text(
                                    f"SELECT setval('{seq}', :v, {1 if max_id else 0})"
                                ),
                                {"v": next_val},
                            )
            report.append((name, "OK", "", len(rows)))

    # 検証: 行数一致
    print("=== migration report ===")
    ok = True
    for name, status, note, count in report:
        print(f"{name}: {status} rows={count} {note}")
        if status != "OK":
            ok = False

    with src_engine.connect() as src_conn, dst_engine.connect() as dst_conn:
        for name, status, note, count in report:
            if status != "OK":
                continue
            dst_count = dst_conn.execute(
                select(func.count()).select_from(dst_tables[name])
            ).scalar()
            if dst_count != count:
                print(f"MISMATCH {name}: src={count} dst={dst_count}")
                ok = False
    print("verification:", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
