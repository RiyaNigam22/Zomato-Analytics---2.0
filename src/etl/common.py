"""Logging setup and deterministic row fingerprinting for the ETL pipeline."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any


def setup_logger(log_dir: Path, log_level: str = "INFO") -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("zomato_etl")
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(level)

    if not logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(level)
        stream_handler.setFormatter(formatter)

        file_handler = logging.FileHandler(log_dir / "etl_pipeline.log", encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)

        logger.addHandler(stream_handler)
        logger.addHandler(file_handler)

    return logger


def compute_row_fingerprint(payload: dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 fingerprint for idempotent snapshot tracking."""
    canonical_keys = [
        "restaurant_name_clean",
        "city_clean",
        "place_name_clean",
        "cuisine_clean",
        "item_name_clean",
        "price",
        "dining_rating",
        "delivery_rating",
        "average_rating",
        "dining_votes",
        "delivery_votes",
        "votes",
        "total_votes",
        "is_bestseller",
        "is_highly_rated",
        "is_expensive",
    ]
    canonical_obj = {k: payload.get(k) for k in canonical_keys}
    serialized = json.dumps(canonical_obj, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
