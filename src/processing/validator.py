"""Schema and data quality validation for enhanced_zomato_dataset_clean.csv."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import numpy as np
import pandas as pd

EXPECTED_COLUMNS: list[str] = [
    "Restaurant_Name",
    "Dining_Rating",
    "Delivery_Rating",
    "Dining_Votes",
    "Delivery_Votes",
    "Cuisine",
    "Place_Name",
    "City",
    "Item_Name",
    "Best_Seller",
    "Votes",
    "Prices",
    "Average_Rating",
    "Total_Votes",
    "Price_per_Vote",
    "Log_Price",
    "Is_Bestseller",
    "Restaurant_Popularity",
    "Avg_Rating_Restaurant",
    "Avg_Price_Restaurant",
    "Avg_Rating_Cuisine",
    "Avg_Price_Cuisine",
    "Avg_Rating_City",
    "Avg_Price_City",
    "Is_Highly_Rated",
    "Is_Expensive",
]

BUSINESS_KEY_COLUMNS: list[str] = [
    "Restaurant_Name",
    "City",
    "Place_Name",
    "Item_Name",
]


@dataclass
class ValidationSummary:
    row_count: int
    column_count: int
    missing_columns: list[str]
    extra_columns: list[str]
    null_counts_by_column: dict[str, int]
    exact_duplicate_rows: int
    business_key_duplicate_rows: int
    is_bestseller_distinct_values: list[Any]
    invalid_price_rows: int
    zero_price_rows: int
    negative_price_rows: int
    out_of_range_dining_rating_rows: int
    out_of_range_delivery_rating_rows: int
    out_of_range_avg_rating_rows: int
    negative_votes_rows: int
    infinite_or_nan_derived_rows: int


def validate_schema(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Return missing and unexpected column names relative to EXPECTED_COLUMNS."""
    actual = list(df.columns)
    missing = [col for col in EXPECTED_COLUMNS if col not in actual]
    extra = [col for col in actual if col not in EXPECTED_COLUMNS]
    return missing, extra


def _numeric_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(dtype="float64", index=df.index)
    return pd.to_numeric(df[col], errors="coerce")


def run_validation(df: pd.DataFrame) -> tuple[ValidationSummary, dict[str, pd.Series]]:
    """Run non-destructive validation checks and return summary + boolean anomaly masks."""
    missing_cols, extra_cols = validate_schema(df)
    null_counts = {col: int(df[col].isna().sum()) for col in df.columns}

    exact_dup_mask = df.duplicated(keep="first")
    present_bkey = [c for c in BUSINESS_KEY_COLUMNS if c in df.columns]
    bkey_dup_mask = (
        df.duplicated(subset=present_bkey, keep="first")
        if present_bkey
        else pd.Series(False, index=df.index)
    )

    is_bs_vals = (
        sorted(df["Is_Bestseller"].dropna().unique().tolist(), key=lambda x: str(x))
        if "Is_Bestseller" in df.columns
        else []
    )

    prices = _numeric_series(df, "Prices")
    neg_price_mask = prices.notna() & (prices < 0)
    zero_price_mask = prices.notna() & (prices == 0)
    invalid_price_mask = neg_price_mask | prices.isna()

    dining_rating = _numeric_series(df, "Dining_Rating")
    delivery_rating = _numeric_series(df, "Delivery_Rating")
    avg_rating = _numeric_series(df, "Average_Rating")

    # Ratings outside standard [0.0, 5.0] scale are flagged as anomalies
    dining_oor_mask = dining_rating.notna() & ((dining_rating < 0) | (dining_rating > 5))
    delivery_oor_mask = delivery_rating.notna() & ((delivery_rating < 0) | (delivery_rating > 5))
    avg_oor_mask = avg_rating.notna() & ((avg_rating < 0) | (avg_rating > 5))

    vote_cols = [c for c in ["Dining_Votes", "Delivery_Votes", "Votes", "Total_Votes"] if c in df.columns]
    neg_votes_mask = pd.Series(False, index=df.index)
    for vc in vote_cols:
        s = _numeric_series(df, vc)
        neg_votes_mask = neg_votes_mask | (s.notna() & (s < 0))

    derived_cols = [
        c for c in ["Price_per_Vote", "Log_Price", "Restaurant_Popularity"] if c in df.columns
    ]
    inf_derived_mask = pd.Series(False, index=df.index)
    for dc in derived_cols:
        s = _numeric_series(df, dc)
        inf_derived_mask = inf_derived_mask | np.isinf(s.to_numpy(dtype="float64", na_value=np.nan))

    masks = {
        "exact_duplicate": exact_dup_mask,
        "business_key_duplicate": bkey_dup_mask,
        "negative_price": neg_price_mask,
        "zero_price": zero_price_mask,
        "dining_rating_out_of_range": dining_oor_mask,
        "delivery_rating_out_of_range": delivery_oor_mask,
        "avg_rating_out_of_range": avg_oor_mask,
        "negative_votes": neg_votes_mask,
        "infinite_derived_metric": inf_derived_mask,
    }

    summary = ValidationSummary(
        row_count=int(len(df)),
        column_count=int(len(df.columns)),
        missing_columns=missing_cols,
        extra_columns=extra_cols,
        null_counts_by_column=null_counts,
        exact_duplicate_rows=int(exact_dup_mask.sum()),
        business_key_duplicate_rows=int(bkey_dup_mask.sum()),
        is_bestseller_distinct_values=is_bs_vals,
        invalid_price_rows=int(invalid_price_mask.sum()),
        zero_price_rows=int(zero_price_mask.sum()),
        negative_price_rows=int(neg_price_mask.sum()),
        out_of_range_dining_rating_rows=int(dining_oor_mask.sum()),
        out_of_range_delivery_rating_rows=int(delivery_oor_mask.sum()),
        out_of_range_avg_rating_rows=int(avg_oor_mask.sum()),
        negative_votes_rows=int(neg_votes_mask.sum()),
        infinite_or_nan_derived_rows=int(inf_derived_mask.sum()),
    )
    return summary, masks