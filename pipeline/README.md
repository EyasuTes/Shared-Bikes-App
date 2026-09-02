# Increment 1: read Capital Bikeshare data

The reusable ETL code is separated by responsibility:

- `extract.py` discovers and fetches the public GBFS feeds.
- `transform.py` cleans the feeds into typed station and status records.
- `load.py` stores raw and cleaned records in PostgreSQL.
- `run_etl.py` calls those three stages in order for a manual end-to-end run.
- `fetch_capital_bikeshare.py` remains a small extraction-only diagnostic command.

Airflow, Kafka, and the web application do not call these stages yet.

From the `my-app` folder, run:

```powershell
python -m pipeline.fetch_capital_bikeshare
```

The command performs three steps:

1. Reads the GBFS discovery document to find the current feed URLs.
2. Fetches `station_information` (names, locations, capacities) and
   `station_status` (current bikes and docks).
3. Joins both datasets by `station_id` and prints a validation summary.

Extracting and transforming use only Python's standard library. Loading requires
the Psycopg PostgreSQL driver:

```powershell
python -m pip install -r pipeline/requirements.txt
```

To test all three stages without using the network or a real database:

```powershell
python -m unittest discover -s pipeline/tests
```

## Run the complete ETL manually

Start PostgreSQL and make sure `database/bikeshare_schema.sql` has been applied.
Then run these commands from the `my-app` folder:

```powershell
python -m pip install -r pipeline/requirements.txt
python -m pipeline.run_etl
```

The runner reads the existing `.env` file and connects from the host through
`127.0.0.1:${POSTGRES_HOST_PORT}`. A real `DATABASE_URL` environment variable,
when present, overrides the values in `.env`.

`GBFS_DISCOVERY_URL` can override the default discovery endpoint if needed.
