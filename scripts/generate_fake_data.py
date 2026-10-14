#!/usr/bin/env python3
"""Generate a local DuckDB database that mimics the platform sources.

Everything here is fictitious: companies (CONTOSO, FABRIKAM), vendors, tax ids,
items, machines and production orders. Dates are relative to "today" so the
moving-window extractions always find data.

Schemas:
- SBO_CONTOSO_PRD / SBO_FABRIKAM_PRD: the SAP Business One tables used by the
  finance SQL (OPCH, PCH1, PCH4, PCH5, PCH12, OSTT, OWTQ, WTQ1, OWTR, WTR1);
- public: the Motan data-collector views (order windows, consumption, SAP plan
  cache and the consolidated plan-vs-actual reference view).

HANA compatibility: DUMMY table and ADD_DAYS / DAYS_BETWEEN macros, so the same
SQL files run on SAP HANA and here.

Edge cases planted on purpose (the tests rely on them):
- cancelled invoices and invoices edited long after posting;
- a withholding code that is not mapped (must be ignored);
- no CSRF withholding at all in the first load (all-null column);
- transfers whose BaseType is not a transfer request (must not be linked);
- request lines with more than one transfer;
- service invoices without vendor tax id;
- production orders without SAP plan and windows without consumption.

`--simulate-changes` applies a second wave of changes to an existing database,
used by the demo to show incremental loads and MERGE.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb

COMPANIES = {"CONTOSO": "SBO_CONTOSO_PRD", "FABRIKAM": "SBO_FABRIKAM_PRD"}
SERVICE_CFOPS = ["1933", "2933"]
GOODS_CFOPS = ["1102", "2102"]
TRANSFER_REQUEST_OBJECT = 1250000001
VENDORS = [
    "Alfa Servicos Tecnicos", "Beta Manutencao Industrial", "Gama Consultoria", "Delta Logistica",
    "Epsilon Engenharia", "Zeta Limpeza e Conservacao", "Eta Seguranca Patrimonial", "Teta Tecnologia",
    "Iota Calibracao", "Kappa Transportes", "Lambda Assessoria Contabil", "Mu Treinamentos",
    "Nu Locacao de Equipamentos", "Xi Automacao", "Omicron Ambiental", "Pi Juridico",
]
BRANCHES = ["Matriz", "Filial Norte", "Filial Sul"]
ITEMS = ["RES-PP-001", "RES-PE-002", "MB-AZUL-010", "MB-PRETO-011", "ADT-UV-020", "EMB-CX-100"]
WAREHOUSES = ["ALM01", "ALM02", "DEV01", "PRD01"]
MACHINES = ["DOSER-01", "DOSER-02"]
PRODUCTS = [("PA-1001", "Tampa 28mm"), ("PA-1002", "Pote 500ml"), ("PA-1003", "Balde 3L"), ("PA-1004", "Frasco 1L")]


def fake_tax_id(rng: random.Random) -> str:
    # 'ZZ' prefix keeps it obviously fictitious (not a valid Brazilian tax id).
    return f"ZZ.{rng.randint(100, 999)}.{rng.randint(100, 999)}/0001-00"


def money(value: float) -> float:
    return round(value, 2)


def create_compat(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE OR REPLACE TABLE DUMMY (DUMMY VARCHAR)")
    con.execute("INSERT INTO DUMMY VALUES ('X')")
    con.execute("CREATE OR REPLACE MACRO ADD_DAYS(d, n) AS CAST(d AS DATE) + CAST(n AS INTEGER)")
    con.execute("CREATE OR REPLACE MACRO DAYS_BETWEEN(a, b) AS date_diff('day', CAST(a AS DATE), CAST(b AS DATE))")


def create_sap_schema(con: duckdb.DuckDBPyConnection, schema: str, with_transfers: bool) -> None:
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    ddl = {
        "OPCH": '"DocEntry" INTEGER, "DocNum" INTEGER, "DocDate" DATE, "TaxDate" DATE, "UpdateDate" DATE, '
        '"CreateDate" DATE, "CardCode" VARCHAR, "CardName" VARCHAR, "BPLName" VARCHAR, "Serial" INTEGER, '
        '"DocTotal" DECIMAL(19,6), "CANCELED" VARCHAR, "DocStatus" VARCHAR',
        "PCH1": '"DocEntry" INTEGER, "LineNum" INTEGER, "LineTotal" DECIMAL(19,6), "CFOPCode" VARCHAR, '
        '"BaseType" INTEGER, "BaseEntry" INTEGER, "BaseRef" VARCHAR',
        "PCH4": '"DocEntry" INTEGER, "LineNum" INTEGER, "staType" INTEGER, "TaxSum" DECIMAL(19,6)',
        "PCH5": '"AbsEntry" INTEGER, "WTCode" VARCHAR, "WTAmnt" DECIMAL(19,6), "Category" VARCHAR',
        "PCH12": '"DocEntry" INTEGER, "TaxId0" VARCHAR, "TaxId4" VARCHAR',
        "OSTT": '"AbsId" INTEGER, "Name" VARCHAR',
    }
    if with_transfers:
        ddl |= {
            "OWTQ": '"DocEntry" INTEGER, "DocNum" INTEGER, "CANCELED" VARCHAR, "DocStatus" VARCHAR, '
            '"DocDate" DATE, "CreateDate" DATE, "BPLName" VARCHAR',
            "WTQ1": '"DocEntry" INTEGER, "LineNum" INTEGER, "ItemCode" VARCHAR, "Quantity" DECIMAL(19,6), '
            '"OpenQty" DECIMAL(19,6), "Price" DECIMAL(19,6), "FromWhsCod" VARCHAR, "WhsCode" VARCHAR, "LineStatus" VARCHAR',
            "OWTR": '"DocEntry" INTEGER, "DocNum" INTEGER, "CANCELED" VARCHAR, "DocStatus" VARCHAR, "CreateDate" DATE, "BPLName" VARCHAR',
            "WTR1": '"DocEntry" INTEGER, "LineNum" INTEGER, "BaseType" INTEGER, "BaseEntry" INTEGER, "BaseLine" INTEGER, '
            '"ItemCode" VARCHAR, "Quantity" DECIMAL(19,6)',
        }
    for table, columns in ddl.items():
        con.execute(f"CREATE OR REPLACE TABLE {schema}.{table} ({columns})")
    con.executemany(f"INSERT INTO {schema}.OSTT VALUES (?, ?)", [(1, "ISS"), (2, "ICMS"), (3, "IPI")])


def insert_invoice(con, schema: str, rng: random.Random, doc_entry: int, doc_date: date, today: date,
                   company: str, allow_csrf: bool) -> None:
    vendor_idx = rng.randrange(len(VENDORS))
    is_service = rng.random() < 0.45
    lines = []
    for line_num in range(rng.randint(1, 3)):
        total = money(rng.uniform(300, 25000))
        cfop = rng.choice(SERVICE_CFOPS if is_service else GOODS_CFOPS)
        has_po = rng.random() < 0.6
        lines.append((doc_entry, line_num, total, cfop, 22 if has_po else -1,
                      rng.randint(1000, 1999) if has_po else None,
                      str(rng.randint(4000, 4999)) if has_po else None))
    lines_total = sum(line[2] for line in lines)

    withholdings: list[tuple] = []
    if is_service:
        if rng.random() < 0.6:
            withholdings.append((doc_entry, "WT-IRRF", money(lines_total * 0.015), "I"))
        if rng.random() < 0.4:
            withholdings += [
                (doc_entry, "WT-PIS", money(lines_total * 0.0065), "I"),
                (doc_entry, "WT-COF", money(lines_total * 0.03), "I"),
                (doc_entry, "WT-CSL", money(lines_total * 0.01), "I"),
            ]
        if rng.random() < 0.2:
            withholdings.append((doc_entry, "WT-INSS", money(lines_total * 0.11), "I"))
        if rng.random() < 0.1:
            withholdings.append((doc_entry, "WT-OUTRO", money(lines_total * 0.02), "I"))  # unmapped code
        if allow_csrf and rng.random() < 0.3:
            withholdings.append((doc_entry, "WT-CSRF", money(lines_total * 0.0465), "I"))
        if rng.random() < 0.1:
            withholdings.append((doc_entry, "WT-IRRF", money(lines_total * 0.015), "P"))  # not withheld at source

    update_date = min(doc_date + timedelta(days=rng.randint(0, 5)), today)
    cancelled = rng.random() < 0.04
    con.execute(
        f"INSERT INTO {schema}.OPCH VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (doc_entry, 50000 + doc_entry, doc_date, doc_date - timedelta(days=rng.randint(0, 3)), update_date, doc_date,
         f"F{vendor_idx:04d}", VENDORS[vendor_idx], rng.choice(BRANCHES), rng.randint(1000, 99999),
         money(lines_total * (1 if rng.random() < 0.9 else 1.05)), "Y" if cancelled else "N", "C" if cancelled else "O"),
    )
    con.executemany(f"INSERT INTO {schema}.PCH1 VALUES (?, ?, ?, ?, ?, ?, ?)", lines)
    if withholdings:
        con.executemany(f"INSERT INTO {schema}.PCH5 VALUES (?, ?, ?, ?)", withholdings)
    if is_service and rng.random() < 0.7:
        con.execute(f"INSERT INTO {schema}.PCH4 VALUES (?, 0, 1, ?)", (doc_entry, money(lines_total * 0.05)))
    if not is_service:
        con.execute(f"INSERT INTO {schema}.PCH4 VALUES (?, 0, 2, ?)", (doc_entry, money(lines_total * 0.18)))
    tax_id = fake_tax_id(rng) if rng.random() < 0.9 else rng.choice([None, ""])
    con.execute(f"INSERT INTO {schema}.PCH12 VALUES (?, ?, NULL)", (doc_entry, tax_id))


def generate_sap(con, rng: random.Random, today: date) -> None:
    start = date(today.year, 1, 2)
    for company, schema in COMPANIES.items():
        create_sap_schema(con, schema, with_transfers=(company == "CONTOSO"))
        span = (today - start).days
        for doc_entry in range(1, 221):
            doc_date = start + timedelta(days=rng.randint(0, span))
            insert_invoice(con, schema, rng, doc_entry, doc_date, today, company, allow_csrf=False)
        # an invoice edited long after posting: only an UpdateDate watermark catches it
        con.execute(f'UPDATE {schema}.OPCH SET "UpdateDate" = ? WHERE "DocEntry" = 7', (today - timedelta(days=1),))

    schema = COMPANIES["CONTOSO"]
    transfer_entry = 0
    for doc_entry in range(1, 121):
        created = start + timedelta(days=rng.randint(0, (today - start).days))
        line_status = []
        for line_num in range(rng.randint(1, 3)):
            qty = float(rng.randint(10, 500))
            is_open = rng.random() < 0.7
            line_status.append(is_open)
            con.execute(
                f"INSERT INTO {schema}.WTQ1 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (doc_entry, line_num, rng.choice(ITEMS), qty, qty if is_open else 0.0, money(rng.uniform(5, 80)),
                 rng.choice(WAREHOUSES), "DEV01", "O" if is_open else "C"),
            )
            for _ in range(rng.choices([0, 1, 2], weights=[4, 5, 1])[0]):
                transfer_entry += 1
                when = min(created + timedelta(days=rng.randint(0, 10)), today)
                con.execute(f"INSERT INTO {schema}.OWTR VALUES (?, ?, 'N', 'C', ?, ?)",
                            (transfer_entry, 80000 + transfer_entry, when, rng.choice(BRANCHES)))
                con.execute(f"INSERT INTO {schema}.WTR1 VALUES (?, 0, ?, ?, ?, ?, ?)",
                            (transfer_entry, TRANSFER_REQUEST_OBJECT, doc_entry, line_num, rng.choice(ITEMS), qty))
        con.execute(
            f"INSERT INTO {schema}.OWTQ VALUES (?, ?, ?, ?, ?, ?, ?)",
            (doc_entry, 70000 + doc_entry, "Y" if rng.random() < 0.03 else "N",
             "O" if any(line_status) else "C", created, created, rng.choice(BRANCHES)),
        )
    # decoys: transfers based on another object type that share DocEntry/LineNum
    for doc_entry in range(1, 16):
        transfer_entry += 1
        con.execute(f"INSERT INTO {schema}.OWTR VALUES (?, ?, 'N', 'C', ?, 'Matriz')",
                    (transfer_entry, 80000 + transfer_entry, today - timedelta(days=200)))
        con.execute(f"INSERT INTO {schema}.WTR1 VALUES (?, 0, 67, ?, 0, 'RES-PP-001', 1)", (transfer_entry, doc_entry))


def generate_motan(con, rng: random.Random, now: datetime) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS public")
    con.execute("""CREATE OR REPLACE TABLE public.vw_order_number_changes (
        machine VARCHAR, order_number VARCHAR, started_at TIMESTAMP, next_order_started_at TIMESTAMP, duration_minutes DOUBLE)""")
    con.execute("""CREATE OR REPLACE TABLE public.vw_order_actual_consumption_total (
        machine VARCHAR, order_number VARCHAR, started_at TIMESTAMP, ended_at TIMESTAMP, duration_minutes DOUBLE,
        actual_consumed_total_kg DOUBLE, actual_coverage DOUBLE)""")
    con.execute("""CREATE OR REPLACE TABLE public.sap_production_orders (
        order_number VARCHAR, sap_abs_entry INTEGER, sap_document_number INTEGER, status VARCHAR,
        product_item_code VARCHAR, product_description VARCHAR, planned_quantity DOUBLE, completed_quantity DOUBLE,
        planned_resin_total_kg DOUBLE, resin_filter_applied VARCHAR, start_date DATE, due_date DATE,
        raw_data JSON, synced_at TIMESTAMP, created_at TIMESTAMP)""")
    con.execute("""CREATE OR REPLACE TABLE public.sap_production_order_components (
        order_number VARCHAR, line_number INTEGER, item_code VARCHAR, item_description VARCHAR,
        planned_quantity DOUBLE, issued_quantity DOUBLE, warehouse VARCHAR, uom VARCHAR,
        included_in_resin_total BOOLEAN, raw_data JSON, synced_at TIMESTAMP, created_at TIMESTAMP)""")

    order_seq = 30000
    naive_now = now.replace(tzinfo=None, microsecond=0)
    for machine in MACHINES:
        cursor = naive_now - timedelta(days=10)
        previous_order = None
        while cursor < naive_now - timedelta(hours=3):
            # 20% of the time the same order comes back in a second window
            if previous_order and rng.random() < 0.2:
                order = previous_order
            else:
                order_seq += 1
                order = f"OP-{order_seq}"
            hours = rng.uniform(2, 10)
            end = min(cursor + timedelta(hours=hours), naive_now)
            is_last = end >= naive_now - timedelta(hours=3)
            next_start = None if is_last else end
            duration = round(((end if next_start else naive_now) - cursor).total_seconds() / 60, 1)
            con.execute("INSERT INTO public.vw_order_number_changes VALUES (?, ?, ?, ?, ?)",
                        (machine, order, cursor, next_start, duration))
            consumed = None if rng.random() < 0.08 else round(hours * rng.uniform(18, 26), 3)
            con.execute("INSERT INTO public.vw_order_actual_consumption_total VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (machine, order, cursor, next_start, duration, consumed,
                         None if consumed is None else round(rng.uniform(0.85, 1.0), 3)))
            previous_order = order
            cursor = end

    orders = [row[0] for row in con.execute("SELECT DISTINCT order_number FROM public.vw_order_number_changes ORDER BY 1").fetchall()]
    for order in orders:
        if rng.random() < 0.1:
            continue  # order observed on the machine but without SAP plan
        code, description = rng.choice(PRODUCTS)
        consumed = con.execute(
            "SELECT COALESCE(SUM(actual_consumed_total_kg), 0) FROM public.vw_order_actual_consumption_total WHERE order_number = ?",
            (order,)).fetchone()[0]
        planned = round(max(consumed, 50) * rng.uniform(0.9, 1.1), 3)
        start = (naive_now - timedelta(days=rng.randint(5, 12))).date()
        synced = naive_now - timedelta(hours=rng.randint(1, 48))
        raw = {"DocumentNumber": int(order[3:]), "ItemNo": code, "Status": "boposReleased"}
        con.execute("INSERT INTO public.sap_production_orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (order, int(order[3:]) + 100000, int(order[3:]), "R", code, description, float(rng.randint(500, 5000)),
                     float(rng.randint(0, 500)), planned, "group_not_packaging_or_components", start,
                     start + timedelta(days=14), json.dumps(raw), synced, synced - timedelta(days=2)))
        for line, (item, share, included) in enumerate([("RES-PP-001", 0.97, True), ("MB-AZUL-010", 0.03, True), ("EMB-CX-100", 0, False)]):
            con.execute("INSERT INTO public.sap_production_order_components VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (order, line, item, item, round(planned * share, 3) if share else 120.0, 0.0, "PRD01",
                         "kg" if share else "un", included, json.dumps({"ItemNo": item}), synced, synced - timedelta(days=2)))

    con.execute("""
    CREATE OR REPLACE VIEW public.vw_order_plan_vs_actual_consolidated AS
    WITH windows AS (
        SELECT machine, order_number,
               MIN(started_at) AS started_at,
               CASE WHEN COUNT(*) = COUNT(ended_at) THEN MAX(ended_at) END AS ended_at,
               SUM(duration_minutes) AS duration_minutes,
               SUM(actual_consumed_total_kg) AS actual_consumed_total_kg,
               COUNT(*) AS windows_count,
               COUNT(*) - COUNT(actual_consumed_total_kg) AS windows_without_consumption
        FROM public.vw_order_actual_consumption_total
        GROUP BY machine, order_number
    )
    SELECT w.machine, w.order_number, w.started_at, w.ended_at, w.duration_minutes,
           o.status AS sap_status,
           CASE o.status WHEN 'R' THEN 'Released' WHEN 'P' THEN 'Planned' WHEN 'L' THEN 'Closed' END AS sap_status_description,
           o.status = 'R' AS sap_released_for_production,
           o.product_item_code, o.product_description,
           o.planned_quantity AS sap_planned_production_quantity,
           o.completed_quantity AS sap_completed_production_quantity,
           o.start_date AS sap_start_date, o.due_date AS sap_due_date,
           CASE WHEN o.order_number IS NULL THEN 'NO_SAP_PLAN'
                WHEN CAST(w.started_at AS DATE) BETWEEN o.start_date - 14 AND o.due_date + 14 THEN 'DATE_MATCH'
                ELSE 'DATE_MISMATCH' END AS sap_date_match_status,
           o.planned_resin_total_kg,
           w.actual_consumed_total_kg,
           w.actual_consumed_total_kg - o.planned_resin_total_kg AS variance_kg,
           (w.actual_consumed_total_kg - o.planned_resin_total_kg) / NULLIF(o.planned_resin_total_kg, 0) * 100 AS variance_percent,
           CASE WHEN o.order_number IS NULL THEN 'NO_PLAN'
                WHEN w.actual_consumed_total_kg IS NULL THEN 'NO_ACTUAL_CONSUMPTION'
                ELSE 'COMPARED' END AS comparison_status,
           w.windows_count, w.windows_without_consumption,
           o.resin_filter_applied, o.synced_at AS sap_synced_at
    FROM windows w
    LEFT JOIN public.sap_production_orders o ON o.order_number = w.order_number
    """)


def simulate_changes(con, rng: random.Random, today: date, now: datetime) -> None:
    """Second wave: edits, a cancellation, new documents and new machine windows."""
    contoso, fabrikam = COMPANIES["CONTOSO"], COMPANIES["FABRIKAM"]
    old = [r[0] for r in con.execute(
        f'SELECT "DocEntry" FROM {contoso}.OPCH WHERE "DocDate" < ? AND "CANCELED" = \'N\' ORDER BY "DocEntry" LIMIT 4',
        (today - timedelta(days=30),)).fetchall()]
    for doc_entry in old[:3]:
        con.execute(f'UPDATE {contoso}.OPCH SET "DocTotal" = "DocTotal" * 1.10, "UpdateDate" = ? WHERE "DocEntry" = ?', (today, doc_entry))
    con.execute(f'UPDATE {contoso}.OPCH SET "CANCELED" = \'Y\', "DocStatus" = \'C\', "UpdateDate" = ? WHERE "DocEntry" = ?', (today, old[3]))
    next_entry = con.execute(f'SELECT MAX("DocEntry") + 1 FROM {contoso}.OPCH').fetchone()[0]
    for doc_entry in range(next_entry, next_entry + 2):
        insert_invoice(con, contoso, rng, doc_entry, today, today, "CONTOSO", allow_csrf=False)

    # first CSRF withholding ever: the column must keep the same type as before
    service_doc = con.execute(
        f'SELECT MIN(L."DocEntry") FROM {fabrikam}.PCH1 L WHERE L."CFOPCode" IN (\'1933\', \'2933\')').fetchone()[0]
    con.execute(f"INSERT INTO {fabrikam}.PCH5 VALUES (?, 'WT-CSRF', 123.45, 'I')", (service_doc,))

    open_line = con.execute(f'SELECT "DocEntry", "LineNum" FROM {contoso}.WTQ1 WHERE "LineStatus" = \'O\' LIMIT 1').fetchone()
    next_transfer = con.execute(f'SELECT MAX("DocEntry") + 1 FROM {contoso}.OWTR').fetchone()[0]
    con.execute(f"INSERT INTO {contoso}.OWTR VALUES (?, ?, 'N', 'C', ?, 'Matriz')", (next_transfer, 80000 + next_transfer, today))
    con.execute(f"INSERT INTO {contoso}.WTR1 VALUES (?, 0, ?, ?, ?, 'RES-PP-001', 10)",
                (next_transfer, TRANSFER_REQUEST_OBJECT, open_line[0], open_line[1]))

    naive_now = now.replace(tzinfo=None, microsecond=0)
    for machine in MACHINES:
        last = con.execute("SELECT order_number, started_at FROM public.vw_order_number_changes "
                           "WHERE machine = ? AND next_order_started_at IS NULL", (machine,)).fetchone()
        if last is None:
            continue
        close_at = naive_now - timedelta(minutes=30)
        duration = round((close_at - last[1]).total_seconds() / 60, 1)
        con.execute("UPDATE public.vw_order_number_changes SET next_order_started_at = ?, duration_minutes = ? "
                    "WHERE machine = ? AND started_at = ?", (close_at, duration, machine, last[1]))
        con.execute("UPDATE public.vw_order_actual_consumption_total SET ended_at = ?, duration_minutes = ?, "
                    "actual_consumed_total_kg = COALESCE(actual_consumed_total_kg, 0) + 15 WHERE machine = ? AND started_at = ?",
                    (close_at, duration, machine, last[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--path", default="data/sources.duckdb")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--simulate-changes", action="store_true", help="Apply the second wave of changes to an existing database")
    args = parser.parse_args()

    path = Path(args.path)
    rng = random.Random(args.seed + (1 if args.simulate_changes else 0))
    now = datetime.now(timezone.utc)
    today = now.date()

    if args.simulate_changes:
        if not path.exists():
            parser.error(f"{path} does not exist; generate it first")
        with duckdb.connect(str(path)) as con:
            simulate_changes(con, rng, today, now)
        print(f"changes applied to {path}")
        return 0

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    with duckdb.connect(str(path)) as con:
        create_compat(con)
        generate_sap(con, rng, today)
        generate_motan(con, rng, now)
    print(f"fake sources written to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
