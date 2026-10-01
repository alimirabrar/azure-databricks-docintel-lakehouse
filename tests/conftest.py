from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample"

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")


@pytest.fixture(scope="session")
def spark():
    from docintel.pipeline.io import local_spark

    session = local_spark("docintel-tests")
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


@pytest.fixture(scope="session")
def sample_dir() -> Path:
    return SAMPLE
