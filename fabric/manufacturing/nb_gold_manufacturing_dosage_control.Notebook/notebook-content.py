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

# # Gold - manufacturing_dosage_control
#
# Calculado no lakehouse a partir do Silver (antes era copiado de uma view
# on-premise). Grao: uma linha por maquina e OP. A tolerancia vem do contrato do
# Data Product (`business_rules.dosage_status.variance_tolerance_percent`).
# A view on-premise continua no Bronze como referencia para o teste de paridade.

# CELL ********************

from pyspark.sql import functions as F

VARIANCE_TOLERANCE_PERCENT = 5.0  # contracts/data-products/manufacturing/manufacturing-dosage-control.yaml

consumption = spark.table("silver_manufacturing_order_consumption")
orders = spark.table("silver_manufacturing_production_orders")

windows = consumption.groupBy("machine", "order_number").agg(
    F.min("started_at").alias("started_at"),
    F.when(F.count("*") == F.count("ended_at"), F.max("ended_at")).alias("ended_at"),
    F.sum("duration_minutes").alias("duration_minutes"),
    F.sum("actual_consumed_total_kg").alias("actual_consumed_total_kg"),  # NULL quando todas as janelas sao nulas
    (F.count("*") - F.count("actual_consumed_total_kg")).alias("windows_without_consumption"),
    F.count("*").alias("windows_count"),
)

variance_percent = F.col("variance_kg") / F.col("planned_resin_total_kg") * 100
gold = (
    windows.join(
        orders.select("order_number", "product_item_code", "product_description", "planned_resin_total_kg",
                      F.col("status").alias("sap_status"), F.col("synced_at").alias("sap_synced_at")),
        "order_number", "left",
    )
    .withColumn("variance_kg", F.col("actual_consumed_total_kg") - F.col("planned_resin_total_kg"))
    .withColumn("variance_percent", variance_percent)
    .withColumn(
        "dosage_control_status",
        F.when(F.col("planned_resin_total_kg").isNull(), "NO_PLAN")
        .when(F.col("actual_consumed_total_kg").isNull(), "NO_ACTUAL_CONSUMPTION")
        .when(F.abs("variance_percent") <= VARIANCE_TOLERANCE_PERCENT, "WITHIN_TOLERANCE")
        .when(F.col("variance_percent") > VARIANCE_TOLERANCE_PERCENT, "OVER_CONSUMPTION")
        .otherwise("UNDER_CONSUMPTION"),
    )
    .withColumn("_gold_loaded_at", F.current_timestamp())
)

dups = gold.count() - gold.select("machine", "order_number").distinct().count()
assert dups == 0, f"gold com {dups} chave(s) duplicada(s)"

gold.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("gold_manufacturing_dosage_control")

# CELL ********************

# Paridade com a view on-premise que o Gold substitui.
reference = spark.table("bronze_motan_order_plan_vs_actual_reference")
diff = (
    spark.table("gold_manufacturing_dosage_control").alias("g")
    .join(reference.alias("r"), ["machine", "order_number"])
    .select(F.max(F.abs(F.col("g.actual_consumed_total_kg") - F.col("r.actual_consumed_total_kg"))).alias("max_diff_kg"))
)
display(diff)
