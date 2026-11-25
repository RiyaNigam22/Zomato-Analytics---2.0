"""Unit tests for Phase 1 validation and cleaning pipeline."""

from pathlib import Path
import pandas as pd
import pytest

from src.processing.cleaner import clean_and_report
from src.processing.validator import EXPECTED_COLUMNS, run_validation, validate_schema


def _sample_df() -> pd.DataFrame:
    row = {
        "Restaurant_Name": "  spice hub  ",
        "Dining_Rating": 4.2,
        "Delivery_Rating": 4.0,
        "Dining_Votes": 120,
        "Delivery_Votes": 80,
        "Cuisine": " north indian ",
        "Place_Name": " indiranagar ",
        "City": " bengaluru ",
        "Item_Name": "paneer butter masala",
        "Best_Seller": "1",
        "Votes": 200,
        "Prices": 280.0,
        "Average_Rating": 4.1,
        "Total_Votes": 200,
        "Price_per_Vote": 1.4,
        "Log_Price": 5.638,
        "Is_Bestseller": 1,
        "Restaurant_Popularity": 0.85,
        "Avg_Rating_Restaurant": 4.1,
        "Avg_Price_Restaurant": 280.0,
        "Avg_Rating_Cuisine": 4.0,
        "Avg_Price_Cuisine": 260.0,
        "Avg_Rating_City": 4.05,
        "Avg_Price_City": 270.0,
        "Is_Highly_Rated": 1,
        "Is_Expensive": 0,
    }
    return pd.DataFrame([row, row.copy()])


def test_schema_matches_expected_26_columns() -> None:
    df = _sample_df()
    missing, extra = validate_schema(df)
    assert len(EXPECTED_COLUMNS) == 26
    assert missing == []
    assert extra == []


def test_validation_detects_exact_duplicates_and_constant_bestseller() -> None:
    df = _sample_df()
    summary, _ = run_validation(df)
    assert summary.row_count == 2
    assert summary.exact_duplicate_rows == 1
    assert summary.is_bestseller_distinct_values == [1]


def test_clean_and_report_preserves_raw_and_standardizes_strings(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    raw_file = raw_dir / "enhanced_zomato_dataset_clean.csv"
    df_orig = _sample_df()
    df_orig.to_csv(raw_file, index=False)
    raw_bytes_before = raw_file.read_bytes()

    report = clean_and_report(
        raw_csv_path=raw_file,
        processed_dir=tmp_path / "processed",
        quarantine_dir=tmp_path / "quarantine",
        drop_exact_duplicates=False,
    )

    assert raw_file.read_bytes() == raw_bytes_before
    cleaned = pd.read_csv(tmp_path / "processed" / "zomato_baseline_clean.csv")
    assert len(cleaned) == 2
    assert cleaned.loc[0, "Restaurant_Name"] == "Spice Hub"
    assert cleaned.loc[0, "City"] == "Bengaluru"
    assert cleaned.loc[0, "Place_Name"] == "Indiranagar"
    assert cleaned.loc[0, "has_original_timestamp"] is False or str(cleaned.loc[0, "has_original_timestamp"]).lower() == "false"
    assert report["pre_cleaning_validation"]["exact_duplicate_rows"] == 1