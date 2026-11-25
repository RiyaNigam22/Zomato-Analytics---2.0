# Zomato Analytics 2.0 — Phase 5 Business Insights Report

- **Generated (UTC):** 2026-11-25T14:28:51.708220+00:00
- **Scope:** Existing Zomato dataset in PostgreSQL (`fact_menu_snapshot` & dimensions; no external web scraping).

## A. Restaurant Performance — `top_restaurants_by_city`
- **Business Question:** Which restaurants rank highest within each city by rating and engagement volume?
- **Metric Definition:** city_rating_rank via DENSE_RANK() partitioned by city ordered by avg_rating DESC, total_votes_sum DESC.
- **Interpretation:** Identifies top-performing restaurants per city while factoring in review/vote engagement.
- **Limitations:** Depends on rows loaded into fact_menu_snapshot; does not prove causal drivers of ratings.
- **Rows Returned:** 74 (`top_restaurants_by_city.csv`)

## B. Cuisine Analytics — `cuisine_competitiveness`
- **Business Question:** How do cuisines compare across restaurant count, average price, price spread, and rating?
- **Metric Definition:** distinct_restaurants, avg_price, price_range (max - min), avg_rating, and popularity_rank.
- **Interpretation:** Separates high-volume/high-competition cuisines from specialized or higher-priced categories.
- **Limitations:** Raw Is_Bestseller was constant in baseline CSV; bestseller counts reflect normalized indicator values.
- **Rows Returned:** 20 (`cuisine_competitiveness.csv`)

## C. Location Analytics — `location_density_and_pricing`
- **Business Question:** Which sub-locations have the highest restaurant density and how do their prices compare to city averages?
- **Metric Definition:** restaurant_count, city_density_rank, and city_relative_price_index (location avg_price / city avg_price).
- **Interpretation:** Index > 1.0 indicates higher average item prices than the city benchmark; < 1.0 indicates lower.
- **Limitations:** Reflects observed dataset coverage per location rather than an external census.
- **Rows Returned:** 70 (`location_density_and_pricing.csv`)

## D. Menu Analytics — `menu_price_tiers`
- **Business Question:** How are menu items distributed across price tiers and what are the highest-priced items per restaurant?
- **Metric Definition:** price_tier bucketed from avg_price and restaurant_price_rank via DENSE_RANK() per restaurant.
- **Interpretation:** Shows menu pricing structure and top-priced dishes within each restaurant.
- **Limitations:** Item names are standardized text strings; dish-level ratings are inherited from listing/restaurant records.
- **Rows Returned:** 4 (`menu_price_tiers.csv`)

## E. Historical Snapshot Analytics — `historical_snapshot_changes`
- **Business Question:** How do average price and rating change across distinct snapshot timestamps for a restaurant?
- **Metric Definition:** avg_price_delta and avg_rating_delta computed with LAG() ordered by observed_at.
- **Interpretation:** Valid only across observations captured at distinct timestamps; zero/null deltas indicate single-timestamp records.
- **Limitations:** Baseline CSV lacks original timestamps; historical deltas appear once multiple timestamped batches exist.
- **Rows Returned:** 25 (`historical_snapshot_changes.csv`)

## F. Business Intelligence — `bi_high_rating_low_price`
- **Business Question:** Which restaurants achieve above-benchmark ratings at or below city average prices?
- **Metric Definition:** positioning_quadrant comparing restaurant avg_rating and avg_price against city benchmarks, plus value_index.
- **Interpretation:** Surfaces candidate value-positioned restaurants for comparative analysis.
- **Limitations:** Descriptive screening index only; does not establish causation or operational margins.
- **Rows Returned:** 25 (`bi_high_rating_low_price.csv`)
