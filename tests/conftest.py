from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "sample_data"
LSV_NAME = "LSV-裸-100uMROS-L1.bin"
IT_NAME = "玻碳2-AuNPs-PB-5,10,20,40,80uMROS-ph6.5.bin"


@pytest.fixture(scope="session")
def lsv_path() -> Path:
    return SAMPLE_DIR / LSV_NAME


@pytest.fixture(scope="session")
def it_path() -> Path:
    return SAMPLE_DIR / IT_NAME

