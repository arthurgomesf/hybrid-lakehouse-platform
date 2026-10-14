#!/usr/bin/env python3
"""Local Bronze / Silver / Gold with polars + Delta Lake (delta-rs), no Spark.

Same rules as the Fabric notebooks in fabric/, so the concepts can be run and
tested on a laptop:

- only runs that have a manifest are read (the manifest is the "run completed"
  marker written last by the exporter);
- lineage comes from the manifest: _run_id, _ingestion_date, _run_started_at;
- runs are ordered by _run_started_at (a timestamp), never by run_id, because
  run ids from different orchestrators are not comparable;
- a control table (ctrl_ingested_runs) records which run each layer already
  loaded, and it is written only when something new was loaded;
- incremental datasets: MERGE by key, updating only when the incoming run is
  newer than the stored row;
- full datasets: the latest complete run replaces the table;
- Silver applies the critical quality rules of the contract (key unique, key
  not null) and refuses to publish when they fail.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl
import yaml
from deltalake import DeltaTable, write_deltalake

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCES = ["pipelines/sources/sap/datasets.yaml", "pipelines/sources/motan/datasets.yaml"]
CTRL_TABLE = "ctrl_ingested_runs"


class QualityError(RuntimeError):
    """A critical quality rule failed; the layer is not published."""


@dataclass(frozen=True)
class Run:
    run_id: str
    ingestion_date: str
    started_at: datetime
    files: dict[str, Path]  # landing_dataset -> parquet file
    landing_paths: dict[str, str]  # landing_dataset -> path relative to the landing root


class Lakehouse:
    def __init__(self, landing: Path, lakehouse: Path) -> None:
        self.landing = landing
        self.root = lakehouse
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, table: str) -> str:
        return str(self.root / table)

    def exists(self, table: str) -> bool:
        return (self.root / table / "_delta_log").exists()

    def read(self, table: str) -> pl.DataFrame:
        return pl.read_delta(self.path(table))

    # ---- control table -------------------------------------------------
    def loaded_runs(self, layer: str, dataset: str) -> set[str]:
        if not self.exists(CTRL_TABLE):
            return set()
        ctrl = self.read(CTRL_TABLE).filter((pl.col("layer") == layer) & (pl.col("dataset") == dataset))
        return set(ctrl["run_id"].to_list())

    def record_runs(self, layer: str, dataset: str, runs: list[Run], counts: dict[str, int]) -> None:
        if not runs:
            return
        now = datetime.now(timezone.utc)
        rows = pl.DataFrame(
            {
                "layer": [layer] * len(runs),
                "dataset": [dataset] * len(runs),
                "run_id": [r.run_id for r in runs],
                "ingestion_date": [r.ingestion_date for r in runs],
                "run_started_at": [r.started_at for r in runs],
                "row_count": [counts.get(r.run_id, 0) for r in runs],
                "ingested_at": [now] * len(runs),
            }
        )
        write_deltalake(self.path(CTRL_TABLE), rows.to_arrow(), mode="append")


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def completed_runs(landing: Path, domain: str, source: str) -> list[Run]:
    runs = []
    for manifest_file in sorted((landing / domain / source / "_manifests").glob("ingestion_date=*/run_id=*/manifest.json")):
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        if manifest.get("status") != "success":
            continue
        runs.append(
            Run(
                run_id=str(manifest["run_id"]),
                ingestion_date=manifest["ingestion_date"],
                started_at=datetime.fromisoformat(manifest["started_at"]),
                files={d["landing_dataset"]: landing / d["landing_path"] for d in manifest["datasets"]},
                landing_paths={d["landing_dataset"]: d["landing_path"] for d in manifest["datasets"]},
            )
        )
    return sorted(runs, key=lambda r: r.started_at)


def with_lineage(frame: pl.DataFrame, run: Run, dataset: str, source: str) -> pl.DataFrame:
    return frame.with_columns(
        pl.lit(run.run_id).alias("_run_id"),
        pl.lit(run.ingestion_date).alias("_ingestion_date"),
        pl.lit(run.started_at).cast(pl.Datetime("us", "UTC")).alias("_run_started_at"),
        pl.lit(run.landing_paths[dataset]).alias("_source_path"),
        pl.lit(source).alias("_source_system"),
    )


def latest_per_key(frame: pl.DataFrame, keys: list[str]) -> pl.DataFrame:
    return frame.sort("_run_started_at", descending=True).unique(subset=keys, keep="first", maintain_order=True)


def check_keys(frame: pl.DataFrame, keys: list[str], table: str) -> None:
    nulls = frame.select(pl.any_horizontal(pl.col(k).is_null() for k in keys).sum()).item()
    dups = frame.height - frame.select(keys).unique().height
    if nulls or dups:
        raise QualityError(f"[{table}] chave {keys}: {nulls} nulas, {dups} duplicadas")


def merge_newer(lake: Lakehouse, table: str, incoming: pl.DataFrame, keys: list[str]) -> None:
    if not lake.exists(table):
        write_deltalake(lake.path(table), incoming.to_arrow(), mode="overwrite")
        return
    predicate = " AND ".join(f"t.{k} = s.{k}" for k in keys)
    (
        DeltaTable(lake.path(table))
        .merge(incoming.to_arrow(), predicate=predicate, source_alias="s", target_alias="t")
        .when_matched_update_all(predicate="s._run_started_at > t._run_started_at")
        .when_not_matched_insert_all()
        .execute()
    )


def load_bronze(lake: Lakehouse, source: str, ds: dict[str, Any], runs: list[Run]) -> str:
    name, table = ds["landing_dataset"], ds["bronze_table"]
    keys, mode = ds["upsert_keys"], ds.get("load_mode", "full")
    done = lake.loaded_runs("bronze", name)
    candidates = [r for r in runs if name in r.files]
    if mode == "full":
        new_runs = candidates[-1:] if candidates and candidates[-1].run_id not in done else []
    else:
        new_runs = [r for r in candidates if r.run_id not in done]
    if not new_runs:
        return f"{table}: nada novo"

    frames = [with_lineage(pl.read_parquet(r.files[name]), r, name, source) for r in new_runs]
    incoming = pl.concat(frames, how="vertical_relaxed").with_columns(
        pl.lit(datetime.now(timezone.utc)).cast(pl.Datetime("us", "UTC")).alias("_bronze_loaded_at")
    )
    counts = {r.run_id: f.height for r, f in zip(new_runs, frames, strict=True)}
    if mode == "full":
        write_deltalake(lake.path(table), incoming.to_arrow(), mode="overwrite", schema_mode="overwrite")
    else:
        merge_newer(lake, table, latest_per_key(incoming, keys), keys)
    lake.record_runs("bronze", name, new_runs, counts)
    return f"{table}: {len(new_runs)} run(s), {incoming.height} linhas ({mode})"


def load_silver(lake: Lakehouse, ds: dict[str, Any]) -> str:
    table = ds.get("silver_table")
    if not table:
        return ""
    bronze = lake.read(ds["bronze_table"])
    keys = ds["upsert_keys"]
    silver = latest_per_key(bronze, keys).drop("_bronze_loaded_at").with_columns(
        pl.lit(datetime.now(timezone.utc)).cast(pl.Datetime("us", "UTC")).alias("_silver_loaded_at")
    )
    check_keys(silver, keys, table)
    if ds.get("load_mode", "full") == "full" or not lake.exists(table):
        write_deltalake(lake.path(table), silver.to_arrow(), mode="overwrite", schema_mode="overwrite")
    else:
        merge_newer(lake, table, silver, keys)
    return f"{table}: {silver.height} linhas"


def dosage_status(variance_percent: pl.Expr, tolerance: float) -> pl.Expr:
    return (
        pl.when(variance_percent.is_null()).then(pl.lit(None, dtype=pl.Utf8))
        .when(variance_percent.abs() <= tolerance).then(pl.lit("WITHIN_TOLERANCE"))
        .when(variance_percent > tolerance).then(pl.lit("OVER_CONSUMPTION"))
        .otherwise(pl.lit("UNDER_CONSUMPTION"))
    )


def build_gold_dosage_control(lake: Lakehouse) -> pl.DataFrame:
    """Gold computed in the lakehouse from Silver (not copied from the on-prem view)."""
    contract = load_yaml(REPO_ROOT / "contracts/data-products/manufacturing/manufacturing-dosage-control.yaml")
    tolerance = float(contract["business_rules"]["dosage_status"]["variance_tolerance_percent"])

    consumption = lake.read("silver_manufacturing_order_consumption")
    orders = lake.read("silver_manufacturing_production_orders")
    windows = consumption.group_by("machine", "order_number").agg(
        pl.col("started_at").min(),
        pl.when(pl.col("ended_at").null_count() == 0).then(pl.col("ended_at").max()).alias("ended_at"),
        pl.col("duration_minutes").sum(),
        pl.col("actual_consumed_total_kg").sum().alias("actual_sum"),
        pl.col("actual_consumed_total_kg").null_count().alias("windows_without_consumption"),
        pl.len().alias("windows_count"),
    )
    gold = (
        windows.join(
            orders.select("order_number", "product_item_code", "product_description", "planned_resin_total_kg", "status", "synced_at"),
            on="order_number",
            how="left",
        )
        .with_columns(
            # all windows without consumption -> no actual (sum of nulls is 0 in polars)
            pl.when(pl.col("windows_without_consumption") == pl.col("windows_count"))
            .then(None).otherwise(pl.col("actual_sum")).alias("actual_consumed_total_kg"),
        )
        .with_columns((pl.col("actual_consumed_total_kg") - pl.col("planned_resin_total_kg")).alias("variance_kg"))
        .with_columns((pl.col("variance_kg") / pl.col("planned_resin_total_kg") * 100).alias("variance_percent"))
        .with_columns(
            pl.when(pl.col("planned_resin_total_kg").is_null()).then(pl.lit("NO_PLAN"))
            .when(pl.col("actual_consumed_total_kg").is_null()).then(pl.lit("NO_ACTUAL_CONSUMPTION"))
            .otherwise(dosage_status(pl.col("variance_percent"), tolerance)).alias("dosage_control_status"),
            pl.col("status").alias("sap_status"),
            pl.col("synced_at").alias("sap_synced_at"),
            pl.lit(datetime.now(timezone.utc)).cast(pl.Datetime("us", "UTC")).alias("_gold_loaded_at"),
        )
        .drop("actual_sum", "status", "synced_at")
        .sort("machine", "started_at")
    )
    check_keys(gold, ["machine", "order_number"], "gold_manufacturing_dosage_control")
    write_deltalake(lake.path("gold_manufacturing_dosage_control"), gold.to_arrow(), mode="overwrite", schema_mode="overwrite")
    return gold


def run(landing: Path, lakehouse: Path, verbose: bool = True) -> dict[str, list[str]]:
    lake = Lakehouse(landing, lakehouse)
    report: dict[str, list[str]] = {}
    silver_changed: set[str] = set()
    for config_file in SOURCES:
        config = load_yaml(REPO_ROOT / config_file)
        source, domain = config["source"]["name"], config["source"]["domain"]
        runs = completed_runs(landing, domain, source)
        lines = [f"{len(runs)} run(s) completos na landing"]
        for ds in config["datasets"]:
            message = load_bronze(lake, source, ds, runs)
            lines.append("bronze " + message)
            # Silver only moves when its Bronze received a new run (or does not exist yet)
            silver = ds.get("silver_table")
            if not silver or not lake.exists(ds["bronze_table"]):
                continue
            if message.endswith("nada novo") and lake.exists(silver):
                lines.append(f"silver {silver}: nada novo")
            else:
                lines.append("silver " + load_silver(lake, ds))
                silver_changed.add(silver)
        report[f"{domain}/{source}"] = lines
    gold_inputs = {"silver_manufacturing_order_consumption", "silver_manufacturing_production_orders"}
    if all(lake.exists(t) for t in gold_inputs):
        if silver_changed & gold_inputs or not lake.exists("gold_manufacturing_dosage_control"):
            gold = build_gold_dosage_control(lake)
            report["gold"] = [f"gold_manufacturing_dosage_control: {gold.height} linhas"]
        else:
            report["gold"] = ["gold_manufacturing_dosage_control: nada novo"]
    if verbose:
        for section, lines in report.items():
            print(f"== {section}")
            for line in lines:
                print("   " + line)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local medallion layers.")
    parser.add_argument("--landing", default="data/landing")
    parser.add_argument("--lakehouse", default="data/lakehouse")
    args = parser.parse_args()
    run(Path(args.landing), Path(args.lakehouse))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
