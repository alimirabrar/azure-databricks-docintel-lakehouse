"""MLflow tracking for extraction runs (prompt version, client, accuracy)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from docintel.evaluation import EvalReport
from docintel.prompts import get_prompt

DEFAULT_EXPERIMENT = "docintel-extraction"


def log_extraction_run(
    report: EvalReport,
    *,
    prompt_version: str,
    client_name: str,
    model: str,
    experiment: str | None = None,
    tracking_uri: str | None = None,
    extra_params: dict[str, Any] | None = None,
    run_name: str | None = None,
) -> str:
    """Log params, metrics and artifacts for one evaluation run. Returns the run id.

    On Databricks the tracking URI is the workspace (``databricks``) and
    ``experiment`` should be a workspace path such as ``/Shared/docintel-extraction``.
    Locally it defaults to a SQLite store at ``./mlflow.db`` (``mlflow ui --backend-store-uri
    sqlite:///mlflow.db``).
    """
    import mlflow

    uri = tracking_uri or os.environ.get("MLFLOW_TRACKING_URI")
    if uri:
        mlflow.set_tracking_uri(uri)
    elif not os.environ.get("DATABRICKS_RUNTIME_VERSION"):
        mlflow.set_tracking_uri(f"sqlite:///{Path('mlflow.db').resolve()}")
    mlflow.set_experiment(experiment or os.environ.get("MLFLOW_EXPERIMENT", DEFAULT_EXPERIMENT))

    prompt = get_prompt(prompt_version)
    with mlflow.start_run(run_name=run_name or f"{client_name}-{prompt_version}") as run:
        mlflow.set_tags({"component": "extraction", "client": client_name})
        mlflow.log_params(
            {
                "prompt_version": prompt_version,
                "llm_client": client_name,
                "model": model,
                "n_docs": report.n_docs,
                **(extra_params or {}),
            }
        )
        mlflow.log_metrics(report.metrics())
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t / "field_scores.json").write_text(json.dumps(report.table(), indent=2))
            (t / "field_scores.md").write_text(report.to_markdown() + "\n")
            (t / "per_doc.json").write_text(json.dumps(report.per_doc, indent=2))
            (t / f"prompt_{prompt_version}.json").write_text(
                json.dumps(
                    {"version": prompt.version, "system": prompt.system, "user": prompt.user},
                    indent=2,
                )
            )
            mlflow.log_artifacts(tmp, artifact_path="eval")
        return run.info.run_id
