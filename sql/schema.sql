-- Zomato Analytics 2.0 PostgreSQL Schema (Existing Dataset + Historical Snapshots)

CREATE TABLE IF NOT EXISTS dim_location (
    location_id         BIGSERIAL PRIMARY KEY,
    city_clean          VARCHAR(120) NOT NULL,
    place_name_clean    VARCHAR(180) NOT NULL,
    city_raw            VARCHAR(120),
    place_name_raw      VARCHAR(180),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_dim_location_city_place UNIQUE (city_clean, place_name_clean)
);

CREATE TABLE IF NOT EXISTS dim_cuisine (
    cuisine_id          BIGSERIAL PRIMARY KEY,
    cuisine_clean       VARCHAR(180) NOT NULL,
    cuisine_raw         VARCHAR(180),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_dim_cuisine_clean UNIQUE (cuisine_clean)
);

CREATE TABLE IF NOT EXISTS dim_restaurant (
    restaurant_id           BIGSERIAL PRIMARY KEY,
    restaurant_name_clean   VARCHAR(255) NOT NULL,
    restaurant_name_raw     VARCHAR(255),
    location_id             BIGINT NOT NULL REFERENCES dim_location(location_id) ON DELETE RESTRICT,
    primary_cuisine_id      BIGINT REFERENCES dim_cuisine(cuisine_id) ON DELETE SET NULL,
    source_name             VARCHAR(64) NOT NULL DEFAULT 'baseline_csv',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_dim_restaurant_name_loc UNIQUE (restaurant_name_clean, location_id)
);

CREATE TABLE IF NOT EXISTS dim_menu_item (
    menu_item_id        BIGSERIAL PRIMARY KEY,
    restaurant_id       BIGINT NOT NULL REFERENCES dim_restaurant(restaurant_id) ON DELETE CASCADE,
    item_name_clean     VARCHAR(300) NOT NULL,
    item_name_raw       VARCHAR(300),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_dim_menu_item_rest_item UNIQUE (restaurant_id, item_name_clean)
);

CREATE TABLE IF NOT EXISTS etl_run_logs (
    run_id              BIGSERIAL PRIMARY KEY,
    pipeline_mode       VARCHAR(32) NOT NULL,          -- 'full' | 'incremental'
    source_name         VARCHAR(64) NOT NULL DEFAULT 'baseline_csv',
    snapshot_batch_id   VARCHAR(64) NOT NULL,
    status              VARCHAR(24) NOT NULL,          -- 'RUNNING' | 'SUCCESS' | 'FAILED'
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at            TIMESTAMPTZ,
    rows_read           INTEGER NOT NULL DEFAULT 0,
    rows_quarantined    INTEGER NOT NULL DEFAULT 0,
    rows_upserted       INTEGER NOT NULL DEFAULT 0,
    error_message       TEXT
);

CREATE TABLE IF NOT EXISTS data_quality_results (
    dq_result_id        BIGSERIAL PRIMARY KEY,
    run_id              BIGINT REFERENCES etl_run_logs(run_id) ON DELETE SET NULL,
    checked_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    dataset_scope       VARCHAR(100) NOT NULL,
    check_name          VARCHAR(120) NOT NULL,
    status              VARCHAR(16) NOT NULL,          -- 'PASS' | 'WARN' | 'FAIL'
    failed_rows         INTEGER NOT NULL DEFAULT 0,
    details_json        JSONB
);

CREATE TABLE IF NOT EXISTS fact_menu_snapshot (
    snapshot_id             BIGSERIAL PRIMARY KEY,
    run_id                  BIGINT REFERENCES etl_run_logs(run_id) ON DELETE SET NULL,
    snapshot_batch_id       VARCHAR(64) NOT NULL,
    observed_at             TIMESTAMPTZ NOT NULL,
    source_name             VARCHAR(64) NOT NULL DEFAULT 'baseline_csv',
    row_fingerprint         CHAR(64) NOT NULL,
    restaurant_id           BIGINT NOT NULL REFERENCES dim_restaurant(restaurant_id) ON DELETE RESTRICT,
    menu_item_id            BIGINT NOT NULL REFERENCES dim_menu_item(menu_item_id) ON DELETE RESTRICT,
    location_id             BIGINT NOT NULL REFERENCES dim_location(location_id) ON DELETE RESTRICT,
    cuisine_id              BIGINT REFERENCES dim_cuisine(cuisine_id) ON DELETE SET NULL,
    price                   NUMERIC(12, 2),
    log_price               DOUBLE PRECISION,
    price_per_vote          DOUBLE PRECISION,
    dining_rating           NUMERIC(4, 2),
    delivery_rating         NUMERIC(4, 2),
    average_rating          NUMERIC(4, 2),
    dining_votes            INTEGER,
    delivery_votes          INTEGER,
    votes                   INTEGER,
    total_votes             INTEGER,
    best_seller_raw         VARCHAR(64),
    is_bestseller           SMALLINT,
    restaurant_popularity   DOUBLE PRECISION,
    is_highly_rated         SMALLINT,
    is_expensive            SMALLINT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_fact_snapshot_batch_fingerprint UNIQUE (snapshot_batch_id, row_fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_dim_restaurant_location ON dim_restaurant(location_id);
CREATE INDEX IF NOT EXISTS idx_dim_restaurant_cuisine ON dim_restaurant(primary_cuisine_id);
CREATE INDEX IF NOT EXISTS idx_dim_menu_item_restaurant ON dim_menu_item(restaurant_id);
CREATE INDEX IF NOT EXISTS idx_fact_snapshot_observed_at ON fact_menu_snapshot(observed_at);
CREATE INDEX IF NOT EXISTS idx_fact_snapshot_restaurant_time ON fact_menu_snapshot(restaurant_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_fact_snapshot_item_time ON fact_menu_item(restaurant_id) ;
CREATE INDEX IF NOT EXISTS idx_fact_snapshot_location ON fact_menu_snapshot(location_id);
CREATE INDEX IF NOT EXISTS idx_fact_snapshot_cuisine ON fact_menu_snapshot(cuisine_id);
CREATE INDEX IF NOT EXISTS idx_etl_run_logs_started_at ON etl_run_logs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_dq_results_run_id ON data_quality_results(run_id);
