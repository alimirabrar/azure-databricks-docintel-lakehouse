# Databricks notebook source
# MAGIC %md
# MAGIC ### Shared setup
# MAGIC Run via `%run ./_setup` from the layer notebooks. Declares widgets, makes the
# MAGIC `docintel` package importable and builds the Unity Catalog table target.

# COMMAND ----------

import os
import sys

dbutils.widgets.text("catalog", "main")  # noqa: F821
dbutils.widgets.text("schema", "docintel")  # noqa: F821
dbutils.widgets.text("landing_path", "/Volumes/main/docintel/landing/raw")  # noqa: F821
dbutils.widgets.text("labels_path", "/Volumes/main/docintel/landing/labels")  # noqa: F821
dbutils.widgets.dropdown("llm_client", "rule_based", ["rule_based", "azure_openai"])  # noqa: F821
dbutils.widgets.dropdown("prompt_version", "v2", ["v1", "v2"])  # noqa: F821
dbutils.widgets.text("experiment", "/Shared/docintel-extraction")  # noqa: F821
dbutils.widgets.text("llm_partitions", "8")  # noqa: F821

CATALOG = dbutils.widgets.get("catalog")  # noqa: F821
SCHEMA = dbutils.widgets.get("schema")  # noqa: F821
LANDING_PATH = dbutils.widgets.get("landing_path")  # noqa: F821
LABELS_PATH = dbutils.widgets.get("labels_path")  # noqa: F821
LLM_CLIENT = dbutils.widgets.get("llm_client")  # noqa: F821
PROMPT_VERSION = dbutils.widgets.get("prompt_version")  # noqa: F821
EXPERIMENT = dbutils.widgets.get("experiment")  # noqa: F821
LLM_PARTITIONS = int(dbutils.widgets.get("llm_partitions"))  # noqa: F821

# The bundle installs the wheel on the job cluster; when running the notebooks
# interactively from a Git folder, fall back to the repo's src/ directory.
try:
    import docintel  # noqa: F401
except ImportError:
    sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "..", "src")))

from docintel.pipeline.io import TableTarget  # noqa: E402

TARGET = TableTarget(catalog=CATALOG, schema=SCHEMA, fmt="delta")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")  # noqa: F821
print(f"target={CATALOG}.{SCHEMA} landing={LANDING_PATH} client={LLM_CLIENT} prompt={PROMPT_VERSION}")
