"""Transform validated Zomato CSV rows into normalized dimension and snapshot payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any
import numpy as np
import pandas as pd

from src.etl.common import compute_row_fingerprint
from src.processing.cleaner import _clean_whitespace_and_case, _normalize_bestseller_flag
from src.processing.validator import run_validation


def _to_float_or_none(val: Any) -> float | None:
    if val is None or pd.isna(val):
        return None
    f = float(val)
    return None if np.isnan(f) or np.isinf(f) else f


def _to_int_or_none(val: Any) -> int | None:
    if val is None or pd.isna(val):
        return None
    f = float(val)
    if np.isnan(f) or np.isinf(f):
        return None
    return int(round(f))


def _to_str_or_none(val: Any, max_len: int | None = None) -> str | None:
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return None
    return s[:max_len] if max_len else s


def prepare_records(
    df_slice: pd.DataFrame,
    *,
    snapshot_batch_id: str,
    observed_at: datetime,
    source_name: str = "baseline_csv",
) -> tuple[list[dict[str, Any]], pd.DataFrame, dict[str, Any]]:
    """Clean a slice of Zomato rows, separate severe anomalies, and build snapshot records."""
    summary, masks = run_validation(df_slice)

    df = df_slice.copy()
    for col in ["Restaurant_Name", "City", "Place_Name", "Cuisine", "Item_Name"]:
        if col in df.columns:
            df[f"{col}_raw"] = _clean_whitespace_and_case(df[col], title_case=False)
            df[f"{col}_clean"] = _clean_whitespace_and_case(df[col], title_case=(col != "Item_Name"))
        else:
            df[f"{col}_raw"] = None
            df[f"{col}_clean"] = None

    severe_mask = (
        masks["negative_price"]
        | masks["dining_rating_out_of_range"]
        | masks["delivery_rating_out_of_range"]
        | masks["avg_rating_out_of_range"]
        | masks["negative_votes"]
        | masks["infinite_derived_metric"]
    )
    quarantined_df = df[severe_mask].copy()
    valid_df = df[~severe_mask].copy()

    records: list[dict[str, Any]] = []
    for _, row in valid_df.iterrows():
        city_clean = _to_str_or_none(row.get("City_clean"), 120) or "Unknown"
        place_clean = _to_str_or_none(row.get("Place_Name_clean"), 180) or "Unknown"
        cuisine_clean = _to_str_or_none(row.get("Cuisine_clean"), 180) or "Unspecified"
        rest_clean = _to_str_or_none(row.get("Restaurant_Name_clean"), 255) or "Unknown Restaurant"
        item_clean = _to_str_or_none(row.get("Item_Name_clean"), 300) or "Unspecified Item"

        best_seller_raw = _to_str_or_none(row.get("Best_Seller"), 64)
        is_bestseller_val = (
            _normalize_bestseller_flag(best_seller_raw)
            if best_seller_raw is not None
            else _to_int_or_none(row.get("Is_Bestseller"))
        )

        rec: dict[str, Any] = {
            "snapshot_batch_id": snapshot_batch_id,
            "observed_at": observed_at,
            "source_name": source_name,
            "city_clean": city_clean,
            "place_name_clean": place_clean,
            "city_raw": _to_str_or_none(row.get("City_raw"), 120),
            "place_name_raw": _to_str_or_none(row.get("Place_Name_raw"), 180),
            "cuisine_clean": cuisine_clean,
            "cuisine_raw": _to_str_or_none(row.get("Cuisine_raw"), 180),
            "restaurant_name_clean": rest_clean,
            "restaurant_name_raw": _to_str_or_none(row.get("Restaurant_Name_raw"), 255),
            "item_name_clean": item_clean,
            "item_name_raw": _to_str_or_none(row.get("Item_Name_raw"), 300),
            "item_raw": _to_str_or_none(row.get("Item_Name_raw"), 300),
            "price": _to_float_or_none(row.get("Prices")),
            "log_price": _to_float_or_none(row.get("Log_Price")),
            "price_per_vote": _to_float_or_none(row.get("Price_per_Vote")),
            "dining_rating": _to_float_or_none(row.get("Dining_Rating")),
            "delivery_rating": _to_float_or_none(row.get("Delivery_Rating")),
            "average_rating": _to_float_or_none(row.get("Average_Rating")),
            "dining_votes": _to_int_or_none(row.get("Dining_Votes")),
            "delivery_votes": _to_int_or_none(row.get("Delivery_Votes")),
            "votes": _to_int_or_none(row.get("Votes")),
            "total_votes": _to_int_or_none(row.get("Total_Votes")),
            "best_seller_raw": best_seller_raw,
            "is_bestseller": is_bestseller_val,
            "restaurant_popularity": _to_float_or_none(row.get("Restaurant_Popularity")),
            "is_highly_rated": _to_int_or_none(row.get("Is_Highly_Rated")),
            "is_expensive": _to_int_or_none(row.get("Is_Expensive")),
        }
        rec["row_fingerprint"] = compute_row_fingerprint(rec)
        records.append(rec)

    dq_checks = [
        {
            "check_name": "schema_columns_present",
            "status": "FAIL" if summary.missing_columns else "PASS",
            "failed_rows": len(summary.missing_columns),
            "details_json": {"missing_columns": summary.missing_columns, "extra_columns": summary.extra_columns},
        },
        {
            "check_name": "severe_numeric_and_rating_bounds",
            "status": "WARN" if len(quarantined_df) > 0 else "PASS",
            "failed_rows": int(len(quarantined_df)),
            "details_json": {
                "negative_price_rows": summary.negative_price_rows,
                "dining_rating_oor": summary.out_of_range_dining_rating_rows,
                "delivery_rating_oor": summary.out_of_range_delivery_rating_rows,
                "avg_rating_oor": summary.out_of_range_avg_rating_rows,
                "negative_votes_rows": summary.negative_votes_rows,
            },
        },
        {
            "check_name": "exact_duplicates_detected",
            "status": "WARN" if summary.exact_duplicate_rows > 0 else "PASS",
            "failed_rows": summary.exact_duplicate_rows,
            "details_json": {"business_key_duplicates": summary.business_key_duplicate_rows},
        },
    ]

    return records, quarantined_df, {"summary": summary.__dict__, "checks": dq_checks}
