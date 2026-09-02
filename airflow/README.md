# Capital Bikeshare ETL with Apache Airflow

Airflow orchestrates the reusable Python pipeline as three visible tasks:

```text
extract -> transform -> load
```

## Pipeline tasks

1. `extract` fetches both Capital Bikeshare GBFS feeds.
2. `transform` cleans and validates station and availability records.
3. `load` stores raw JSON, stations, and status history in one transaction.

The first two tasks exchange files under the Compose-managed `airflow_data`
volume. Only their file paths are placed in Airflow XCom. After a successful
load, the temporary files are removed. Permanent data stays in PostgreSQL.

## Run locally with Docker Compose

From the `my-app` directory:

```bash
docker compose up -d --build db airflow
```

The first Airflow image build can take several minutes. Open:

- Airflow: http://localhost:8080

This learning setup disables Airflow authentication. Do not use that setting in
production.

## Trigger the ETL

1. Open the Airflow UI.
2. Find `capital_bikeshare_etl`.
3. Open the DAG and select the trigger button.
4. Watch `extract`, `transform`, and `load` run in order.

The DAG also runs automatically every five minutes.

You can also inspect the loaded rows directly:

```bash
docker compose exec db psql -U my_app_user -d my_app \
  -c "SELECT COUNT(*) FROM station_status_history;"
```

The `stations` count stays roughly constant, while `station_status_history`
grows as newer observations are loaded. Reprocessing an identical observation
is safe because the load uses conflict handling.

## Stop the environment

Preserve PostgreSQL and Airflow data:

```bash
docker compose down
```

Delete all Compose-managed data and start from scratch:

```bash
docker compose down -v
```

The `-v` command permanently deletes the application database and Airflow
metadata volumes.
