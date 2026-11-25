"""Central configuration loader for Zomato Analytics 2.0."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from dotenv import load_dotenv


@dataclass(frozen=True)
class ProjectConfig:
    project_root: Path
    raw_csv_path: Path
    processed_dir: Path
    quarantine_dir: Path
    log_level: str


def load_config(project_root: Path | None = None) -> ProjectConfig:
    load_dotenv()
    root = (project_root or Path(__file__).resolve().parent.parent).resolve()

    raw_csv = Path(os.getenv("RAW_CSV_PATH", "data/raw/enhanced_zomato_dataset_clean.csv"))
    processed_dir = Path(os.getenv("PROCESSED_DIR", "data/processed"))
    quarantine_dir = Path(os.getenv("QUARANTINE_DIR", "data/quarantine"))

    if not raw_csv.is_absolute():
        raw_csv = root / raw_csv
    if not processed_dir.is_absolute():
        processed_dir = root / processed_dir
    if not quarantine_dir.is_absolute():
        quarantine_dir = root / quarantine_dir

    return ProjectConfig(
        project_root=root,
        raw_csv_path=raw_csv,
        processed_dir=processed_dir,
        quarantine_dir=quarantine_dir,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
