import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './App.css';

const PAGE_SIZE = 50;
const ALERT_PAGE_SIZE = 12;

function formatNumber(value) {
  return new Intl.NumberFormat().format(Number(value || 0));
}

function formatTime(value) {
  if (!value) return 'No report';
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
}

function formatMinutes(value) {
  const minutes = Number(value);
  if (!Number.isFinite(minutes)) return 'Triggered by current bike count';
  if (minutes < 1) return 'Less than 1 minute to predicted depletion';
  return `${minutes.toFixed(minutes < 10 ? 1 : 0)} minutes to predicted depletion`;
}

function stationState(station) {
  if (!station.reported_at || !station.is_installed || !station.is_renting) {
    return { label: 'Offline', tone: 'offline' };
  }
  if (station.bikes_available === 0) return { label: 'Empty', tone: 'critical' };
  if (station.bikes_available <= 5) return { label: 'Low bikes', tone: 'warning' };
  return { label: 'Available', tone: 'healthy' };
}

function SummaryCard({ label, value, detail, tone = '' }) {
  return (
    <article className={`summary-card ${tone}`}>
      <p>{label}</p>
      <strong>{value === undefined ? '—' : formatNumber(value)}</strong>
      <span>{detail}</span>
    </article>
  );
}

function AvailabilityBar({ bikes, docks, capacity }) {
  const knownCapacity = Number(capacity) || Number(bikes || 0) + Number(docks || 0);
  const bikePercent = knownCapacity
    ? Math.min(100, (Number(bikes || 0) / knownCapacity) * 100)
    : 0;
  const dockPercent = knownCapacity
    ? Math.min(100 - bikePercent, (Number(docks || 0) / knownCapacity) * 100)
    : 0;

  return (
    <div
      className="availability-bar"
      aria-label={`${bikes ?? 0} bikes and ${docks ?? 0} open docks`}
    >
      <span className="bike-fill" style={{ width: `${bikePercent}%` }} />
      <span className="dock-fill" style={{ width: `${dockPercent}%` }} />
    </div>
  );
}

function AlertPanel({
  alerts,
  total,
  loading,
  error,
  lastUpdated,
  page,
  severity,
  onPageChange,
  onSeverityChange,
  onSelectStation,
}) {
  const firstVisible = total ? page * ALERT_PAGE_SIZE + 1 : 0;
  const lastVisible = Math.min((page + 1) * ALERT_PAGE_SIZE, total);
  const pageCount = Math.max(1, Math.ceil(total / ALERT_PAGE_SIZE));

  return (
    <section className="alert-panel" aria-labelledby="alert-panel-title">
      <div className="alert-panel-heading">
        <div>
          <p className="eyebrow">Predictive operations</p>
          <div className="alert-title-row">
            <h2 id="alert-panel-title">Active depletion alerts</h2>
            {!loading && !error && <span className="alert-count">{total}</span>}
          </div>
          <p>
            Kafka observations are evaluated continuously. This panel refreshes every 30 seconds.
          </p>
        </div>
        <div className="alert-heading-actions">
          <label className="filter-field">
            <span>Severity</span>
            <select value={severity} onChange={(event) => onSeverityChange(event.target.value)}>
              <option value="all">All alerts</option>
              <option value="critical">Critical only</option>
              <option value="warning">Warnings only</option>
            </select>
          </label>
          <div className="alert-update-status">
            <span className="live-dot" aria-hidden="true" />
            <span>{lastUpdated ? `Checked ${formatTime(lastUpdated)}` : 'Waiting for first check'}</span>
          </div>
        </div>
      </div>

      {loading && <p className="notice" aria-live="polite">Loading active alerts…</p>}
      {error && <p className="notice error" role="alert">{error}</p>}

      {!loading && !error && alerts.length === 0 && (
        <div className="alerts-empty" role="status">
          <span aria-hidden="true">✓</span>
          <div>
            <strong>No active depletion alerts</strong>
            <p>All monitored stations are currently above the configured risk thresholds.</p>
          </div>
        </div>
      )}

      {!loading && !error && alerts.length > 0 && (
        <>
          <ul className="alert-list">
            {alerts.map((alert) => (
              <li key={alert.id} className={`alert-card ${alert.severity}`}>
                <div className="alert-card-topline">
                  <span className={`status-badge ${alert.severity}`}>{alert.severity}</span>
                  <span>{formatTime(alert.last_reported_at)}</span>
                </div>
                <button
                  type="button"
                  className="alert-station-link"
                  onClick={() => onSelectStation(alert.station_id)}
                >
                  {alert.station_name}
                </button>
                <div className="alert-measurements">
                  <strong>{formatNumber(alert.bikes_available)}</strong>
                  <span>bike{Number(alert.bikes_available) === 1 ? '' : 's'} remaining</span>
                </div>
                <p>{alert.reason}</p>
                <small>{formatMinutes(alert.predicted_minutes_to_empty)}</small>
              </li>
            ))}
          </ul>
          <footer className="pagination alert-pagination">
            <p>Showing {firstVisible}–{lastVisible} of {formatNumber(total)} active alerts</p>
            <div>
              <button type="button" disabled={page === 0} onClick={() => onPageChange(page - 1)}>
                Previous
              </button>
              <span>Page {page + 1} of {pageCount}</span>
              <button
                type="button"
                disabled={page + 1 >= pageCount}
                onClick={() => onPageChange(page + 1)}
              >
                Next
              </button>
            </div>
          </footer>
        </>
      )}
    </section>
  );
}

function markerTone(station) {
  if (!station.reported_at || !station.is_installed || !station.is_renting) {
    return { color: '#697780', label: 'Offline' };
  }
  if (Number(station.bikes_available) === 0) {
    return { color: '#d9232e', label: 'Empty' };
  }
  if (Number(station.bikes_available) <= 5) {
    return { color: '#d0922a', label: 'Low bikes' };
  }
  return { color: '#26734d', label: 'Available' };
}

function StationMap({ stations, loading, error, onSelectStation }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const markerLayerRef = useRef(null);
  const hasFitBoundsRef = useRef(false);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return undefined;

    const map = L.map(containerRef.current, {
      preferCanvas: true,
      zoomControl: true,
    }).setView([38.9072, -77.0369], 12);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 19,
    }).addTo(map);
    markerLayerRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      markerLayerRef.current = null;
      hasFitBoundsRef.current = false;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const markerLayer = markerLayerRef.current;
    if (!map || !markerLayer) return;

    markerLayer.clearLayers();
    const coordinates = [];

    stations.forEach((station) => {
      const latitude = Number(station.latitude);
      const longitude = Number(station.longitude);
      if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return;

      const tone = markerTone(station);
      const marker = L.circleMarker([latitude, longitude], {
        radius: 6,
        color: '#ffffff',
        weight: 1.5,
        fillColor: tone.color,
        fillOpacity: 0.9,
      });
      const tooltip = document.createElement('div');
      const title = document.createElement('strong');
      const detail = document.createElement('span');
      title.textContent = station.name;
      detail.textContent = `${station.bikes_available ?? 'No'} bikes · ${tone.label}`;
      tooltip.append(title, detail);
      marker.bindTooltip(tooltip, { direction: 'top', offset: [0, -5] });
      marker.on('click', () => onSelectStation(station.station_id));
      marker.addTo(markerLayer);
      coordinates.push([latitude, longitude]);
    });

    if (!hasFitBoundsRef.current && coordinates.length) {
      map.fitBounds(coordinates, { padding: [24, 24], maxZoom: 13 });
      hasFitBoundsRef.current = true;
    }
  }, [onSelectStation, stations]);

  return (
    <section className="map-panel" aria-labelledby="station-map-title">
      <div className="panel-heading map-heading">
        <div>
          <p className="eyebrow">Geographic overview</p>
          <h2 id="station-map-title">Station availability map</h2>
          <p>{formatNumber(stations.length)} stations plotted from their latest stored status.</p>
        </div>
        <div className="map-legend" aria-label="Map marker legend">
          <span><i className="map-dot empty" /> 0 bikes</span>
          <span><i className="map-dot low" /> 1–5 bikes</span>
          <span><i className="map-dot available" /> More than 5</span>
          <span><i className="map-dot offline" /> Offline</span>
        </div>
      </div>
      <div className="map-body">
        <div ref={containerRef} className="station-map" aria-label="Map of Capital Bikeshare stations" />
        {loading && <p className="map-overlay">Loading station map…</p>}
        {error && <p className="map-overlay error" role="alert">{error}</p>}
      </div>
    </section>
  );
}

function HistoryChart({ history, capacity }) {
  if (history.length < 2) {
    return (
      <p className="empty-chart">
        Run the ETL again later to create enough observations for a trend line.
      </p>
    );
  }

  const width = 720;
  const height = 220;
  const padding = 24;
  const maximum = Math.max(Number(capacity) || 0, ...history.map((item) => (
    Math.max(Number(item.bikes_available), Number(item.docks_available))
  )), 1);
  const pointsFor = (field) => history.map((item, index) => {
    const x = padding + (index / (history.length - 1)) * (width - padding * 2);
    const y = height - padding - (Number(item[field]) / maximum) * (height - padding * 2);
    return `${x},${y}`;
  }).join(' ');

  return (
    <div className="chart-wrap">
      <svg
        className="history-chart"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-labelledby="history-chart-title history-chart-description"
      >
        <title id="history-chart-title">Station availability history</title>
        <desc id="history-chart-description">
          Red represents available bikes and blue represents open docks.
        </desc>
        {[0.25, 0.5, 0.75].map((position) => (
          <line
            key={position}
            className="chart-grid"
            x1={padding}
            x2={width - padding}
            y1={padding + position * (height - padding * 2)}
            y2={padding + position * (height - padding * 2)}
          />
        ))}
        <polyline className="chart-line docks" points={pointsFor('docks_available')} />
        <polyline className="chart-line bikes" points={pointsFor('bikes_available')} />
      </svg>
      <div className="chart-legend">
        <span><i className="legend-dot bikes" /> Bikes available</span>
        <span><i className="legend-dot docks" /> Open docks</span>
      </div>
    </div>
  );
}

function App() {
  const [summary, setSummary] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [totalAlerts, setTotalAlerts] = useState(0);
  const [alertsLoading, setAlertsLoading] = useState(true);
  const [alertsError, setAlertsError] = useState('');
  const [alertsLastUpdated, setAlertsLastUpdated] = useState(null);
  const [alertPage, setAlertPage] = useState(0);
  const [alertSeverity, setAlertSeverity] = useState('all');
  const [mapStations, setMapStations] = useState([]);
  const [mapLoading, setMapLoading] = useState(true);
  const [mapError, setMapError] = useState('');
  const [stations, setStations] = useState([]);
  const [totalStations, setTotalStations] = useState(0);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [risk, setRisk] = useState('all');
  const [stationSort, setStationSort] = useState('name');
  const [page, setPage] = useState(0);
  const [selectedStationId, setSelectedStationId] = useState(null);
  const [selectedHistory, setSelectedHistory] = useState(null);
  const [loading, setLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [error, setError] = useState('');
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(0);
    }, 300);
    return () => window.clearTimeout(timeout);
  }, [searchInput]);

  useEffect(() => {
    const controller = new AbortController();

    async function loadDashboard() {
      setLoading(true);
      setError('');
      const parameters = new URLSearchParams({
        search,
        risk,
        sort: stationSort,
        limit: String(PAGE_SIZE),
        offset: String(page * PAGE_SIZE),
      });

      try {
        const [summaryResponse, stationsResponse] = await Promise.all([
          fetch('/api/bikeshare/summary', { signal: controller.signal }),
          fetch(`/api/bikeshare/stations?${parameters}`, { signal: controller.signal }),
        ]);
        if (!summaryResponse.ok || !stationsResponse.ok) throw new Error('Request failed');
        const [summaryData, stationData] = await Promise.all([
          summaryResponse.json(),
          stationsResponse.json(),
        ]);
        setSummary(summaryData);
        setStations(stationData.items);
        setTotalStations(stationData.total);
      } catch (requestError) {
        if (requestError.name !== 'AbortError') {
          setError('Could not load bike data. Check that the backend and PostgreSQL are running.');
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }

    loadDashboard();
    return () => controller.abort();
  }, [page, refreshToken, risk, search, stationSort]);

  useEffect(() => {
    let active = true;
    let currentController = null;

    async function loadAlerts() {
      currentController?.abort();
      currentController = new AbortController();

      try {
        const parameters = new URLSearchParams({
          severity: alertSeverity,
          limit: String(ALERT_PAGE_SIZE),
          offset: String(alertPage * ALERT_PAGE_SIZE),
        });
        const response = await fetch(`/api/bikeshare/alerts?${parameters}`, {
          signal: currentController.signal,
        });
        if (!response.ok) throw new Error('Request failed');
        const data = await response.json();
        if (!active) return;
        setAlerts(data.items);
        setTotalAlerts(data.total);
        setAlertsError('');
        setAlertsLastUpdated(new Date().toISOString());
      } catch (requestError) {
        if (active && requestError.name !== 'AbortError') {
          setAlertsError('Could not load active alerts. Check that the alert table and backend are available.');
        }
      } finally {
        if (active) setAlertsLoading(false);
      }
    }

    loadAlerts();
    const interval = window.setInterval(loadAlerts, 30_000);

    return () => {
      active = false;
      window.clearInterval(interval);
      currentController?.abort();
    };
  }, [alertPage, alertSeverity, refreshToken]);

  useEffect(() => {
    let active = true;
    let currentController = null;

    async function loadMapStations() {
      currentController?.abort();
      currentController = new AbortController();
      try {
        const response = await fetch('/api/bikeshare/stations/map', {
          signal: currentController.signal,
        });
        if (!response.ok) throw new Error('Request failed');
        const data = await response.json();
        if (!active) return;
        setMapStations(data.items);
        setMapError('');
      } catch (requestError) {
        if (active && requestError.name !== 'AbortError') {
          setMapError('Could not load station locations.');
        }
      } finally {
        if (active) setMapLoading(false);
      }
    }

    loadMapStations();
    const interval = window.setInterval(loadMapStations, 60_000);
    return () => {
      active = false;
      window.clearInterval(interval);
      currentController?.abort();
    };
  }, [refreshToken]);

  useEffect(() => {
    if (!selectedStationId) return undefined;
    const controller = new AbortController();

    async function loadHistory() {
      setHistoryLoading(true);
      try {
        const response = await fetch(
          `/api/bikeshare/stations/${encodeURIComponent(selectedStationId)}/history?hours=24`,
          { signal: controller.signal }
        );
        if (!response.ok) throw new Error('Request failed');
        setSelectedHistory(await response.json());
      } catch (requestError) {
        if (requestError.name !== 'AbortError') setSelectedHistory(null);
      } finally {
        if (!controller.signal.aborted) setHistoryLoading(false);
      }
    }

    loadHistory();
    return () => controller.abort();
  }, [refreshToken, selectedStationId]);

  const firstVisible = totalStations ? page * PAGE_SIZE + 1 : 0;
  const lastVisible = Math.min((page + 1) * PAGE_SIZE, totalStations);
  const pageCount = Math.max(1, Math.ceil(totalStations / PAGE_SIZE));

  return (
    <main className="dashboard-shell">
      <header className="dashboard-header">
        <div>
          <p className="eyebrow">Capital Bikeshare operations</p>
          <h1>Station availability</h1>
          <p className="header-copy">
            Latest station conditions loaded by the Airflow GBFS pipeline.
          </p>
        </div>
        <div className="header-actions">
          <p>
            Latest report
            <strong>{formatTime(summary?.latest_reported_at)}</strong>
          </p>
          <button type="button" onClick={() => setRefreshToken((value) => value + 1)}>
            Refresh data
          </button>
        </div>
      </header>

      <section className="summary-grid" aria-label="Network summary">
        <SummaryCard
          label="Stations"
          value={summary?.total_stations}
          detail={`${formatNumber(summary?.stations_reporting)} currently reporting`}
        />
        <SummaryCard
          label="Available bikes"
          value={summary?.bikes_available}
          detail="Across all latest reports"
        />
        <SummaryCard
          label="Open docks"
          value={summary?.docks_available}
          detail="Ready for bike returns"
        />
        <SummaryCard
          label="Low-bike stations"
          value={summary?.low_bike_stations}
          detail={`Between 1 and ${summary?.low_bike_threshold || 5} bikes`}
          tone="warning"
        />
        <SummaryCard
          label="Empty stations"
          value={summary?.empty_stations}
          detail="No rentable bikes"
          tone="critical"
        />
      </section>

      <AlertPanel
        alerts={alerts}
        total={totalAlerts}
        loading={alertsLoading}
        error={alertsError}
        lastUpdated={alertsLastUpdated}
        page={alertPage}
        severity={alertSeverity}
        onPageChange={setAlertPage}
        onSeverityChange={(value) => {
          setAlertSeverity(value);
          setAlertPage(0);
        }}
        onSelectStation={setSelectedStationId}
      />

      <StationMap
        stations={mapStations}
        loading={mapLoading}
        error={mapError}
        onSelectStation={setSelectedStationId}
      />

      <section className="station-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Live inventory</p>
            <h2>Stations</h2>
          </div>
          <div className="station-controls">
            <label className="search-field">
              <span>Search stations</span>
              <input
                type="search"
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                placeholder="Name or station number"
              />
            </label>
            <label className="filter-field">
              <span>Condition</span>
              <select
                value={risk}
                onChange={(event) => {
                  setRisk(event.target.value);
                  setPage(0);
                }}
              >
                <option value="all">All stations</option>
                <option value="low">Low bikes</option>
                <option value="empty">Empty</option>
                <option value="offline">Offline</option>
              </select>
            </label>
            <label className="filter-field">
              <span>Sort by</span>
              <select
                value={stationSort}
                onChange={(event) => {
                  setStationSort(event.target.value);
                  setPage(0);
                }}
              >
                <option value="name">Station name</option>
                <option value="bikes-low">Fewest bikes</option>
                <option value="bikes-high">Most bikes</option>
              </select>
            </label>
          </div>
        </div>

        {error && <p className="notice error" role="alert">{error}</p>}
        {loading && <p className="notice" aria-live="polite">Loading station data…</p>}

        {!loading && !error && (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Station</th>
                    <th>Availability</th>
                    <th>Bikes</th>
                    <th>Docks</th>
                    <th>Condition</th>
                    <th>Reported</th>
                  </tr>
                </thead>
                <tbody>
                  {stations.map((station) => {
                    const state = stationState(station);
                    return (
                      <tr key={station.station_id}>
                        <td>
                          <button
                            type="button"
                            className="station-link"
                            onClick={() => setSelectedStationId(station.station_id)}
                          >
                            {station.name}
                          </button>
                          <small>{station.short_name || 'No station number'} · {station.capacity} docks</small>
                        </td>
                        <td className="bar-cell">
                          <AvailabilityBar
                            bikes={station.bikes_available}
                            docks={station.docks_available}
                            capacity={station.capacity}
                          />
                        </td>
                        <td className="number-cell">{station.bikes_available ?? '—'}</td>
                        <td className="number-cell">{station.docks_available ?? '—'}</td>
                        <td><span className={`status-badge ${state.tone}`}>{state.label}</span></td>
                        <td className="reported-cell">{formatTime(station.reported_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {!stations.length && <p className="notice">No stations match this filter.</p>}

            <footer className="pagination">
              <p>Showing {firstVisible}–{lastVisible} of {formatNumber(totalStations)}</p>
              <div>
                <button type="button" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>
                  Previous
                </button>
                <span>Page {page + 1} of {pageCount}</span>
                <button
                  type="button"
                  disabled={page + 1 >= pageCount}
                  onClick={() => setPage((value) => value + 1)}
                >
                  Next
                </button>
              </div>
            </footer>
          </>
        )}
      </section>

      {selectedStationId && (
        <section className="history-panel" aria-live="polite">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">24-hour detail</p>
              <h2>{selectedHistory?.station.name || 'Loading station…'}</h2>
              {selectedHistory && (
                <p>{selectedHistory.station.capacity} total docks · {selectedHistory.history.length} observations</p>
              )}
            </div>
            <button
              type="button"
              className="close-button"
              onClick={() => {
                setSelectedStationId(null);
                setSelectedHistory(null);
              }}
            >
              Close
            </button>
          </div>
          {historyLoading && <p className="notice">Loading station history…</p>}
          {!historyLoading && selectedHistory && (
            <HistoryChart
              history={selectedHistory.history}
              capacity={selectedHistory.station.capacity}
            />
          )}
        </section>
      )}
    </main>
  );
}

export default App;
