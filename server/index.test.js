const test = require('node:test');
const assert = require('node:assert/strict');

const {
  createApp,
  normalizeAlertSeverity,
  normalizeRiskFilter,
  normalizeStationSort,
  parseBoundedInteger,
  stationOrderBy,
} = require('./index');

test('parseBoundedInteger applies defaults and bounds', () => {
  assert.equal(parseBoundedInteger(undefined, 50, 1, 200), 50);
  assert.equal(parseBoundedInteger('25', 50, 1, 200), 25);
  assert.equal(parseBoundedInteger('-10', 50, 1, 200), 1);
  assert.equal(parseBoundedInteger('1000', 50, 1, 200), 200);
});

test('normalizeRiskFilter accepts known filters and rejects unknown values', () => {
  assert.equal(normalizeRiskFilter('low'), 'low');
  assert.equal(normalizeRiskFilter('empty'), 'empty');
  assert.equal(normalizeRiskFilter('anything-else'), 'all');
});

test('normalizeAlertSeverity accepts known severities and rejects unknown values', () => {
  assert.equal(normalizeAlertSeverity('warning'), 'warning');
  assert.equal(normalizeAlertSeverity('critical'), 'critical');
  assert.equal(normalizeAlertSeverity('anything-else'), 'all');
});

test('station sorting defaults to name and supports explicit availability sorting', () => {
  assert.equal(normalizeStationSort(undefined), 'name');
  assert.equal(normalizeStationSort('bikes-low'), 'bikes-low');
  assert.equal(normalizeStationSort('invalid'), 'name');
  assert.equal(stationOrderBy('name'), 'name ASC');
  assert.match(stationOrderBy('bikes-high'), /bikes_available DESC/);
});

test('GET /api/bikeshare/alerts returns active alerts and pagination metadata', async (t) => {
  const calls = [];
  const databasePool = {
    async query(statement, parameters) {
      calls.push({ statement, parameters });
      return {
        rows: [
          {
            id: '7',
            station_id: 'A',
            station_name: 'Example Station',
            severity: 'critical',
            bikes_available: 1,
            predicted_minutes_to_empty: 3.5,
            reason: 'Predicted to be empty soon',
            total_count: 1,
          },
        ],
      };
    },
  };
  const server = createApp(databasePool).listen(0);
  t.after(() => new Promise((resolve) => server.close(resolve)));
  await new Promise((resolve) => server.once('listening', resolve));

  const { port } = server.address();
  const response = await fetch(
    `http://127.0.0.1:${port}/api/bikeshare/alerts?severity=critical&limit=10`
  );
  const body = await response.json();

  assert.equal(response.status, 200);
  assert.equal(body.total, 1);
  assert.equal(body.items[0].station_name, 'Example Station');
  assert.equal(body.items[0].total_count, undefined);
  assert.deepEqual(calls[0].parameters, ['critical', 10, 0]);
  assert.match(calls[0].statement, /WHERE resolved_at IS NULL/);
  assert.match(calls[0].statement, /WHEN 'critical' THEN 0/);
});

test('GET /api/bikeshare/alerts reports database failures safely', async (t) => {
  const databasePool = {
    async query() {
      throw new Error('database unavailable');
    },
  };
  const server = createApp(databasePool).listen(0);
  t.after(() => new Promise((resolve) => server.close(resolve)));
  await new Promise((resolve) => server.once('listening', resolve));

  const { port } = server.address();
  const response = await fetch(`http://127.0.0.1:${port}/api/bikeshare/alerts`);

  assert.equal(response.status, 500);
  assert.deepEqual(await response.json(), { error: 'Could not load station alerts' });
});

test('GET /api/bikeshare/stations/map returns lightweight station locations', async (t) => {
  const databasePool = {
    async query(statement) {
      assert.match(statement, /stations\.latitude/);
      assert.match(statement, /latest_status\.bikes_available/);
      return {
        rows: [
          {
            station_id: 'A',
            name: 'Example Station',
            latitude: 38.9,
            longitude: -77.03,
            bikes_available: 7,
            is_installed: true,
            is_renting: true,
          },
        ],
      };
    },
  };
  const server = createApp(databasePool).listen(0);
  t.after(() => new Promise((resolve) => server.close(resolve)));
  await new Promise((resolve) => server.once('listening', resolve));

  const { port } = server.address();
  const response = await fetch(`http://127.0.0.1:${port}/api/bikeshare/stations/map`);
  const body = await response.json();

  assert.equal(response.status, 200);
  assert.equal(body.total, 1);
  assert.equal(body.items[0].station_id, 'A');
});
