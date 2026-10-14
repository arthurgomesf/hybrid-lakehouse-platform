#!/usr/bin/env python3
"""Show what is inside the local lakehouse produced by run_demo.py.

Without arguments: tables per layer with row/column counts, the runs recorded in
the control table (backfill + incremental) and a sample of the Gold table.
With `--table NAME`: schema and first rows of one table.

Read-only: nothing in the lakehouse is changed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from local.medallion import CTRL_TABLE, Lakehouse  # noqa: E402

GOLD_TABLE = "gold_manufacturing_dosage_control"
# column -> short label, so the sample fits in a normal terminal
GOLD_COLUMNS = {"machine": "machine", "order_number": "order", "product_item_code": "item",
                "planned_resin_total_kg": "planned_kg", "actual_consumed_total_kg": "actual_kg",
                "variance_percent": "variance_%", "dosage_control_status": "status"}
LAYERS = ["bronze", "silver", "gold", "ctrl"]


def title(text: str) -> None:
    print(f"\n{'=' * 70}\n{text}\n{'=' * 70}")


def table_names(lakehouse: Path) -> list[str]:
    return sorted(p.name for p in lakehouse.iterdir() if (p / "_delta_log").exists())


def overview(lake: Lakehouse, names: list[str]) -> None:
    title("Tabelas por camada")
    rows = []
    for name in names:
        frame = lake.read(name)
        rows.append({"camada": name.split("_", 1)[0], "tabela": name, "linhas": frame.height, "colunas": frame.width})
    summary = pl.DataFrame(rows).sort(pl.col("camada").replace_strict(LAYERS, list(range(len(LAYERS))), default=len(LAYERS)), "tabela")
    print(summary)

    if lake.exists(CTRL_TABLE):
        title("Runs carregados (ctrl_ingested_runs)")
        ctrl = lake.read(CTRL_TABLE)
        print(ctrl.group_by("run_id").agg(
            pl.col("run_started_at").min().alias("run_started_at"),
            pl.len().alias("datasets"),
            pl.col("row_count").sum().alias("linhas"),
        ).sort("run_id"))
        print("O primeiro run e o backfill; o segundo e o incremental (so as mudancas).")

    if lake.exists(GOLD_TABLE):
        gold = lake.read(GOLD_TABLE)
        title(f"Gold: {GOLD_TABLE}")
        print(gold.group_by("dosage_control_status").agg(pl.len().alias("ordens")).sort("ordens", descending=True))
        sample = gold.sort("machine", "order_number").head(10).select(list(GOLD_COLUMNS)).rename(GOLD_COLUMNS)
        print(sample.with_columns(pl.col("variance_%").round(2)))

    print("\nPara ver uma tabela: python scripts/inspect_lakehouse.py --table <nome>")


def show_table(lake: Lakehouse, name: str, rows: int) -> None:
    frame = lake.read(name)
    title(f"{name}: {frame.height} linhas, {frame.width} colunas")
    for column, dtype in frame.schema.items():
        print(f"  {column}: {dtype}")
    print()
    print(frame.head(rows))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lakehouse", default=str(ROOT / "data" / "lakehouse"))
    parser.add_argument("--table", help="Show schema and first rows of this table")
    parser.add_argument("--rows", type=int, default=10, help="Rows to show with --table")
    args = parser.parse_args()

    # Windows terminals default to cp1252, which cannot print polars' table borders.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    pl.Config.set_tbl_rows(50)
    pl.Config.set_tbl_cols(10)
    pl.Config.set_fmt_str_lengths(40)

    lakehouse = Path(args.lakehouse)
    names = table_names(lakehouse) if lakehouse.is_dir() else []
    if not names:
        print(f"Nenhuma tabela Delta em {lakehouse}. Rode `python run_demo.py` primeiro.")
        return 1
    lake = Lakehouse(lakehouse.parent / "landing", lakehouse)

    if args.table is None:
        overview(lake, names)
        return 0
    if args.table not in names:
        print(f"Tabela '{args.table}' nao existe. Tabelas disponiveis:")
        for name in names:
            print(f"  {name}")
        return 1
    show_table(lake, args.table, args.rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
