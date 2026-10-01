"""Table IO that works both on Databricks (Unity Catalog + Delta) and locally (Parquet)."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession


@dataclass(frozen=True)
class TableTarget:
    """Either a Unity Catalog ``catalog.schema`` or a local base directory."""

    catalog: str | None = None
    schema: str | None = None
    base_path: str | None = None
    fmt: str = "delta"

    def name(self, table: str) -> str:
        if self.catalog and self.schema:
            return f"{self.catalog}.{self.schema}.{table}"
        if self.base_path:
            return str(Path(self.base_path) / table)
        raise ValueError("TableTarget needs catalog+schema or base_path")

    def write(self, df: DataFrame, table: str, mode: str = "overwrite") -> str:
        name = self.name(table)
        w = df.write.format(self.fmt).mode(mode)
        if self.fmt == "delta":
            w = w.option("overwriteSchema", "true")
        if self.catalog and self.schema:
            w.saveAsTable(name)
        else:
            w.save(name)
        return name

    def read(self, spark: SparkSession, table: str) -> DataFrame:
        name = self.name(table)
        if self.catalog and self.schema:
            return spark.table(name)
        return spark.read.format(self.fmt).load(name)


def local_spark(app_name: str = "docintel-local") -> SparkSession:
    """A small local SparkSession for development, tests and CI."""
    # Make Python workers use the same interpreter as the driver (venvs, CI matrices).
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)
    return (
        SparkSession.builder.master("local[2]")
        .appName(app_name)
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.driver.memory", "1g")
        .getOrCreate()
    )
