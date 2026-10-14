from datetime import datetime, timezone
from decimal import Decimal

import polars as pl
import pytest

from pipelines.exporters.source_to_landing import (
    SchemaDriftError,
    build_frame,
    contract_schema,
    landing_path,
    manifest_path,
    render_sql,
)


def test_render_sql_replaces_known_params_with_literals():
    sql = "SELECT * FROM t WHERE d >= ADD_DAYS(CURRENT_DATE, -:window_days) AND c >= :start_date;"
    assert render_sql(sql, {"window_days": 7, "start_date": "2026-01-01"}) == (
        "SELECT * FROM t WHERE d >= ADD_DAYS(CURRENT_DATE, -7) AND c >= '2026-01-01'"
    )


def test_render_sql_keeps_casts_and_unknown_names():
    sql = "SELECT x::date, :other FROM t WHERE n = :window_days"
    assert render_sql(sql, {"window_days": 3}) == "SELECT x::date, :other FROM t WHERE n = 3"


def test_render_sql_escapes_quotes():
    assert render_sql("WHERE a = :start_date", {"start_date": "x'y"}) == "WHERE a = 'x''y'"


SCHEMA = contract_schema(
    [
        {"name": "id", "type": "integer"},
        {"name": "amount", "type": "decimal"},
        {"name": "seen_at", "type": "timestamptz"},
        {"name": "payload", "type": "jsonb"},
    ]
)


def test_all_null_column_keeps_contract_type():
    frame = build_frame(["id", "amount", "seen_at", "payload"], [(1, None, None, None), (2, None, None, None)], SCHEMA, "t")
    assert frame.schema["amount"] == pl.Decimal(38, 6)
    assert frame.schema["seen_at"] == pl.Datetime("us", "UTC")


def test_values_are_cast_to_contract_types():
    naive = datetime(2026, 10, 1, 12, 0)
    frame = build_frame(["id", "amount", "seen_at", "payload"], [(1, Decimal("10.5"), naive, {"a": 1})], SCHEMA, "t")
    row = frame.row(0, named=True)
    assert row["amount"] == Decimal("10.500000")
    assert row["seen_at"] == naive.replace(tzinfo=timezone.utc)
    assert row["payload"] == '{"a": 1}'


def test_extra_column_is_schema_drift():
    with pytest.raises(SchemaDriftError, match="extra=\\['surprise'\\]"):
        build_frame(["id", "amount", "seen_at", "payload", "surprise"], [], SCHEMA, "t")


def test_missing_column_is_schema_drift():
    with pytest.raises(SchemaDriftError, match="missing=\\['payload'\\]"):
        build_frame(["id", "amount", "seen_at"], [], SCHEMA, "t")


def test_local_layout_mirrors_landing():
    assert landing_path("finance", "sap", "purchase_invoices", "2026-10-14", "42") == (
        "finance/sap/purchase_invoices/ingestion_date=2026-10-14/run_id=42/part-000.parquet"
    )
    assert manifest_path("finance", "sap", "2026-10-14", "42") == (
        "finance/sap/_manifests/ingestion_date=2026-10-14/run_id=42/manifest.json"
    )
