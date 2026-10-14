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

# # Silver finance
#
# Deriva o Silver do Bronze: versao mais recente por chave, regras criticas do
# contrato (chave unica e nao nula) e publicacao so se elas passarem. So roda
# quando o Bronze tem run mais novo que o Silver.

# CELL ********************

from delta.tables import DeltaTable
from pyspark.sql import Window
from pyspark.sql import functions as F

DATASETS = [
    {"bronze": "bronze_sap_purchase_invoices", "silver": "silver_finance_purchase_invoices", "keys": ["doc_entry"], "load_mode": "incremental"},
    {"bronze": "bronze_sap_return_transfers", "silver": "silver_finance_return_transfers", "keys": ["doc_entry", "line_num"], "load_mode": "full"},
    {"bronze": "bronze_sap_service_invoices", "silver": "silver_finance_service_invoices", "keys": ["company", "doc_entry"], "load_mode": "full"},
]


class QualityError(Exception):
    pass


def latest_per_key(df, keys):
    w = Window.partitionBy(*keys).orderBy(F.col("_run_started_at").desc())
    return df.withColumn("_rn", F.row_number().over(w)).where("_rn = 1").drop("_rn")


def check_keys(df, keys, table):
    nulls = df.where(" OR ".join(f"`{k}` IS NULL" for k in keys)).count()
    dups = df.count() - df.select(*keys).distinct().count()
    if nulls or dups:
        raise QualityError(f"[{table}] chave {keys}: {nulls} nulas, {dups} duplicadas")


def max_run(table):
    if not spark.catalog.tableExists(table):
        return None
    return spark.table(table).agg(F.max("_run_started_at")).first()[0]


def ingest_silver(bronze, silver, keys, load_mode):
    if spark.catalog.tableExists(silver) and max_run(bronze) <= max_run(silver):
        print(f"[{silver}] nada novo")
        return
    df = (
        latest_per_key(spark.table(bronze), keys)
        .drop("_bronze_loaded_at")
        .withColumn("_silver_loaded_at", F.current_timestamp())
        .cache()
    )
    check_keys(df, keys, silver)
    if load_mode == "full" or not spark.catalog.tableExists(silver):
        df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(silver)
    else:
        cond = " AND ".join(f"t.`{k}` = s.`{k}`" for k in keys)
        (
            DeltaTable.forName(spark, silver).alias("t")
            .merge(df.alias("s"), cond)
            .whenMatchedUpdateAll(condition="s._run_started_at > t._run_started_at")
            .whenNotMatchedInsertAll()
            .execute()
        )
    print(f"[{silver}] {df.count()} linhas")
    df.unpersist()

# CELL ********************

for cfg in DATASETS:
    ingest_silver(cfg["bronze"], cfg["silver"], cfg["keys"], cfg["load_mode"])

# CELL ********************

display(spark.sql("""
SELECT 'silver_finance_purchase_invoices' AS tabela, COUNT(*) AS linhas, SUM(CAST(is_cancelled AS INT)) AS canceladas
FROM silver_finance_purchase_invoices
UNION ALL SELECT 'silver_finance_return_transfers', COUNT(*), NULL FROM silver_finance_return_transfers
UNION ALL SELECT 'silver_finance_service_invoices', COUNT(*), SUM(CAST(is_cancelled AS INT)) FROM silver_finance_service_invoices
"""))
