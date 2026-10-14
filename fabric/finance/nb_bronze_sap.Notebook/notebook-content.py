# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse_name": "lh_finance"
# META     }
# META   }
# META }

# MARKDOWN ********************

# # Bronze SAP (finance)
#
# Le a landing pelo shortcut `Files/sap` (-> `landing/finance/sap`) e carrega as
# tabelas `bronze_sap_*`. Mesmas regras do `local/medallion.py`:
#
# - so le runs que tem manifest (o manifest e gravado por ultimo pelo exportador);
# - ordena runs por `_run_started_at` (do manifest), nunca por `run_id`;
# - `ctrl_ingested_runs` registra o que ja foi carregado; so recebe linha nova
#   quando algo novo entrou;
# - incremental: MERGE por chave, so atualiza se o run que chega e mais novo;
# - full: o ultimo run completo substitui a tabela.

# CELL ********************

from datetime import datetime, timezone
from functools import reduce

from delta.tables import DeltaTable
from pyspark.sql import Window
from pyspark.sql import functions as F

LANDING = "Files/sap"  # shortcut -> landing/finance/sap
SOURCE = "sap"
CTRL = "ctrl_ingested_runs"
DATASETS = [
    {"dataset": "purchase_invoices", "bronze": "bronze_sap_purchase_invoices", "load_mode": "incremental", "keys": ["doc_entry"]},
    {"dataset": "return_transfers", "bronze": "bronze_sap_return_transfers", "load_mode": "full", "keys": ["doc_entry", "line_num"]},
    {"dataset": "service_invoices", "bronze": "bronze_sap_service_invoices", "load_mode": "full", "keys": ["company", "doc_entry"]},
]

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CTRL} (
  layer STRING, dataset STRING, run_id STRING, ingestion_date STRING,
  run_started_at TIMESTAMP, row_count BIGINT, ingested_at TIMESTAMP
) USING DELTA
""")


def completed_runs(dataset):
    """Runs with a successful manifest that contain the dataset, oldest first."""
    manifests = spark.read.option("multiLine", True).json(f"{LANDING}/_manifests/*/*/manifest.json")
    rows = (
        manifests.where(F.col("status") == "success")
        .select(
            F.col("run_id").cast("string").alias("run_id"),
            "ingestion_date",
            F.to_timestamp("started_at").alias("run_started_at"),
            F.explode("datasets").alias("d"),
        )
        .where(F.col("d.landing_dataset") == dataset)
        .select("run_id", "ingestion_date", "run_started_at", F.col("d.landing_path").alias("landing_path"))
        .collect()
    )
    return sorted(rows, key=lambda r: r.run_started_at)


def loaded_runs(layer, dataset):
    rows = spark.table(CTRL).where((F.col("layer") == layer) & (F.col("dataset") == dataset)).select("run_id").collect()
    return {r.run_id for r in rows}


def latest_per_key(df, keys):
    w = Window.partitionBy(*keys).orderBy(F.col("_run_started_at").desc())
    return df.withColumn("_rn", F.row_number().over(w)).where("_rn = 1").drop("_rn")


def ingest_bronze(dataset, bronze, load_mode, keys):
    runs = completed_runs(dataset)
    if load_mode == "full":
        runs = runs[-1:]
    done = loaded_runs("bronze", dataset)
    new_runs = [r for r in runs if r.run_id not in done]
    if not new_runs:
        print(f"[{dataset}] nada novo")
        return

    frames = []
    for r in new_runs:
        path = f"{LANDING}/" + r.landing_path.split(f"/{SOURCE}/", 1)[1]
        frames.append(
            spark.read.parquet(path)
            .withColumn("_run_id", F.lit(r.run_id))
            .withColumn("_ingestion_date", F.lit(r.ingestion_date))
            .withColumn("_run_started_at", F.lit(r.run_started_at).cast("timestamp"))
            .withColumn("_source_path", F.lit(path))
        )
    df = (
        reduce(lambda a, b: a.unionByName(b), frames)
        .withColumn("_bronze_loaded_at", F.current_timestamp())
        .withColumn("_source_system", F.lit(SOURCE))
        .cache()
    )

    if load_mode == "full":
        df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(bronze)
    elif not spark.catalog.tableExists(bronze):
        latest_per_key(df, keys).write.format("delta").saveAsTable(bronze)
    else:
        cond = " AND ".join(f"t.`{k}` = s.`{k}`" for k in keys)
        (
            DeltaTable.forName(spark, bronze).alias("t")
            .merge(latest_per_key(df, keys).alias("s"), cond)
            .whenMatchedUpdateAll(condition="s._run_started_at > t._run_started_at")
            .whenNotMatchedInsertAll()
            .execute()
        )

    counts = {row["_run_id"]: row["count"] for row in df.groupBy("_run_id").count().collect()}
    now = datetime.now(timezone.utc)
    ctrl = [("bronze", dataset, r.run_id, r.ingestion_date, r.run_started_at, counts.get(r.run_id, 0), now) for r in new_runs]
    spark.createDataFrame(ctrl, schema=spark.table(CTRL).schema).write.mode("append").saveAsTable(CTRL)
    df.unpersist()
    print(f"[{dataset}] ({load_mode}) {len(new_runs)} run(s) -> {bronze}")

# CELL ********************

for cfg in DATASETS:
    ingest_bronze(cfg["dataset"], cfg["bronze"], cfg["load_mode"], cfg["keys"])

# CELL ********************

display(spark.sql(f"""
SELECT layer, dataset, COUNT(*) AS runs, SUM(row_count) AS linhas, MAX(run_started_at) AS ultimo_run
FROM {CTRL} GROUP BY layer, dataset ORDER BY layer, dataset
"""))
