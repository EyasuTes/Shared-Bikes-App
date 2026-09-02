-- Raw copies make pipeline runs auditable and allow failed transformations to be replayed.
CREATE TABLE IF NOT EXISTS gbfs_raw_data (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  feed_name TEXT NOT NULL CHECK (
    feed_name IN ('station_information', 'station_status')
  ),
  gbfs_version VARCHAR(10) NOT NULL,
  source_last_updated TIMESTAMPTZ NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  payload JSONB NOT NULL,
  UNIQUE (feed_name, source_last_updated)
);

-- One current, cleaned record for each physical or virtual station.
CREATE TABLE IF NOT EXISTS stations (
  station_id TEXT PRIMARY KEY,
  name TEXT NOT NULL CHECK (char_length(trim(name)) > 0),
  short_name TEXT,
  latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
  longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
  capacity INTEGER NOT NULL CHECK (capacity >= 0),
  source_last_updated TIMESTAMPTZ NOT NULL,
  loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Append-only observations let us calculate availability trends over time.
CREATE TABLE IF NOT EXISTS station_status_history (
  station_id TEXT NOT NULL REFERENCES stations (station_id),
  reported_at TIMESTAMPTZ NOT NULL,
  bikes_available INTEGER NOT NULL CHECK (bikes_available >= 0),
  bikes_disabled INTEGER NOT NULL CHECK (bikes_disabled >= 0),
  docks_available INTEGER NOT NULL CHECK (docks_available >= 0),
  docks_disabled INTEGER NOT NULL CHECK (docks_disabled >= 0),
  is_installed BOOLEAN NOT NULL,
  is_renting BOOLEAN NOT NULL,
  is_returning BOOLEAN NOT NULL,
  loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (station_id, reported_at)
);

CREATE INDEX IF NOT EXISTS station_status_history_reported_at_idx
  ON station_status_history (reported_at DESC);

-- The streaming alert consumer keeps one open alert per station. Resolved alerts
-- remain in this table so operators can review what happened later.
CREATE TABLE IF NOT EXISTS station_alerts (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  station_id TEXT NOT NULL,
  station_name TEXT NOT NULL,
  severity VARCHAR(10) NOT NULL CHECK (severity IN ('warning', 'critical')),
  bikes_available INTEGER NOT NULL CHECK (bikes_available >= 0),
  depletion_rate_per_minute DOUBLE PRECISION CHECK (
    depletion_rate_per_minute IS NULL OR depletion_rate_per_minute >= 0
  ),
  predicted_minutes_to_empty DOUBLE PRECISION CHECK (
    predicted_minutes_to_empty IS NULL OR predicted_minutes_to_empty >= 0
  ),
  reason TEXT NOT NULL,
  first_reported_at TIMESTAMPTZ NOT NULL,
  last_reported_at TIMESTAMPTZ NOT NULL,
  last_event_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolved_at TIMESTAMPTZ,
  CHECK (last_reported_at >= first_reported_at)
);

-- A partial unique index prevents duplicate open alerts while preserving history.
CREATE UNIQUE INDEX IF NOT EXISTS station_alerts_one_active_per_station_idx
  ON station_alerts (station_id)
  WHERE resolved_at IS NULL;

CREATE INDEX IF NOT EXISTS station_alerts_active_severity_idx
  ON station_alerts (severity, updated_at DESC)
  WHERE resolved_at IS NULL;
