#!/usr/bin/env python3
"""End-to-end demo with fictitious data, no cloud connection needed.

1. generate the fake sources (DuckDB);
2. first export: backfill of the incremental datasets + full snapshots;
3. load Bronze / Silver / Gold;
4. change the sources (edits, a cancellation, new documents, first CSRF);
5. second export with the normal 7-day window;
6. load again: MERGE brings only the changes;
7. load a third time with nothing new: idempotent, nothing changes.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DUCKDB = DATA / "sources.duckdb"
LANDING = DATA / "landing"
LAKEHOUSE = DATA / "lakehouse"

sys.path.insert(0, str(ROOT))
from local import medallion  # noqa: E402


def step(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def run(*args: str) -> None:
    subprocess.run([sys.executable, *args], check=True, cwd=ROOT)


def export(run_id: str, window_days: int) -> None:
    for config in ("pipelines/sources/sap/datasets.yaml", "pipelines/sources/motan/datasets.yaml"):
        run(
            "pipelines/exporters/source_to_landing.py",
            "--config", config,
            "--engine", "duckdb",
            "--duckdb-path", str(DUCKDB),
            "--output-dir", str(LANDING),
            "--run-id", run_id,
            "--window-days", str(window_days),
        )


def main() -> int:
    for path in (LANDING, LAKEHOUSE):
        shutil.rmtree(path, ignore_errors=True)

    step("1. Gerando fontes ficticias (SAP B1 + Motan) em DuckDB")
    run("scripts/generate_fake_data.py", "--path", str(DUCKDB))

    first = datetime.now(timezone.utc) - timedelta(minutes=1)
    step("2. Export inicial (backfill de 400 dias)")
    export(first.strftime("%Y%m%d%H%M%S"), window_days=400)

    step("3. Bronze / Silver / Gold - primeira carga")
    medallion.run(LANDING, LAKEHOUSE)

    step("4. Mudancas na fonte: edicoes, cancelamento, documentos novos, primeiro CSRF")
    run("scripts/generate_fake_data.py", "--path", str(DUCKDB), "--simulate-changes")

    step("5. Export incremental (janela de 7 dias)")
    export(datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"), window_days=7)

    step("6. Bronze / Silver / Gold - so as mudancas entram")
    medallion.run(LANDING, LAKEHOUSE)

    step("7. Rodando de novo sem run novo - nada deve mudar")
    medallion.run(LANDING, LAKEHOUSE)

    print(f"\nPronto. Landing em {LANDING}, tabelas Delta em {LAKEHOUSE}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
