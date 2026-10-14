"""End-to-end: fake sources -> landing -> Bronze -> Silver -> Gold, two waves.

Each test checks one of the edge cases planted by scripts/generate_fake_data.py.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import polars as pl
import pytest
from deltalake import DeltaTable

from local import medallion

ROOT = Path(__file__).resolve().parents[1]
CONTOSO = "SBO_CONTOSO_PRD"


def _python(*args: str) -> None:
    subprocess.run([sys.executable, *args], check=True, cwd=ROOT)


def _export(db: Path, landing: Path, run_id: str, window_days: int) -> None:
    for config in ("pipelines/sources/sap/datasets.yaml", "pipelines/sources/motan/datasets.yaml"):
        _python("pipelines/exporters/source_to_landing.py", "--config", config, "--engine", "duckdb",
                "--duckdb-path", str(db), "--output-dir", str(landing), "--run-id", run_id,
                "--window-days", str(window_days))


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    base = tmp_path_factory.mktemp("demo")
    db, landing, lake = base / "sources.duckdb", base / "landing", base / "lakehouse"
    _python("scripts/generate_fake_data.py", "--path", str(db))

    first_run = (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime("%Y%m%d%H%M%S")
    _export(db, landing, first_run, window_days=400)
    medallion.run(landing, lake, verbose=False)
    first = {
        "invoices": pl.read_delta(str(lake / "silver_finance_purchase_invoices")),
        "service_parquet": next(landing.glob(f"finance/sap/service_invoices/*/run_id={first_run}/*.parquet")),
    }

    _python("scripts/generate_fake_data.py", "--path", str(db), "--simulate-changes")
    second_run = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    _export(db, landing, second_run, window_days=7)
    medallion.run(landing, lake, verbose=False)

    return {"db": db, "landing": landing, "lake": lake, "first": first, "second_run": second_run}


def table(env, name: str) -> pl.DataFrame:
    return pl.read_delta(str(env["lake"] / name))


def source(env, sql: str):
    with duckdb.connect(str(env["db"]), read_only=True) as con:
        return con.execute(sql).fetchall()


@pytest.mark.parametrize(
    "name,keys",
    [
        ("silver_finance_purchase_invoices", ["doc_entry"]),
        ("silver_finance_return_transfers", ["doc_entry", "line_num"]),
        ("silver_finance_service_invoices", ["company", "doc_entry"]),
        ("silver_manufacturing_order_consumption", ["machine", "order_number", "started_at"]),
        ("gold_manufacturing_dosage_control", ["machine", "order_number"]),
    ],
)
def test_keys_are_unique_and_not_null(env, name, keys):
    frame = table(env, name)
    assert frame.height > 0
    assert frame.select(keys).unique().height == frame.height
    assert frame.select(pl.any_horizontal(pl.col(k).is_null() for k in keys).sum()).item() == 0


def test_incremental_merge_brings_edits_and_cancellation(env):
    before = env["first"]["invoices"].select("doc_entry", "document_total", "is_cancelled")
    after = table(env, "silver_finance_purchase_invoices").select("doc_entry", "document_total", "is_cancelled", "_run_id")
    changed = after.join(before, on="doc_entry", suffix="_before").filter(
        (pl.col("document_total") != pl.col("document_total_before")) | (pl.col("is_cancelled") != pl.col("is_cancelled_before"))
    )
    assert changed.height == 4  # 3 edited totals + 1 cancellation
    assert changed["_run_id"].unique().to_list() == [env["second_run"]]
    assert changed.filter(pl.col("is_cancelled")).height == 1
    assert after.height == before.height + 2  # two new invoices


def test_old_invoice_edited_recently_is_captured_by_update_date(env):
    row = table(env, "silver_finance_purchase_invoices").filter(pl.col("doc_entry") == 7).row(0, named=True)
    assert row["updated_date"] > row["posting_date"]


def test_rerun_without_new_runs_is_idempotent(env):
    lake = env["lake"]
    versions = {p.name: DeltaTable(str(p)).version() for p in lake.iterdir()}
    report = medallion.run(env["landing"], lake, verbose=False)
    assert all("nada novo" in line for line in report["finance/sap"] if line.startswith("bronze"))
    assert DeltaTable(str(lake / "ctrl_ingested_runs")).version() == versions["ctrl_ingested_runs"]
    for bronze in ("bronze_sap_purchase_invoices", "bronze_sap_service_invoices", "bronze_motan_order_context"):
        assert DeltaTable(str(lake / bronze)).version() == versions[bronze]


def test_csrf_keeps_decimal_type_when_all_null(env):
    first = pl.read_parquet(env["first"]["service_parquet"])
    assert first["csrf_amount"].null_count() == first.height  # no CSRF in the first wave
    assert first.schema["csrf_amount"] == pl.Decimal(38, 6)
    silver = table(env, "silver_finance_service_invoices")
    assert silver["csrf_amount"].drop_nulls().len() == 1


def test_unmapped_withholding_code_is_ignored(env):
    silver = table(env, "silver_finance_service_invoices").filter(pl.col("company") == "CONTOSO")
    total_withheld = silver.select(
        pl.sum_horizontal(pl.col(c).fill_null(0) for c in
                          ["inss_amount", "irrf_amount", "pis_amount", "cofins_amount", "csll_amount", "csrf_amount"]).sum()
    ).item()
    mapped = source(env, f"""
        SELECT SUM(W."WTAmnt") FROM {CONTOSO}.PCH5 W JOIN {CONTOSO}.OPCH H ON H."DocEntry" = W."AbsEntry"
        WHERE W."WTCode" <> 'WT-OUTRO' AND W."Category" = 'I' AND H."DocDate" >= DATE '2026-01-01'
          AND EXISTS (SELECT 1 FROM {CONTOSO}.PCH1 L WHERE L."DocEntry" = W."AbsEntry" AND L."CFOPCode" IN ('1933','2933'))""")[0][0]
    assert float(total_withheld) == pytest.approx(float(mapped), abs=0.01)


def test_missing_vendor_tax_id_is_null_not_placeholder(env):
    silver = table(env, "silver_finance_service_invoices")
    assert silver["vendor_tax_id"].null_count() > 0
    assert silver.filter(pl.col("vendor_tax_id").is_in(["", "N/A", "NA"])).height == 0


def test_transfers_with_other_base_type_are_not_linked(env):
    decoy_only = source(env, f"""
        SELECT COUNT(*) FROM {CONTOSO}.WTR1 D
        WHERE D."BaseType" = 67 AND NOT EXISTS (
            SELECT 1 FROM {CONTOSO}.WTR1 R
            WHERE R."BaseType" = 1250000001 AND R."BaseEntry" = D."BaseEntry" AND R."BaseLine" = D."BaseLine")""")[0][0]
    assert decoy_only > 0
    silver = table(env, "silver_finance_return_transfers")
    linked = source(env, f"""
        SELECT COUNT(*) FROM {CONTOSO}.WTR1 W
        JOIN {CONTOSO}.WTQ1 Q ON Q."DocEntry" = W."BaseEntry" AND Q."LineNum" = W."BaseLine"
        JOIN {CONTOSO}.OWTQ H ON H."DocEntry" = Q."DocEntry"
        JOIN {CONTOSO}.OWTR T ON T."DocEntry" = W."DocEntry"
        WHERE W."BaseType" = 1250000001 AND Q."LineStatus" = 'O' AND H."CANCELED" = 'N'
          AND T."CANCELED" = 'N' AND H."CreateDate" >= DATE '2026-01-01'""")[0][0]
    assert silver["transfer_count"].sum() == linked
    assert silver.filter(pl.col("lead_time_days") < 0).height == 0


def test_gold_matches_on_prem_reference_view(env):
    """Parity: the Gold computed in the lakehouse equals the on-prem view it replaces."""
    gold = table(env, "gold_manufacturing_dosage_control")
    reference = table(env, "bronze_motan_order_plan_vs_actual_reference")
    joined = gold.join(reference, on=["machine", "order_number"], suffix="_ref")
    assert joined.height == reference.height
    for column in ("actual_consumed_total_kg", "planned_resin_total_kg", "variance_kg"):
        diff = joined.select((pl.col(column) - pl.col(f"{column}_ref")).abs().max()).item()
        assert diff is None or diff < 1e-6, column
    assert set(gold["dosage_control_status"].unique()) <= {
        "NO_ACTUAL_CONSUMPTION", "NO_PLAN", "WITHIN_TOLERANCE", "OVER_CONSUMPTION", "UNDER_CONSUMPTION"}


def test_inspect_lakehouse_script(env, tmp_path):
    def inspect(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "scripts/inspect_lakehouse.py", "--lakehouse", str(env["lake"]), *args],
                              cwd=ROOT, capture_output=True, encoding="utf-8")

    overview = inspect()
    assert overview.returncode == 0, overview.stderr
    assert "gold_manufacturing_dosage_control" in overview.stdout
    assert env["second_run"] in overview.stdout

    one = inspect("--table", "silver_finance_purchase_invoices", "--rows", "3")
    assert one.returncode == 0, one.stderr
    assert "doc_entry" in one.stdout
    assert inspect("--table", "does_not_exist").returncode == 1

    empty = subprocess.run([sys.executable, "scripts/inspect_lakehouse.py", "--lakehouse", str(tmp_path / "none")],
                           cwd=ROOT, capture_output=True, encoding="utf-8")
    assert empty.returncode == 1
    assert "run_demo.py" in empty.stdout
