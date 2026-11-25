"""Deterministic cleaning, standardization, and reporting for Zomato baseline data."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any
import numpy as np
import pandas as pd

from src.processing.validator import BUSINESS_KEY_COLUMNS, run_validation


def _clean_whitespace_and_case(series: pd.Series, title_case: bool = True) -> pd.Series:
    cleaned = series.astype("string").str.strip().str.replace(r"\s+", " ", regex=True)
    if title_case:
        cleaned = cleaned.str.title()
    return cleaned


def _normalize_bestseller_flag(raw_val: Any) -> int:
    if pd.isna(raw_val):
        return 0
    s = str(raw_val).strip().lower()
    if s in {"1", "true", "yes", "bestseller", "best seller", "y"}:
        return 1
    return 0


def clean_and_report(
    raw_csv_path: Path,
    processed_dir: Path,
    quarantine_dir: Path,
    drop_exact_duplicates: bool = False,
) -> dict[str, Any]:
    """Load raw CSV without modifying it, clean fields, record DQ metrics, and export outputs."""
    processed_dir.mkdir(parents=True, exist_ok=True)
    quarantine_dir.mkdir(parents=True, exist_ok=True)

    run_timestamp_utc = datetime.now(timezone.utc).isoformat()
    df_raw = pd.read_csv(raw_csv_path, low_memory=False)
    pre_validation, masks = run_validation(df_raw)

    df = df_raw.copy()
    df["raw_row_number"] = np.arange(1, len(df) + 1)
    df["record_source"] = "baseline_csv"
    df["baseline_loaded_at_utc"] = run_timestamp_utc
    df["has_original_timestamp"] = False

    # Standardize text fields while preserving raw values in separate audit columns if needed
    for text_col in ["Restaurant_Name", "City", "Place_Name", "Cuisine", "Item_Name"]:
        if text_col in df.columns:
            df[f"{text_col}_raw"] = df[text_col].astype("string")
            is_item = text_col == "Item_Name"
            df[text_col] = _clean_whitespace_and_case(df[text_col], title_case=not is_item)

    # Audit Is_Bestseller vs Best_Seller explicitly
    is_bestseller_constant = len(pre_validation.is_bestseller_distinct_values) <= 1
    if "Best_Seller" in df.columns:
        df["Derived_Bestseller_From_Label"] = df["Best_Seller"].apply(_normalize_bestseller_flag)
    else:
        df["Derived_Bestseller_From_Label"] = 0

    df["Is_Bestseller_Audit_Flag"] = np.where(
        is_bestseller_constant,
        "CONSTANT_VALUE_IN_RAW_SOURCE",
        "VARIED_IN_RAW_SOURCE",
    )

    # Numeric conversions & anomaly indicators (no silent record deletion)
    numeric_cols = [
        "Dining_Rating",
        "Delivery_Rating",
        "Dining_Votes",
        "Delivery_Votes",
        "Votes",
        "Prices",
        "Average_Rating",
        "Total_Votes",
        "Price_per_Vote",
        "Log_Price",
        "Restaurant_Popularity",
        "Avg_Rating_Restaurant",
        "Avg_Price_Restaurant",
        "Avg_Rating_Cuisine",
        "Avg_Price_Cuisine",
        "Avg_Rating_City",
        "Avg_Price_City",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Recompute safe Log_Price only where Prices > 0 for comparison/audit
    if "Prices" in df.columns:
        valid_pos_price = df["Prices"].notna() & (df["Prices"] > 0)
        df["Recomputed_Log_Price"] = np.where(valid_pos_price, np.log1p(df["Prices"]), np.nan)

    # Build quarantine view for severe anomalies (negative prices or out-of-range ratings)
    severe_anomaly_mask = (
        masks["negative_price"]
        | masks["dining_rating_out_of_range"]
        | masks["delivery_rating_out_of_range"]
        | masks["avg_rating_out_of_range"]
        | masks["negative_votes"]
        | masks["infinite_derived_metric"]
    )
    quarantine_df = df[severe_anomaly_mask].copy()
    quarantine_path = quarantine_dir / "quarantine_anomalies.csv"
    quarantine_df.to_csv(quarantine_path, index=False)

    # Optional explicit exact-duplicate handling (default False so zero rows are lost unless opted in)
    rows_removed_exact_dups = 0
    if drop_exact_duplicates:
        subset_cols = [c for c in df.columns if c not in {"raw_row_number", "baseline_loaded_at_utc"}]
        before_len = len(df)
        df = df.drop_duplicates(subset=subset_cols, keep="first").copy()
        rows_removed_exact_dups = before_len - len(df)

    cleaned_csv_path = processed_dir / "zomato_baseline_clean.csv"
    df.to_csv(cleaned_csv_path, index=False)

    post_validation, _ = run_validation(df)

    # Top location / cuisine cardinality snapshot for auditability
    top_cities = (
        df["City"].value_counts(dropna=False).head(10).to_dict() if "City" in df.columns else {}
    )
    distinct_locations_clean = (
        int(df[["City", "Place_Name"]].drop_duplicates().shape[0])
        if {"City", "Place_Name"}.issubset(df.columns)
        else 0
    )

    report: dict[str, Any] = {
        "generated_at_utc": run_timestamp_utc,
        "raw_source_file": str(raw_csv_path),
        "processed_output_file": str(cleaned_csv_path),
        "quarantine_output_file": str(quarantine_path),
        "drop_exact_duplicates_enabled": drop_exact_duplicates,
        "rows_removed_exact_duplicates": rows_removed_exact_dups,
        "quarantined_anomaly_rows": int(len(quarantine_df)),
        "distinct_clean_city_place_pairs": distinct_locations_clean,
        "top_cities_row_counts": top_cities,
        "business_key_columns": BUSINESS_KEY_COLUMNS,
        "pre_cleaning_validation": pre_validation.__dict__,
        "post_cleaning_validation": post_validation.__dict__,
    }

    json_report_path = processed_dir / "data_quality_report.json"
    json_report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    md_report_path = processed_dir / "data_quality_report.md"
    md_lines = [
        "# Zomato Analytics 2.0 — Phase 1 Data Quality Report",
        "",
        f"- **Generated (UTC):** {run_timestamp_utc}",
        f"- **Raw Source:** `{raw_csv_path}`",
        f"- **Processed Baseline:** `{cleaned_csv_path}` ({len(df):,} rows)",
        f"- **Quarantined Anomaly Rows:** {len(quarantine_df):,} (`{quarantine_path}`)",
        f"- **Exact Duplicates Removed:** {rows_removed_exact_dups:,} (opt-in flag: `{drop_exact_duplicates}`)",
        f"- **Exact Duplicate Rows Detected (Raw):** {pre_validation.exact_duplicate_rows:,}",
        f"- **Business-Key Duplicate Rows Detected (Raw):** {pre_validation.business_key_duplicate_rows:,}",
        f"- **`Is_Bestseller` Distinct Values (Raw):** {pre_validation.is_bestseller_distinct_values}",
        f"- **Zero-Price Rows:** {pre_validation.zero_price_rows:,} | **Negative-Price Rows:** {pre_validation.negative_price_rows:,}",
        f"- **Out-of-Range Ratings (Dining / Delivery / Avg):** {pre_validation.out_of_range_dining_rating_rows:,} / {pre_validation.out_of_range_delivery_rating_rows:,} / {pre_validation.out_of_range_avg_rating_rows:,}",
        f"- **Negative Vote Rows:** {pre_validation.negative_votes_rows:,}",
        f"- **Infinite/Non-Finite Derived Metric Rows:** {pre_validation.infinite_or_nan_derived_rows:,}",
    ]
    md_report_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    return report