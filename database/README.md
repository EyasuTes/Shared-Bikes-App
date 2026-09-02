# Bike data tables

`bikeshare_schema.sql` creates the storage needed by the Capital Bikeshare ETL:

- `gbfs_raw_data` preserves each original API response as JSON.
- `stations` contains the latest cleaned information for each station.
- `station_status_history` contains availability observations over time.
- `station_alerts` contains current and resolved bike-depletion alerts.

The relationship is:

```text
stations (one row per station)
    |
    +--- station_status_history (many observations per station)
```

## New PostgreSQL volume

Compose mounts the SQL file under `/docker-entrypoint-initdb.d`. The official
PostgreSQL image executes it automatically when it creates a new empty database.

## Existing PostgreSQL volume

PostgreSQL initialization scripts do not run again for an existing volume. The
Compose `db-schema` service handles that case by applying this repeatable schema
to the running database:

```bash
docker compose run --rm db-schema
```

The `alert-consumer` depends on `db-schema`, so Compose runs it automatically
when you start the consumer. It is expected to finish successfully and exit.

You can still apply the file directly from PowerShell if needed:

```powershell
Get-Content database/bikeshare_schema.sql -Raw |
  docker compose exec -T db psql -U my_app_user -d my_app
```

This applies only `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`
statements. It does not delete the existing database or volume.
