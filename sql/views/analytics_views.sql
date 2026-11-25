-- Zomato Analytics 2.0 — Phase 5 Analytical Views (Areas A - F)

-- A. Restaurant Performance
CREATE OR REPLACE VIEW vw_restaurant_performance AS
WITH rest_agg AS (
    SELECT
        r.restaurant_id,
        r.restaurant_name_clean AS restaurant_name,
        l.city_clean AS city,
        l.place_name_clean AS place_name,
        c.cuisine_clean AS primary_cuisine,
        COUNT(f.snapshot_id) AS snapshot_observations,
        COUNT(DISTINCT f.menu_item_id) AS distinct_menu_items,
        ROUND(AVG(f.average_rating)::numeric, 2) AS avg_rating,
        ROUND(AVG(f.dining_rating)::numeric, 2) AS avg_dining_rating,
        ROUND(AVG(f.delivery_rating)::numeric, 2) AS avg_delivery_rating,
        ROUND((AVG(f.dining_rating) - AVG(f.delivery_rating))::numeric, 2) AS dining_vs_delivery_gap,
        COALESCE(SUM(f.total_votes), 0) AS total_votes_sum,
        ROUND(AVG(f.price)::numeric, 2) AS avg_item_price,
        ROUND(AVG(f.restaurant_popularity)::numeric, 4) AS avg_popularity_score
    FROM fact_menu_snapshot f
    JOIN dim_restaurant r ON f.restaurant_id = r.restaurant_id
    JOIN dim_location l ON f.location_id = l.location_id
    LEFT JOIN dim_cuisine c ON f.cuisine_id = c.cuisine_id
    GROUP BY
        r.restaurant_id,
        r.restaurant_name_clean,
        l.city_clean,
        l.place_name_clean,
        c.cuisine_clean
)
SELECT
    *,
    DENSE_RANK() OVER (
        PARTITION BY city
        ORDER BY avg_rating DESC NULLS LAST, total_votes_sum DESC
    ) AS city_rating_rank,
    RANK() OVER (
        ORDER BY total_votes_sum DESC, avg_rating DESC NULLS LAST
    ) AS overall_engagement_rank
FROM rest_agg;

-- B. Cuisine Analytics
CREATE OR REPLACE VIEW vw_cuisine_analytics AS
WITH cuisine_agg AS (
    SELECT
        COALESCE(c.cuisine_clean, 'Unspecified') AS cuisine,
        COUNT(f.snapshot_id) AS snapshot_rows,
        COUNT(DISTINCT f.restaurant_id) AS distinct_restaurants,
        COUNT(DISTINCT f.menu_item_id) AS distinct_menu_items,
        ROUND(AVG(f.price)::numeric, 2) AS avg_price,
        ROUND(MIN(f.price)::numeric, 2) AS min_price,
        ROUND(MAX(f.price)::numeric, 2) AS max_price,
        ROUND(AVG(f.average_rating)::numeric, 2) AS avg_rating,
        COALESCE(SUM(f.total_votes), 0) AS total_votes_sum,
        COALESCE(SUM(CASE WHEN COALESCE(f.is_bestseller, 0) = 1 THEN 1 ELSE 0 END), 0) AS bestseller_rows
    FROM fact_menu_snapshot f
    LEFT JOIN dim_cuisine c ON f.cuisine_id = c.cuisine_id
    GROUP BY COALESCE(c.cuisine_clean, 'Unspecified')
)
SELECT
    *,
    ROUND((max_price - min_price)::numeric, 2) AS price_range,
    RANK() OVER (ORDER BY snapshot_rows DESC, total_votes_sum DESC) AS popularity_rank,
    DENSE_RANK() OVER (ORDER BY avg_rating DESC NULLS LAST, distinct_restaurants DESC) AS rating_rank
FROM cuisine_agg;

-- C. Location Analytics
CREATE OR REPLACE VIEW vw_location_analytics AS
WITH loc_agg AS (
    SELECT
        l.location_id,
        l.city_clean AS city,
        l.place_name_clean AS place_name,
        COUNT(DISTINCT f.restaurant_id) AS restaurant_count,
        COUNT(DISTINCT f.menu_item_id) AS menu_item_count,
        COUNT(f.snapshot_id) AS snapshot_rows,
        ROUND(AVG(f.price)::numeric, 2) AS avg_price,
        ROUND(AVG(f.average_rating)::numeric, 2) AS avg_rating,
        COALESCE(SUM(f.total_votes), 0) AS total_votes_sum
    FROM fact_menu_snapshot f
    JOIN dim_location l ON f.location_id = l.location_id
    GROUP BY l.location_id, l.city_clean, l.place_name_clean
)
SELECT
    *,
    ROUND(
        (avg_price / NULLIF(AVG(avg_price) OVER (PARTITION BY city), 0))::numeric,
        2
    ) AS city_relative_price_index,
    DENSE_RANK() OVER (
        PARTITION BY city
        ORDER BY restaurant_count DESC, avg_rating DESC NULLS LAST
    ) AS city_density_rank
FROM loc_agg;

-- D. Menu Item Analytics
CREATE OR REPLACE VIEW vw_menu_item_analytics AS
WITH item_base AS (
    SELECT
        m.menu_item_id,
        r.restaurant_id,
        r.restaurant_name_clean AS restaurant_name,
        l.city_clean AS city,
        m.item_name_clean AS item_name,
        COUNT(f.snapshot_id) AS snapshot_rows,
        ROUND(AVG(f.price)::numeric, 2) AS avg_price,
        ROUND(AVG(f.average_rating)::numeric, 2) AS avg_rating,
        COALESCE(SUM(f.total_votes), 0) AS total_votes_sum,
        CASE
            WHEN AVG(f.price) IS NULL THEN 'Unknown'
            WHEN AVG(f.price) < 150 THEN 'Budget (<150)'
            WHEN AVG(f.price) < 350 THEN 'Mid-Range (150-349)'
            WHEN AVG(f.price) < 700 THEN 'Premium (350-699)'
            ELSE 'Luxury (700+)'
        END AS price_tier
    FROM fact_menu_snapshot f
    JOIN dim_menu_item m ON f.menu_item_id = m.menu_item_id
    JOIN dim_restaurant r ON f.restaurant_id = r.restaurant_id
    JOIN dim_location l ON f.location_id = l.location_id
    GROUP BY
        m.menu_item_id,
        r.restaurant_id,
        r.restaurant_name_clean,
        l.city_clean,
        m.item_name_clean
)
SELECT
    *,
    DENSE_RANK() OVER (
        PARTITION BY restaurant_id
        ORDER BY avg_price DESC NULLS LAST, menu_item_id ASC
    ) AS restaurant_price_rank
FROM item_base;

-- E. Historical Snapshot Trends (Multi-Timestamp / Batch Comparison)
CREATE OR REPLACE VIEW vw_historical_snapshot_trends AS
WITH batch_rest AS (
    SELECT
        f.restaurant_id,
        r.restaurant_name_clean AS restaurant_name,
        l.city_clean AS city,
        f.snapshot_batch_id,
        f.observed_at,
        COUNT(f.snapshot_id) AS items_in_batch,
        ROUND(AVG(f.price)::numeric, 2) AS avg_price,
        ROUND(AVG(f.average_rating)::numeric, 2) AS avg_rating,
        COALESCE(SUM(f.total_votes), 0) AS total_votes_sum
    FROM fact_menu_snapshot f
    JOIN dim_restaurant r ON f.restaurant_id = r.restaurant_id
    JOIN dim_location l ON f.location_id = l.location_id
    GROUP BY
        f.restaurant_id,
        r.restaurant_name_clean,
        l.city_clean,
        f.snapshot_batch_id,
        f.observed_at
)
SELECT
    *,
    MIN(observed_at) OVER (PARTITION BY restaurant_id) AS first_observed_at,
    LAG(avg_price) OVER (PARTITION BY restaurant_id ORDER BY observed_at, snapshot_batch_id) AS prev_avg_price,
    ROUND(
        (avg_price - LAG(avg_price) OVER (PARTITION BY restaurant_id ORDER BY observed_at, snapshot_batch_id))::numeric,
        2
    ) AS avg_price_delta,
    LAG(avg_rating) OVER (PARTITION BY restaurant_id ORDER BY observed_at, snapshot_batch_id) AS prev_avg_rating,
    ROUND(
        (avg_rating - LAG(avg_rating) OVER (PARTITION BY restaurant_id ORDER BY observed_at, snapshot_batch_id))::numeric,
        2
    ) AS avg_rating_delta
FROM batch_rest;

-- F. Business Intelligence: High-Rating / Low-Price & Value Positioning
CREATE OR REPLACE VIEW vw_bi_value_opportunities AS
WITH rest_metrics AS (
    SELECT
        r.restaurant_id,
        r.restaurant_name_clean AS restaurant_name,
        l.city_clean AS city,
        l.place_name_clean AS place_name,
        COALESCE(c.cuisine_clean, 'Unspecified') AS cuisine,
        ROUND(AVG(f.average_rating)::numeric, 2) AS avg_rating,
        ROUND(AVG(f.price)::numeric, 2) AS avg_price,
        COALESCE(SUM(f.total_votes), 0) AS total_votes_sum
    FROM fact_menu_snapshot f
    JOIN dim_restaurant r ON f.restaurant_id = r.restaurant_id
    JOIN dim_location l ON f.location_id = l.location_id
    LEFT JOIN dim_cuisine c ON f.cuisine_id = c.cuisine_id
    GROUP BY
        r.restaurant_id,
        r.restaurant_name_clean,
        l.city_clean,
        l.place_name_clean,
        c.cuisine_clean
),
benchmarked AS (
    SELECT
        *,
        AVG(avg_rating) OVER (PARTITION BY city) AS city_mean_rating,
        AVG(avg_price) OVER (PARTITION BY city) AS city_mean_price
    FROM rest_metrics
    WHERE avg_rating IS NOT NULL AND avg_price IS NOT NULL AND avg_price > 0
)
SELECT
    restaurant_id,
    restaurant_name,
    city,
    place_name,
    cuisine,
    avg_rating,
    ROUND(city_mean_rating::numeric, 2) AS city_mean_rating,
    avg_price,
    ROUND(city_mean_price::numeric, 2) AS city_mean_price,
    total_votes_sum,
    CASE
        WHEN avg_rating >= city_mean_rating AND avg_price <= city_mean_price THEN 'High Rating / Lower Price'
        WHEN avg_rating >= city_mean_rating AND avg_price > city_mean_price THEN 'High Rating / Higher Price'
        WHEN avg_rating < city_mean_rating AND avg_price <= city_mean_price THEN 'Lower Rating / Lower Price'
        ELSE 'Lower Rating / Higher Price'
    END AS positioning_quadrant,
    ROUND(
        ((avg_rating * LN(1.0 + GREATEST(total_votes_sum, 0) + 1.0)) / NULLIF(avg_price, 0))::numeric,
        4
    ) AS value_index
FROM benchmarked;
