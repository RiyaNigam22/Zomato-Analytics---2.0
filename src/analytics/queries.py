"""Reusable SQL analytics queries and report generator for Zomato Analytics 2.0."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.db.connection import get_engine

ANALYTICAL_QUERIES: dict[str, dict[str, str]] = {
    "top_restaurants_by_city": {
        "area": "A. Restaurant Performance",
        "business_question": "Which restaurants rank highest within each city by rating and engagement volume?",
        "metric_definition": "city_rating_rank via DENSE_RANK() partitioned by city ordered by avg_rating DESC, total_votes_sum DESC.",
        "interpretation": "Identifies top-performing restaurants per city while factoring in review/vote engagement.",
        "limitations": "Depends on rows loaded into fact_menu_snapshot; does not prove causal drivers of ratings.",
        "sql": """
            SELECT
                city,
                place_name,
                restaurant_name,
                primary_cuisine,
                avg_rating,
                dining_vs_delivery_gap,
                total_votes_sum,
                avg_item_price,
                city_rating_rank
            FROM vw_restaurant_performance
            WHERE city_rating_rank <= 5
            ORDER BY city ASC, city_rating_rank ASC, total_votes_sum DESC
        """,
    },
    "cuisine_competitiveness": {
        "area": "B. Cuisine Analytics",
        "business_question": "How do cuisines compare across restaurant count, average price, price spread, and rating?",
        "metric_definition": "distinct_restaurants, avg_price, price_range (max - min), avg_rating, and popularity_rank.",
        "interpretation": "Separates high-volume/high-competition cuisines from specialized or higher-priced categories.",
        "limitations": "Raw Is_Bestseller was constant in baseline CSV; bestseller counts reflect normalized indicator values.",
        "sql": """
            SELECT
                cuisine,
                distinct_restaurants,
                distinct_menu_items,
                snapshot_rows,
                avg_price,
                price_range,
                avg_rating,
                total_votes_sum,
                popularity_rank
            FROM vw_cuisine_analytics
            ORDER BY popularity_rank ASC
            LIMIT 20
        """,
    },
    "location_density_and_pricing": {
        "area": "C. Location Analytics",
        "business_question": "Which sub-locations have the highest restaurant density and how do their prices compare to city averages?",
        "metric_definition": "restaurant_count, city_density_rank, and city_relative_price_index (location avg_price / city avg_price).",
        "interpretation": "Index > 1.0 indicates higher average item prices than the city benchmark; < 1.0 indicates lower.",
        "limitations": "Reflects observed dataset coverage per location rather than an external census.",
        "sql": """
            SELECT
                city,
                place_name,
                restaurant_count,
                menu_item_count,
                avg_price,
                city_relative_price_index,
                avg_rating,
                city_density_rank
            FROM vw_location_analytics
            WHERE city_density_rank <= 5
            ORDER BY city ASC, city_density_rank ASC
        """,
    },
    "menu_price_tiers": {
        "area": "D. Menu Analytics",
        "business_question": "How are menu items distributed across price tiers and what are the highest-priced items per restaurant?",
        "metric_definition": "price_tier bucketed from avg_price and restaurant_price_rank via DENSE_RANK() per restaurant.",
        "interpretation": "Shows menu pricing structure and top-priced dishes within each restaurant.",
        "limitations": "Item names are standardized text strings; dish-level ratings are inherited from listing/restaurant records.",
        "sql": """
            SELECT
                price_tier,
                COUNT(*) AS menu_item_count,
                ROUND(AVG(avg_price)::numeric, 2) AS tier_avg_price,
                ROUND(AVG(avg_rating)::numeric, 2) AS tier_avg_rating
            FROM vw_menu_item_analytics
            GROUP BY price_tier
            ORDER BY tier_avg_price DESC NULLS LAST
        """,
    },
    "historical_snapshot_changes": {
        "area": "E. Historical Snapshot Analytics",
        "business_question": "How do average price and rating change across distinct snapshot timestamps for a restaurant?",
        "metric_definition": "avg_price_delta and avg_rating_delta computed with LAG() ordered by observed_at.",
        "interpretation": "Valid only across observations captured at distinct timestamps; zero/null deltas indicate single-timestamp records.",
        "limitations": "Baseline CSV lacks original timestamps; historical deltas appear once multiple timestamped batches exist.",
        "sql": """
            SELECT
                restaurant_name,
                city,
                snapshot_batch_id,
                observed_at,
                first_observed_at,
                avg_price,
                prev_avg_price,
                avg_price_delta,
                avg_rating,
                prev_avg_rating,
                avg_rating_delta
            FROM vw_historical_snapshot_trends
            WHERE prev_avg_price IS NOT NULL OR prev_avg_rating IS NOT NULL
            ORDER BY observed_at DESC, restaurant_name ASC
            LIMIT 25
        """,
    },
    "bi_high_rating_low_price": {
        "area": "F. Business Intelligence",
        "business_question": "Which restaurants achieve above-benchmark ratings at or below city average prices?",
        "metric_definition": "positioning_quadrant comparing restaurant avg_rating and avg_price against city benchmarks, plus value_index.",
        "interpretation": "Surfaces candidate value-positioned restaurants for comparative analysis.",
        "limitations": "Descriptive screening index only; does not establish causation or operational margins.",
        "sql": """
            SELECT
                restaurant_name,
                city,
                place_name,
                cuisine,
                avg_rating,
                city_mean_rating,
                avg_price,
                city_mean_price,
                total_votes_sum,
                value_index
            FROM vw_bi_value_opportunities
            WHERE positioning_quadrant = 'High Rating / Lower Price'
            ORDER BY value_index DESC NULLS LAST
            LIMIT 25
        """,
    },
}


def apply_analytical_views(views_sql_path: Path, engine: Engine | None = None) -> None:
    if not views_sql_path.exists():
        raise FileNotFoundError(f"Views SQL file not found: {views_sql_path}")
    raw_sql = views_sql_path.read_text(encoding="utf-8-sig")
    cleaned_lines = [
        line for line in raw_sql.splitlines() if line.strip() and not line.strip().startswith("--")
    ]
    statements = [stmt.strip() for stmt in "\n".join(cleaned_lines).split(";") if stmt.strip()]

    target_engine = engine or get_engine()
    with target_engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))


def run_named_query(
    query_key: str,
    *,
    engine: Engine | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> pd.DataFrame:
    if query_key not in ANALYTICAL_QUERIES:
        raise KeyError(f"Unknown analytical query key: {query_key}")
    sql_str = ANALYTICAL_QUERIES[query_key]["sql"].strip()

    if session_factory is not None:
        with session_factory() as session:
            result = session.execute(text(sql_str))
            return pd.DataFrame(result.fetchall(), columns=list(result.keys()))

    target_engine = engine or get_engine()
    with target_engine.connect() as conn:
        result = conn.execute(text(sql_str))
        return pd.DataFrame(result.fetchall(), columns=list(result.keys()))


def run_all_analytics_and_export(
    *,
    views_sql_path: Path,
    output_dir: Path,
    engine: Engine | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    if session_factory is None:
        apply_analytical_views(views_sql_path, engine=engine)

    generated_at = datetime.now(timezone.utc).isoformat()
    summary_payload: dict[str, Any] = {
        "generated_at_utc": generated_at,
        "queries": {},
    }
    report_lines: list[str] = [
        "# Zomato Analytics 2.0 — Phase 5 Business Insights Report",
        "",
        f"- **Generated (UTC):** {generated_at}",
        "- **Scope:** Existing Zomato dataset in PostgreSQL (`fact_menu_snapshot` & dimensions; no external web scraping).",
        "",
    ]

    for key, meta in ANALYTICAL_QUERIES.items():
        df = run_named_query(key, engine=engine, session_factory=session_factory)
        csv_out = output_dir / f"{key}.csv"
        df.to_csv(csv_out, index=False)

        summary_payload["queries"][key] = {
            "area": meta["area"],
            "business_question": meta["business_question"],
            "row_count": int(len(df)),
            "csv_file": str(csv_out),
        }

        report_lines.extend(
            [
                f"## {meta['area']} — `{key}`",
                f"- **Business Question:** {meta['business_question']}",
                f"- **Metric Definition:** {meta['metric_definition']}",
                f"- **Interpretation:** {meta['interpretation']}",
                f"- **Limitations:** {meta['limitations']}",
                f"- **Rows Returned:** {len(df):,} (`{csv_out.name}`)",
                "",
            ]
        )

    json_path = output_dir / "analytics_summary.json"
    json_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    md_path = output_dir / "business_insights_report.md"
    md_path.write_text("\n".join(report_lines), encoding="utf-8")

    return {
        "generated_at_utc": generated_at,
        "output_dir": str(output_dir),
        "report_path": str(md_path),
        "summary_path": str(json_path),
        "query_count": len(ANALYTICAL_QUERIES),
    }
