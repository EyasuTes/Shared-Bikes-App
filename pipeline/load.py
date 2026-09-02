"""Load raw and transformed Capital Bikeshare data into PostgreSQL."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pipeline.extract import GbfsFeeds
from pipeline.transform import TransformedFeeds, parse_gbfs_timestamp


class LoadError(RuntimeError):
    """Raised when PostgreSQL support is unavailable or loading fails."""


@dataclass(frozen=True)
class LoadSummary:
    raw_feeds_processed: int
    stations_processed: int
    statuses_processed: int


RAW_FEED_SQL = """
    INSERT INTO gbfs_raw_data (
      feed_name, gbfs_version, source_last_updated, payload
    )
    VALUES (%s, %s, %s, %s::jsonb)
    ON CONFLICT (feed_name, source_last_updated) DO NOTHING
"""

STATION_SQL = """
    INSERT INTO stations (
      station_id, name, short_name, latitude, longitude, capacity,
      source_last_updated
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (station_id) DO UPDATE SET
      name = EXCLUDED.name,
      short_name = EXCLUDED.short_name,
      latitude = EXCLUDED.latitude,
      longitude = EXCLUDED.longitude,
      capacity = EXCLUDED.capacity,
      source_last_updated = EXCLUDED.source_last_updated,
      loaded_at = CURRENT_TIMESTAMP
    WHERE EXCLUDED.source_last_updated >= stations.source_last_updated
"""

STATUS_SQL = """
    INSERT INTO station_status_history (
      station_id, reported_at, bikes_available, bikes_disabled,
      docks_available, docks_disabled, is_installed, is_renting, is_returning
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (station_id, reported_at) DO NOTHING
"""


def load_feeds(
    connection: Any, feeds: GbfsFeeds, transformed: TransformedFeeds
) -> LoadSummary:
    """Load one ETL result using the transaction owned by the caller."""

    version = str(feeds.discovery.get("version", "unknown"))
    raw_documents = (
        ("station_information", feeds.station_information),
        ("station_status", feeds.station_status),
    )

    with connection.cursor() as cursor:
        for feed_name, document in raw_documents:
            source_last_updated = parse_gbfs_timestamp(
                document.get("last_updated"), f"{feed_name}.last_updated"
            )
            cursor.execute(
                RAW_FEED_SQL,
                (
                    feed_name,
                    str(document.get("version", version)),
                    source_last_updated,
                    json.dumps(document, separators=(",", ":")),
                ),
            )

        cursor.executemany(
            STATION_SQL,
            [
                (
                    station.station_id,
                    station.name,
                    station.short_name,
                    station.latitude,
                    station.longitude,
                    station.capacity,
                    station.source_last_updated,
                )
                for station in transformed.stations
            ],
        )
        cursor.executemany(
            STATUS_SQL,
            [
                (
                    status.station_id,
                    status.reported_at,
                    status.bikes_available,
                    status.bikes_disabled,
                    status.docks_available,
                    status.docks_disabled,
                    status.is_installed,
                    status.is_renting,
                    status.is_returning,
                )
                for status in transformed.statuses
            ],
        )

    return LoadSummary(
        raw_feeds_processed=len(raw_documents),
        stations_processed=len(transformed.stations),
        statuses_processed=len(transformed.statuses),
    )


def load_to_postgres(
    database_url: str, feeds: GbfsFeeds, transformed: TransformedFeeds
) -> LoadSummary:
    """Connect to PostgreSQL and commit all loads together, or roll them all back."""

    if not database_url.strip():
        raise LoadError("DATABASE_URL is required")

    try:
        import psycopg
    except ModuleNotFoundError as error:
        raise LoadError(
            'PostgreSQL driver is missing; install it with pip install "psycopg[binary]"'
        ) from error

    try:
        # The connection context commits on success and rolls back on failure.
        with psycopg.connect(database_url) as connection:
            return load_feeds(connection, feeds, transformed)
    except Exception as error:
        raise LoadError(f"PostgreSQL load failed: {error}") from error
