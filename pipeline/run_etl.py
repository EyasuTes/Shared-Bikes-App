"""Run the Capital Bikeshare extract, transform, and load stages manually."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from time import monotonic
from urllib.parse import quote

from pipeline.extract import GbfsError, fetch_station_feeds
from pipeline.load import LoadError, load_to_postgres
from pipeline.transform import TransformError, transform_station_feeds


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def read_env_file(path: Path) -> dict[str, str]:
    """Read the simple KEY=VALUE entries used by this project's Compose .env."""

    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key:
            values[key] = value

    return values


def setting(name: str, file_values: dict[str, str]) -> str | None:
    """Let real environment variables override values read from .env."""

    return os.getenv(name) or file_values.get(name)


def build_database_url(env_path: Path = PROJECT_ROOT / ".env") -> str:
    """Build the host-side PostgreSQL URL used by the manual ETL command."""

    file_values = read_env_file(env_path)
    explicit_url = setting("DATABASE_URL", file_values)
    if explicit_url:
        return explicit_url

    user = setting("POSTGRES_USER", file_values)
    password = setting("POSTGRES_PASSWORD", file_values)
    database = setting("POSTGRES_DB", file_values)
    host = setting("POSTGRES_HOST", file_values) or "127.0.0.1"
    port = setting("POSTGRES_HOST_PORT", file_values) or "5433"

    missing = [
        name
        for name, value in (
            ("POSTGRES_USER", user),
            ("POSTGRES_PASSWORD", password),
            ("POSTGRES_DB", database),
        )
        if not value
    ]
    if missing:
        raise LoadError(
            f"Missing database settings in environment or .env: {', '.join(missing)}"
        )

    return (
        f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}@"
        f"{host}:{port}/{quote(database, safe='')}"
    )


def main() -> int:
    started_at = monotonic()

    try:
        print("[extract] Fetching Capital Bikeshare GBFS feeds...")
        feeds = fetch_station_feeds()

        print("[transform] Cleaning station and availability records...")
        transformed = transform_station_feeds(feeds)
        print(f"[transform] Stations ready: {len(transformed.stations)}")
        print(f"[transform] Statuses ready: {len(transformed.statuses)}")
        if transformed.skipped_status_ids:
            print(
                "[transform] Statuses skipped because station information was missing: "
                f"{len(transformed.skipped_status_ids)}"
            )

        print("[load] Writing one transaction to PostgreSQL...")
        summary = load_to_postgres(build_database_url(), feeds, transformed)
    except (GbfsError, TransformError, LoadError) as error:
        print(f"ETL failed: {error}", file=sys.stderr)
        return 1

    elapsed_seconds = monotonic() - started_at
    print(f"[load] Raw feeds processed: {summary.raw_feeds_processed}")
    print(f"[load] Stations processed: {summary.stations_processed}")
    print(f"[load] Statuses processed: {summary.statuses_processed}")
    print(f"ETL completed successfully in {elapsed_seconds:.1f} seconds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
