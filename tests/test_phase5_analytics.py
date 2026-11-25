"""Tests for Phase 5 analytical view definitions and query registry."""

from pathlib import Path

from src.analytics.queries import ANALYTICAL_QUERIES


def test_analytics_views_sql_covers_all_required_areas() -> None:
    views_path = Path("sql/views/analytics_views.sql")
    assert views_path.exists()
    sql_text = views_path.read_text(encoding="utf-8").lower()

    expected_views = [
        "vw_restaurant_performance",
        "vw_cuisine_analytics",
        "vw_location_analytics",
        "vw_menu_item_analytics",
        "vw_historical_snapshot_trends",
        "vw_bi_value_opportunities",
    ]
    for view_name in expected_views:
        assert view_name in sql_text, f"Missing expected view {view_name}"

    assert "dense_rank()" in sql_text
    assert "lag(" in sql_text
    assert "case" in sql_text
    assert "nullif(" in sql_text


def test_analytical_query_catalog_has_required_documentation_fields() -> None:
    assert len(ANALYTICAL_QUERIES) >= 6
    required_keys = {
        "area",
        "business_question",
        "metric_definition",
        "interpretation",
        "limitations",
        "sql",
    }
    for name, spec in ANALYTICAL_QUERIES.items():
        missing = required_keys - set(spec.keys())
        assert not missing, f"Query '{name}' missing fields: {missing}"
        assert spec["sql"].strip()
