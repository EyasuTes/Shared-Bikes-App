# Shared Bikes Operations Platform

A Dockerized data platform that collects live Capital Bikeshare station data,
stores historical observations, detects bike-depletion risk, and presents the
results in an operator dashboard.

The project combines Python ETL, Apache Airflow, PostgreSQL, Apache Kafka, an
Express API, and a React/Leaflet frontend.

## Architecture

```text
                       BATCH PATH (every 5 minutes)

Capital Bikeshare GBFS -> Airflow ETL -> PostgreSQL -> API -> Dashboard
                              |
                              +-> raw feeds, stations, status history

                      STREAMING PATH (every 60 seconds)

Capital Bikeshare GBFS -> producer -> Kafka station-status topic
                                         |
                                         v
                                  alert consumer
                                         |
                                         v
                             PostgreSQL station_alerts
                                         |
                                         v
                                    Dashboard
```

## Services

| Service | Purpose | Host access |
| --- | --- | --- |
| `client` | React, Vite, and Leaflet dashboard | http://localhost:5173 |
| `server` | Express REST API | http://localhost:5000 |
| `db` | PostgreSQL 18 | `localhost:5433` by default |
| `db-schema` | Applies the database schema, then exits | Compose only |
| `airflow` | ETL scheduler and web interface | http://localhost:8080 |
| `kafka` | Single-node Kafka broker in KRaft mode | `localhost:9092` |
| `kafka-init` | Creates the Kafka topic, then exits | Compose only |
| `station-producer` | Publishes new station observations | Compose only |
| `alert-consumer` | Detects and stores station risks | Compose only |

`db-schema` and `kafka-init` are one-time jobs. An `Exited (0)` state means
they completed successfully.

## Prerequisites

Install:

- Git
- Docker Desktop with Docker Compose

Node.js, Python, PostgreSQL, Kafka, and Airflow do not need to be installed on
the host when the full system is run with Docker Compose.

## Quick start

### 1. Clone the repository

```bash
git clone git@github.com:EyasuTes/Shared-Bikes-App.git
cd Shared-Bikes-App
```

If SSH is not configured:

```bash
git clone https://github.com/EyasuTes/Shared-Bikes-App.git
cd Shared-Bikes-App
```

### 2. Create the environment file

PowerShell:

```powershell
Copy-Item .env.example .env
```

Bash or Git Bash:

```bash
cp .env.example .env
```

Update the password in `.env`:

```dotenv
POSTGRES_DB=my_app
POSTGRES_USER=my_app_user
POSTGRES_PASSWORD=choose_a_local_development_password
POSTGRES_HOST_PORT=5433
KAFKA_HOST_PORT=9092
GBFS_POLL_SECONDS=60
```

`.env` is ignored by Git and must not be committed.

### 3. Build and start everything

Make sure Docker Desktop is running:

```bash
docker compose up -d --build
docker compose ps -a
```

The first build can take several minutes while Docker downloads and builds all
required images.

### 4. Open the system

- Dashboard: http://localhost:5173
- API check: http://localhost:5000/api
- Airflow: http://localhost:8080

Airflow authentication is disabled for this local demonstration. Do not expose
this configuration directly to the internet.

## Startup and data flow

1. PostgreSQL starts and creates the configured database.
2. `db-schema` creates or verifies the application tables and indexes.
3. Kafka starts in KRaft mode without ZooKeeper.
4. `kafka-init` creates the three-partition `station-status` topic.
5. The producer fetches Capital Bikeshare GBFS data every 60 seconds.
6. New observations are published with `station_id` as the Kafka message key.
7. The consumer evaluates each event and stores alert state changes.
8. The Express API provides inventory, history, and alerts to the dashboard.
9. Airflow runs the full ETL automatically every five minutes.

## ETL pipeline

| File | Responsibility |
| --- | --- |
| `pipeline/extract.py` | Discovers and downloads the current GBFS feeds |
| `pipeline/transform.py` | Cleans timestamps, flags, coordinates, and counts |
| `pipeline/load.py` | Writes raw and cleaned records to PostgreSQL |
| `pipeline/run_etl.py` | Runs extract, transform, and load in order |
| `pipeline/artifacts.py` | Manages temporary Airflow task artifacts |

The pipeline retrieves:

- `station_information`: station names, coordinates, capacities, and metadata;
- `station_status`: bikes, docks, service flags, and `reported_at`.

The two feeds are joined by `station_id`.

## Airflow

The `capital_bikeshare_etl` DAG contains:

```text
extract -> transform -> load
```

It runs every five minutes. To trigger it immediately:

1. Open http://localhost:8080.
2. Select `capital_bikeshare_etl`.
3. Select the trigger button.
4. Inspect the extract, transform, and load task logs.

The first two tasks exchange temporary file paths through XCom. Permanent data
is stored in PostgreSQL.

## PostgreSQL

| Table | Purpose |
| --- | --- |
| `gbfs_raw_data` | Original API responses for audit and replay |
| `stations` | Latest cleaned metadata for every station |
| `station_status_history` | Availability observations over time |
| `station_alerts` | Active and resolved warning or critical alerts |

Inspect the data:

```bash
docker compose exec db psql -U my_app_user -d my_app -c "SELECT COUNT(*) FROM stations;"
docker compose exec db psql -U my_app_user -d my_app -c "SELECT COUNT(*) FROM station_status_history;"
docker compose exec db psql -U my_app_user -d my_app -c "SELECT COUNT(*) FROM station_alerts;"
```

The database uses the `postgres_data` volume, so `docker compose down` does
not delete its data.

### Connect with pgAdmin

| Setting | Value |
| --- | --- |
| Host | `localhost` |
| Port | `POSTGRES_HOST_PORT`, default `5433` |
| Maintenance database | `POSTGRES_DB` |
| Username | `POSTGRES_USER` |
| Password | `POSTGRES_PASSWORD` |

pgAdmin uses `localhost` because it connects from the host. Containers connect
to `db:5432` through the Compose network.

## Kafka and alerts

The producer sends observations to the `station-status` topic. It skips a
station observation already published by that producer process with the same
`reported_at` timestamp.

The alert consumer uses the `station-depletion-alerts-v1` consumer group and
commits a message only after its database operation succeeds.

| Severity | Default condition |
| --- | --- |
| Critical | Two or fewer bikes, or predicted empty within five minutes |
| Warning | Five or fewer bikes, or predicted empty within fifteen minutes |
| Healthy/resolved | Neither warning nor critical conditions are present |

Prediction requires at least three suitable observations. Count-based alerts
can be generated immediately.

Inspect the topic:

```bash
docker compose exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:19092 --describe --topic station-status
```

Git Bash may rewrite the Linux path. If that happens:

```bash
MSYS_NO_PATHCONV=1 docker compose exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:19092 --describe --topic station-status
```

## API

| Endpoint | Description |
| --- | --- |
| `GET /api` | Basic API response |
| `GET /api/bikeshare/summary` | Network inventory summary |
| `GET /api/bikeshare/alerts` | Paginated active alerts |
| `GET /api/bikeshare/stations/map` | Station locations and availability |
| `GET /api/bikeshare/stations` | Searchable and sortable station inventory |
| `GET /api/bikeshare/stations/:stationId/history` | Station history |

The frontend uses its Vite proxy to reach the server inside the Compose network.

## Dashboard

The operator dashboard includes:

- network inventory totals;
- active alerts ordered by severity;
- alert filtering and pagination;
- a station map: red for zero bikes, yellow for one to five, and green for more
  than five;
- searchable and sortable station inventory; and
- a 24-hour station history view.

## Common Docker commands

```bash
# Status
docker compose ps -a

# All logs or one service's logs
docker compose logs -f
docker compose logs -f station-producer
docker compose logs -f alert-consumer
docker compose logs -f airflow

# Rebuild and start
docker compose up -d --build

# Rebuild selected application services
docker compose up -d --build client server station-producer alert-consumer

# Stop while preserving volumes
docker compose down

# Restart one service
docker compose restart server
```

## Run the ETL manually

Airflow normally handles this, but it can also run from the host:

```bash
docker compose up -d db db-schema
python -m pip install -r pipeline/requirements.txt
python -m pipeline.run_etl
```

The runner reads `.env` and connects through the configured PostgreSQL host
port. A `DATABASE_URL` environment variable overrides the file values.

## Tests

```bash
# Backend
cd server
npm install
npm test
cd ..

# Frontend
cd client
npm install
npm run lint
npm run build
cd ..

# Python pipeline and streaming
python -m unittest discover -s pipeline/tests -v
python -m unittest discover -s streaming/tests -v
```

The Python tests use test doubles and do not require a live API, database, or
Kafka broker.

## Project structure

```text
.
|-- airflow/       Airflow image, DAG, and requirements
|-- client/        React and Leaflet dashboard
|-- database/      PostgreSQL initialization and schema
|-- pipeline/      Reusable Python ETL code and tests
|-- server/        Express API and tests
|-- streaming/     Kafka producer, consumer, alert rules, and tests
|-- compose.yaml   Complete local platform
|-- .env.example   Environment template
└-- README.md      This setup and operating guide
```

## Troubleshooting

### Docker cannot connect

Start Docker Desktop and wait until its engine is running.

### A port is already in use

Stop the program using the port or change the appropriate host port in `.env`.
Common ports are `5173`, `5000`, `5433`, `8080`, and `9092`.

### `db-schema` or `kafka-init` is stopped

These are one-time jobs and should exit with code 0. To apply the schema again:

```bash
docker compose run --rm db-schema
```

### No alerts appear

```bash
docker compose ps -a
docker compose logs station-producer
docker compose logs alert-consumer
```

Alerts appear only while a station meets a warning or critical condition.
Resolved alerts remain in PostgreSQL but are not returned as active.

### Reset all local data

The following permanently deletes this project's PostgreSQL, Airflow, and Kafka
volumes:

```bash
docker compose down -v
docker compose up -d --build
```

Use `down -v` only when the existing local data can be discarded.

## Local-development limitations

This configuration is intended for learning and demonstration:

- Kafka uses one plaintext broker.
- Airflow's local authentication is open.
- Services do not use TLS.
- PostgreSQL credentials are development values.
- Alert trend state is rebuilt after the consumer restarts.

A production deployment would require secret management, authentication,
encrypted connections, monitoring, backups, and resilient Kafka and database
topologies.
