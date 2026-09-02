const express = require('express');
const { Pool } = require('pg');

const PORT = process.env.PORT || 5000;
const LOW_BIKE_THRESHOLD = 5;
const ALLOWED_RISK_FILTERS = new Set(['all', 'low', 'empty', 'offline']);
const ALLOWED_ALERT_SEVERITIES = new Set(['all', 'warning', 'critical']);
const ALLOWED_STATION_SORTS = new Set(['name', 'bikes-low', 'bikes-high']);

function parseBoundedInteger(value, fallback, minimum, maximum) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isInteger(parsed)) return fallback;
  return Math.min(Math.max(parsed, minimum), maximum);
}

function normalizeRiskFilter(value) {
  return ALLOWED_RISK_FILTERS.has(value) ? value : 'all';
}

function normalizeAlertSeverity(value) {
  return ALLOWED_ALERT_SEVERITIES.has(value) ? value : 'all';
}

function normalizeStationSort(value) {
  return ALLOWED_STATION_SORTS.has(value) ? value : 'name';
}

function stationOrderBy(sort) {
  if (sort === 'bikes-low') {
    return 'CASE WHEN bikes_available IS NULL THEN 1 ELSE 0 END, bikes_available ASC, name ASC';
  }
  if (sort === 'bikes-high') {
    return 'CASE WHEN bikes_available IS NULL THEN 1 ELSE 0 END, bikes_available DESC, name ASC';
  }
  return 'name ASC';
}

function createApp(databasePool) {
  const app = express();
  app.use(express.json());

  app.get('/api', (req, res) => {
    res.json({ message: 'Capital Bikeshare operations API' });
  });

  app.get('/api/bikeshare/summary', async (req, res) => {
    try {
      const result = await databasePool.query(
        `
          WITH latest_status AS (
            SELECT DISTINCT ON (station_id)
              station_id,
              reported_at,
              bikes_available,
              docks_available,
              is_installed,
              is_renting,
              is_returning
            FROM station_status_history
            ORDER BY station_id, reported_at DESC
          )
          SELECT
            COUNT(stations.station_id)::INTEGER AS total_stations,
            COUNT(latest_status.station_id)::INTEGER AS stations_reporting,
            COALESCE(SUM(latest_status.bikes_available), 0)::INTEGER AS bikes_available,
            COALESCE(SUM(latest_status.docks_available), 0)::INTEGER AS docks_available,
            COUNT(*) FILTER (
              WHERE latest_status.bikes_available BETWEEN 1 AND $1
                AND latest_status.is_renting
            )::INTEGER AS low_bike_stations,
            COUNT(*) FILTER (
              WHERE latest_status.bikes_available = 0
                AND latest_status.is_renting
            )::INTEGER AS empty_stations,
            COUNT(*) FILTER (
              WHERE latest_status.station_id IS NULL
                OR NOT latest_status.is_installed
                OR NOT latest_status.is_renting
            )::INTEGER AS offline_stations,
            MAX(latest_status.reported_at) AS latest_reported_at
          FROM stations
          LEFT JOIN latest_status USING (station_id)
        `,
        [LOW_BIKE_THRESHOLD]
      );

      return res.json({
        ...result.rows[0],
        low_bike_threshold: LOW_BIKE_THRESHOLD,
      });
    } catch (error) {
      console.error('Could not load bikeshare summary:', error.message);
      return res.status(500).json({ error: 'Could not load bikeshare summary' });
    }
  });

  app.get('/api/bikeshare/alerts', async (req, res) => {
    const severity = normalizeAlertSeverity(req.query.severity);
    const limit = parseBoundedInteger(req.query.limit, 50, 1, 200);
    const offset = parseBoundedInteger(req.query.offset, 0, 0, 100000);

    try {
      const result = await databasePool.query(
        `
          SELECT
            id,
            station_id,
            station_name,
            severity,
            bikes_available,
            depletion_rate_per_minute,
            predicted_minutes_to_empty,
            reason,
            first_reported_at,
            last_reported_at,
            created_at,
            updated_at,
            COUNT(*) OVER()::INTEGER AS total_count
          FROM station_alerts
          WHERE resolved_at IS NULL
            AND ($1 = 'all' OR severity = $1)
          ORDER BY
            CASE severity WHEN 'critical' THEN 0 ELSE 1 END,
            predicted_minutes_to_empty ASC NULLS LAST,
            bikes_available ASC,
            updated_at DESC
          LIMIT $2 OFFSET $3
        `,
        [severity, limit, offset]
      );

      const total = result.rows.length ? result.rows[0].total_count : 0;
      const items = result.rows.map(({ total_count, ...alert }) => alert);
      return res.json({ items, total, limit, offset, severity });
    } catch (error) {
      console.error('Could not load station alerts:', error.message);
      return res.status(500).json({ error: 'Could not load station alerts' });
    }
  });

  app.get('/api/bikeshare/stations/map', async (req, res) => {
    try {
      const result = await databasePool.query(
        `
          WITH latest_status AS (
            SELECT DISTINCT ON (station_id)
              station_id,
              reported_at,
              bikes_available,
              docks_available,
              is_installed,
              is_renting,
              is_returning
            FROM station_status_history
            ORDER BY station_id, reported_at DESC
          )
          SELECT
            stations.station_id,
            stations.name,
            stations.latitude,
            stations.longitude,
            latest_status.reported_at,
            latest_status.bikes_available,
            latest_status.docks_available,
            latest_status.is_installed,
            latest_status.is_renting,
            latest_status.is_returning
          FROM stations
          LEFT JOIN latest_status USING (station_id)
          ORDER BY stations.name ASC
        `
      );

      return res.json({ items: result.rows, total: result.rows.length });
    } catch (error) {
      console.error('Could not load station map:', error.message);
      return res.status(500).json({ error: 'Could not load station map' });
    }
  });

  app.get('/api/bikeshare/stations', async (req, res) => {
    const search = typeof req.query.search === 'string' ? req.query.search.trim().slice(0, 100) : '';
    const risk = normalizeRiskFilter(req.query.risk);
    const limit = parseBoundedInteger(req.query.limit, 50, 1, 200);
    const offset = parseBoundedInteger(req.query.offset, 0, 0, 100000);
    const sort = normalizeStationSort(req.query.sort);

    try {
      const result = await databasePool.query(
        `
          WITH latest_status AS (
            SELECT DISTINCT ON (station_id)
              station_id,
              reported_at,
              bikes_available,
              bikes_disabled,
              docks_available,
              docks_disabled,
              is_installed,
              is_renting,
              is_returning
            FROM station_status_history
            ORDER BY station_id, reported_at DESC
          ), filtered_stations AS (
            SELECT
              stations.station_id,
              stations.name,
              stations.short_name,
              stations.latitude,
              stations.longitude,
              stations.capacity,
              latest_status.reported_at,
              latest_status.bikes_available,
              latest_status.bikes_disabled,
              latest_status.docks_available,
              latest_status.docks_disabled,
              latest_status.is_installed,
              latest_status.is_renting,
              latest_status.is_returning
            FROM stations
            LEFT JOIN latest_status USING (station_id)
            WHERE ($1 = '' OR stations.name ILIKE '%' || $1 || '%'
              OR COALESCE(stations.short_name, '') ILIKE '%' || $1 || '%')
              AND (
                $2 = 'all'
                OR ($2 = 'low' AND latest_status.bikes_available BETWEEN 1 AND $3
                  AND latest_status.is_renting)
                OR ($2 = 'empty' AND latest_status.bikes_available = 0
                  AND latest_status.is_renting)
                OR ($2 = 'offline' AND (latest_status.station_id IS NULL
                  OR NOT latest_status.is_installed OR NOT latest_status.is_renting))
              )
          )
          SELECT *, COUNT(*) OVER()::INTEGER AS total_count
          FROM filtered_stations
          ORDER BY ${stationOrderBy(sort)}
          LIMIT $4 OFFSET $5
        `,
        [search, risk, LOW_BIKE_THRESHOLD, limit, offset]
      );

      const total = result.rows.length ? result.rows[0].total_count : 0;
      const items = result.rows.map(({ total_count, ...station }) => station);
      return res.json({ items, total, limit, offset, risk, search, sort });
    } catch (error) {
      console.error('Could not load stations:', error.message);
      return res.status(500).json({ error: 'Could not load stations' });
    }
  });

  app.get('/api/bikeshare/stations/:stationId/history', async (req, res) => {
    const hours = parseBoundedInteger(req.query.hours, 24, 1, 168);
    const limit = parseBoundedInteger(req.query.limit, 200, 1, 500);

    try {
      const stationResult = await databasePool.query(
        `
          SELECT station_id, name, short_name, latitude, longitude, capacity
          FROM stations
          WHERE station_id = $1
        `,
        [req.params.stationId]
      );

      if (!stationResult.rows.length) {
        return res.status(404).json({ error: 'Station not found' });
      }

      const historyResult = await databasePool.query(
        `
          SELECT
            reported_at,
            bikes_available,
            bikes_disabled,
            docks_available,
            docks_disabled,
            is_installed,
            is_renting,
            is_returning
          FROM station_status_history
          WHERE station_id = $1
            AND reported_at >= CURRENT_TIMESTAMP - ($2::INTEGER * INTERVAL '1 hour')
          ORDER BY reported_at DESC
          LIMIT $3
        `,
        [req.params.stationId, hours, limit]
      );

      return res.json({
        station: stationResult.rows[0],
        history: historyResult.rows.reverse(),
        hours,
      });
    } catch (error) {
      console.error('Could not load station history:', error.message);
      return res.status(500).json({ error: 'Could not load station history' });
    }
  });

  return app;
}

async function startServer() {
  const pool = new Pool({ connectionString: process.env.DATABASE_URL });
  await pool.query('SELECT 1');
  const app = createApp(pool);
  app.listen(PORT, (error) => {
    if (error) {
      console.error('Could not start server:', error.message);
      process.exit(1);
    }
    console.log(`Server running on port ${PORT}`);
  });
}

if (require.main === module) {
  startServer().catch((error) => {
    console.error('Database connection failed:', error.message);
    process.exit(1);
  });
}

module.exports = {
  createApp,
  normalizeAlertSeverity,
  normalizeRiskFilter,
  normalizeStationSort,
  parseBoundedInteger,
  stationOrderBy,
};
