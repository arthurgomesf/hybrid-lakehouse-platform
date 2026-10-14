#!/usr/bin/env python3
"""Generic source-to-landing exporter.

Reads a source dataset config (`datasets.yaml`), runs each SQL query, writes one
Parquet file per dataset and a manifest per run. The script is
orchestrator-agnostic: Azure DevOps, Airflow or a local shell call the same
entrypoint.

Engines (`source.engine` in the config, or `--engine` to override):
- hana: SAP HANA via ODBC (pyodbc) + HANA_CONNECTION_STRING;
- postgresql: psycopg + DATABASE_URL;
- duckdb: local file (DUCKDB_PATH / --duckdb-path), used by the demo and tests.

Guarantees:
- the Parquet schema comes from the data contract, never from the data of the
  run, so an all-null column keeps its type and an unexpected column fails fast;
- the local layout mirrors the landing layout exactly;
- the manifest is written last and works as the "run completed" marker.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urlsplit, urlunsplit

import polars as pl
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

CONTRACT_TYPES: dict[str, pl.DataType] = {
    "string": pl.Utf8,
    "integer": pl.Int64,
    "decimal": pl.Decimal(38, 6),
    "numeric": pl.Float64,
    "boolean": pl.Boolean,
    "date": pl.Date,
    "timestamp": pl.Datetime("us"),
    "timestamptz": pl.Datetime("us", "UTC"),
    "jsonb": pl.Utf8,
}


class SchemaDriftError(RuntimeError):
    """Query output does not match the contract schema."""


@dataclass(frozen=True)
class DatasetResult:
    name: str
    landing_dataset: str
    contract: str
    load_mode: str
    rows: int
    landing_path: str
    schema: dict[str, str]
    status: str


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export configured source datasets to Parquet landing files.")
    parser.add_argument("--config", required=True, help="Path to datasets.yaml")
    parser.add_argument("--run-id", default=os.getenv("BUILD_BUILDID") or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"))
    parser.add_argument(
        "--ingestion-date",
        default=os.getenv("INGESTION_DATE"),
        help="Partition date (YYYY-MM-DD). Set it once per orchestrator run so task retries reuse the same path.",
    )
    parser.add_argument("--window-days", type=int, default=int(os.environ["WINDOW_DAYS"]) if os.getenv("WINDOW_DAYS") else None)
    parser.add_argument("--start-date", default=os.getenv("START_DATE"))
    parser.add_argument("--engine", default=os.getenv("SOURCE_ENGINE"), help="Override source.engine (hana, postgresql, duckdb)")
    parser.add_argument("--duckdb-path", default=os.getenv("DUCKDB_PATH", "data/sources.duckdb"))
    parser.add_argument("--output-dir", default=os.getenv("OUTPUT_DIR", "data/landing"))
    parser.add_argument("--upload", action="store_true", help="Upload files to Azure Storage using azcopy")
    return parser.parse_args(argv)


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        return yaml.safe_load(file)


def render_sql(text: str, params: dict[str, Any]) -> str:
    """Replace :name placeholders with literals. Unknown names are left untouched."""

    def literal(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in params:
            return match.group(0)
        value = params[name]
        if isinstance(value, bool) or value is None:
            raise ValueError(f"unsupported value for :{name}: {value!r}")
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, (date, datetime)):
            value = value.isoformat()
        return "'" + str(value).replace("'", "''") + "'"

    rendered = re.sub(r"(?<!:):([A-Za-z_]\w*)", literal, text)
    return rendered.rstrip().rstrip(";")


def contract_fields(contract: dict[str, Any], schema_key: str = "schema") -> list[dict[str, Any]]:
    section = contract.get(schema_key)
    if not section or "fields" not in section:
        raise SchemaDriftError(f"contract has no '{schema_key}.fields' section")
    return section["fields"]


def contract_schema(fields: list[dict[str, Any]]) -> dict[str, pl.DataType]:
    schema: dict[str, pl.DataType] = {}
    for field in fields:
        type_name = str(field["type"]).lower()
        if type_name not in CONTRACT_TYPES:
            raise SchemaDriftError(f"unknown contract type '{type_name}' for field '{field['name']}'")
        schema[field["name"]] = CONTRACT_TYPES[type_name]
    return schema


def to_series(name: str, values: list[Any], dtype: pl.DataType) -> pl.Series:
    if dtype == pl.Utf8:
        values = [json.dumps(v, ensure_ascii=False, default=str) if isinstance(v, (dict, list)) else (None if v is None else str(v)) for v in values]
        return pl.Series(name, values, dtype=pl.Utf8)
    series = pl.Series(name, values, strict=False)
    if isinstance(dtype, pl.Datetime) and dtype.time_zone:
        if series.dtype == pl.Null:
            return series.cast(dtype)
        if isinstance(series.dtype, pl.Datetime):
            series = series.dt.replace_time_zone("UTC") if series.dtype.time_zone is None else series.dt.convert_time_zone("UTC")
        return series.cast(dtype)
    return series.cast(dtype, strict=True)


def build_frame(columns: list[str], rows: list[tuple], schema: dict[str, pl.DataType], dataset: str) -> pl.DataFrame:
    """Build the DataFrame with the contract types; fail on any column mismatch."""
    missing = [c for c in schema if c not in columns]
    extra = [c for c in columns if c not in schema]
    if missing or extra:
        raise SchemaDriftError(f"[{dataset}] query x contract: missing={missing} extra={extra}")
    series = [to_series(col, [row[i] for row in rows], schema[col]) for i, col in enumerate(columns)]
    return pl.DataFrame(series)


def resolve_connection_string(engine: str, duckdb_path: str) -> str:
    if engine == "hana":
        value = os.getenv("HANA_CONNECTION_STRING")
        if not value:
            print("HANA_CONNECTION_STRING is required for engine=hana", file=sys.stderr)
            raise SystemExit(1)
        return value
    if engine == "postgresql":
        value = os.getenv("DATABASE_URL")
        if not value:
            print("DATABASE_URL is required for engine=postgresql", file=sys.stderr)
            raise SystemExit(1)
        return value
    if engine == "duckdb":
        if not Path(duckdb_path).exists():
            print(f"duckdb file not found: {duckdb_path} (run scripts/generate_fake_data.py)", file=sys.stderr)
            raise SystemExit(1)
        return duckdb_path
    raise ValueError(f"engine nao suportado: {engine}")


T = TypeVar("T")


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


def is_transient_error(engine: str, exc: BaseException) -> bool:
    try:
        if engine == "hana":
            import pyodbc

            return isinstance(exc, (pyodbc.OperationalError, pyodbc.InterfaceError))
        if engine == "postgresql":
            import psycopg

            return isinstance(exc, (psycopg.OperationalError, psycopg.InterfaceError))
        if engine == "duckdb":
            import duckdb

            return isinstance(exc, duckdb.IOException)
    except ImportError:
        pass
    return False


def retry(engine: str, attempts: int, base_backoff: float, max_total_seconds: float, fn: Callable[[], T]) -> T:
    last_error: BaseException | None = None
    started = time.monotonic()
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:
            last_error = exc
            if not is_transient_error(engine, exc):
                raise
            elapsed = time.monotonic() - started
            wait = min(base_backoff * (2 ** (attempt - 1)), max(0.0, max_total_seconds - elapsed))
            print(f"tentativa {attempt}/{attempts} falhou apos {elapsed:.0f}s: {exc}", file=sys.stderr)
            if attempt < attempts and wait > 0:
                print(f"  aguardando {wait:.0f}s antes da proxima tentativa", file=sys.stderr)
                time.sleep(wait)
    raise RuntimeError(
        f"conexao indisponivel: {last_error} (apos {attempts} tentativas em {time.monotonic() - started:.0f}s)"
    ) from last_error


def connect(engine: str, connection_string: str, timeout: int):
    if engine == "hana":
        import pyodbc

        return pyodbc.connect(connection_string, timeout=timeout)
    if engine == "duckdb":
        import duckdb

        connection = duckdb.connect(connection_string, read_only=True)
        connection.execute("SET TimeZone = 'UTC'")  # timestamps in the fake sources are UTC
        return connection
    import psycopg

    return psycopg.connect(connection_string)


@dataclass
class ConnectionConfig:
    engine: str
    connection_string: str
    connect_timeout: int = 60
    retry_attempts: int = 3
    retry_backoff: float = 5.0
    max_retry_total: float = 90.0


class SourceConnection:
    def __init__(self, config: ConnectionConfig) -> None:
        self.config = config
        self._connection = None

    def get(self):
        if self._connection is None:
            self._connection = retry(
                self.config.engine,
                self.config.retry_attempts,
                self.config.retry_backoff,
                self.config.max_retry_total,
                lambda: connect(self.config.engine, self.config.connection_string, self.config.connect_timeout),
            )
        return self._connection

    def invalidate(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None

    def ping(self) -> None:
        ping_sql = "SELECT 1 FROM DUMMY" if self.config.engine == "hana" else "SELECT 1"

        def _ping():
            cursor = self.get().cursor()
            try:
                cursor.execute(ping_sql)
                cursor.fetchall()
            finally:
                cursor.close()

        retry(self.config.engine, self.config.retry_attempts, self.config.retry_backoff, self.config.max_retry_total, _ping)

    def close(self) -> None:
        self.invalidate()


def read_query(source: SourceConnection, query: str) -> tuple[list[str], list[tuple]]:
    def _run():
        try:
            cursor = source.get().cursor()
            try:
                cursor.execute(query)
                description = cursor.description or []
                columns = [col.name if hasattr(col, "name") else col[0] for col in description]
                rows = cursor.fetchall()
            finally:
                cursor.close()
        except Exception as exc:
            if is_transient_error(source.config.engine, exc):
                source.invalidate()
            raise
        return columns, rows

    return retry(source.config.engine, source.config.retry_attempts, source.config.retry_backoff, source.config.max_retry_total, _run)


def upload_with_azcopy(local_path: Path, destination_url: str) -> None:
    subprocess.run(["azcopy", "copy", str(local_path), destination_url, "--overwrite=true"], check=True)


def storage_destination(base_url: str, relative_path: str) -> str:
    parsed = urlsplit(base_url)
    path = f"{parsed.path.rstrip('/')}/{relative_path.lstrip('/')}"
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))


def landing_path(domain: str, source: str, dataset: str, ingestion_date: str, run_id: str) -> str:
    return f"{domain}/{source}/{dataset}/ingestion_date={ingestion_date}/run_id={run_id}/part-000.parquet"


def manifest_path(domain: str, source: str, ingestion_date: str, run_id: str) -> str:
    return f"{domain}/{source}/_manifests/ingestion_date={ingestion_date}/run_id={run_id}/manifest.json"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = Path(args.config)
    config = load_yaml(config_path)
    defaults = config.get("defaults", {})

    source = config["source"]["name"]
    domain = config["source"]["domain"]
    engine = args.engine or config["source"].get("engine", "postgresql")
    params = {
        "window_days": args.window_days if args.window_days is not None else int(defaults.get("window_days", 7)),
        "start_date": args.start_date or str(defaults.get("start_date", "1900-01-01")),
    }
    storage_base_url = os.getenv("AZURE_STORAGE_LANDING_URL")
    if args.upload and not storage_base_url:
        print("AZURE_STORAGE_LANDING_URL is required when --upload is used", file=sys.stderr)
        return 1

    source_connection = SourceConnection(
        ConnectionConfig(
            engine=engine,
            connection_string=resolve_connection_string(engine, args.duckdb_path),
            connect_timeout=env_int("SOURCE_CONNECT_TIMEOUT", 60),
            retry_attempts=env_int("SOURCE_RETRY_ATTEMPTS", 3),
            retry_backoff=float(os.getenv("SOURCE_RETRY_BACKOFF_SECONDS", "5")),
            max_retry_total=float(os.getenv("SOURCE_MAX_RETRY_TOTAL_SECONDS", "90")),
        )
    )

    print(f"checking source connectivity ({engine})...", file=sys.stderr)
    source_connection.ping()

    started_at = datetime.now(timezone.utc)
    ingestion_date = args.ingestion_date or started_at.date().isoformat()
    output_root = Path(args.output_dir)
    results: list[DatasetResult] = []

    for dataset in config["datasets"]:
        name = dataset["name"]
        landing_dataset = dataset.get("landing_dataset", name)
        contract = load_yaml(REPO_ROOT / dataset["contract"])
        schema = contract_schema(contract_fields(contract, dataset.get("contract_schema", "schema")))
        query = render_sql((config_path.parent / dataset["source_sql"]).read_text(encoding="utf-8"), params)

        columns, rows = read_query(source_connection, query)
        frame = build_frame(columns, rows, schema, name)

        relative = landing_path(domain, source, landing_dataset, ingestion_date, args.run_id)
        local_file = output_root / relative
        local_file.parent.mkdir(parents=True, exist_ok=True)
        frame.write_parquet(local_file)
        if args.upload:
            upload_with_azcopy(local_file, storage_destination(storage_base_url, relative))

        results.append(
            DatasetResult(
                name=name,
                landing_dataset=landing_dataset,
                contract=dataset["contract"],
                load_mode=dataset.get("load_mode", "full"),
                rows=frame.height,
                landing_path=relative,
                schema={col: str(dtype) for col, dtype in frame.schema.items()},
                status="success",
            )
        )
        print(f"exported dataset={name} rows={frame.height} file={local_file}")

    source_connection.close()
    manifest = {
        "run_id": args.run_id,
        "source": source,
        "domain": domain,
        "engine": engine,
        "status": "success",
        "ingestion_date": ingestion_date,
        "params": params,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "datasets": [result.__dict__ for result in results],
    }
    # Written last: consumers only read runs that have a manifest.
    relative_manifest = manifest_path(domain, source, ingestion_date, args.run_id)
    local_manifest = output_root / relative_manifest
    local_manifest.parent.mkdir(parents=True, exist_ok=True)
    local_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.upload:
        upload_with_azcopy(local_manifest, storage_destination(storage_base_url, relative_manifest))

    print(f"manifest={local_manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
