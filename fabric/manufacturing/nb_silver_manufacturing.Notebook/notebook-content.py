# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse_name": "lh_manufacturing"
# META     }
# META   }
# META }

# MARKDOWN ********************

# # Silver manufacturing
#
# Deriva o Silver do Bronze: versao mais recente por chave, regras criticas do
# contrato (chave unica e nao nula) e publicacao so se elas passarem. So roda
# quando o Bronze tem run mais novo que o Silver.

# CELL ********************

from delta.tables import DeltaTable
from pyspark.sql import Window
from pyspark.sql import functions as F

DATASETS = [
    {"bronze": "bronze_motan_order_context", "silver": "silver_manufacturing_order_windows", "keys": ["machine", "order_number", "started_at"], "load_mode": "incremental"},
    {"bronze": "bronze_motan_actual_consumption_by_order", "silver": "silver_manufacturing_order_consumption", "keys": ["machine", "order_number", "started_at"], "load_mode": "incremental"},
    {"bronze": "bronze_sap_production_orders", "silver": "silver_manufacturing_production_orders", "keys": ["order_number"], "load_mode": "incremental"},
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
SELECT 'silver_manufacturing_order_windows' AS tabela, COUNT(*) AS linhas FROM silver_manufacturing_order_windows
UNION ALL SELECT 'silver_manufacturing_order_consumption', COUNT(*) FROM silver_manufacturing_order_consumption
UNION ALL SELECT 'silver_manufacturing_production_orders', COUNT(*) FROM silver_manufacturing_production_orders
"""))
