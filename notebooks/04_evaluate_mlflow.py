# Databricks notebook source
# MAGIC %md
# MAGIC # 04 · Evaluate extraction accuracy & log to MLflow
# MAGIC Scores the silver records produced with the current prompt version against the
# MAGIC labeled sample (`labels_path`, one JSON file per `doc_id`) and logs field-level
# MAGIC precision / recall / F1, the prompt text and per-document errors to MLflow.

# COMMAND ----------

# MAGIC %run ./_setup

# COMMAND ----------

import json
import os

from pyspark.sql import functions as F

from docintel.evaluation import evaluate
from docintel.runner import silver_to_predictions
from docintel.tracking import log_extraction_run

labels = {}
for f in os.listdir(LABELS_PATH):
    if f.endswith(".json"):
        with open(os.path.join(LABELS_PATH, f)) as fh:
            labels[f[:-5]] = json.load(fh)

silver_df = TARGET.read(spark, "silver_documents").filter(  # noqa: F821
    (F.col("prompt_version") == PROMPT_VERSION) & F.col("doc_id").isin(list(labels))
)
report = evaluate(silver_to_predictions(silver_df), labels)
print(report.to_markdown())

# COMMAND ----------

meta = silver_df.select("llm_client", "llm_model").filter("llm_client IS NOT NULL").first()
run_id = log_extraction_run(
    report,
    prompt_version=PROMPT_VERSION,
    client_name=meta["llm_client"] if meta else LLM_CLIENT,
    model=meta["llm_model"] if meta else "unknown",
    experiment=EXPERIMENT,
    extra_params={"catalog": CATALOG, "schema": SCHEMA},
)
metrics = report.metrics()
row = {"run_id": run_id, "prompt_version": PROMPT_VERSION, "llm_client": LLM_CLIENT,
       **{k: float(v) for k, v in metrics.items()}}
(
    spark.createDataFrame([row])  # noqa: F821
    .withColumn("evaluated_at", F.current_timestamp())
    .write.format("delta").mode("append").option("mergeSchema", "true")
    .saveAsTable(TARGET.name("gold_extraction_eval"))
)
print(f"MLflow run {run_id}: micro F1 = {metrics['micro_f1']:.3f}")
