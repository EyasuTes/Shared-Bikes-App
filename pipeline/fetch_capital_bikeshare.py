"""Fetch Capital Bikeshare station feeds and print a small validation report."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any

from pipeline.extract import (
    DEFAULT_DISCOVERY_URL,
    GbfsError,
    fetch_station_feeds,
    index_stations,
    station_display_name,
    stations_from,
    validate_station_relationship,
)


def formatted_update_time(value: Any) -> str:
    """Format GBFS 2.x Unix timestamps while tolerating newer string timestamps."""

    if isinstance(value, int):
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    return str(value or "unknown")


def main() -> int:
    discovery_url = os.getenv("GBFS_DISCOVERY_URL", DEFAULT_DISCOVERY_URL)

    try:
        feeds = fetch_station_feeds(discovery_url)
        summary = validate_station_relationship(feeds)
        information = index_stations(
            stations_from(feeds.station_information, "station_information"),
            "station_information",
        )
        statuses = index_stations(
            stations_from(feeds.station_status, "station_status"),
            "station_status",
        )
    except GbfsError as error:
        print(f"GBFS fetch failed: {error}", file=sys.stderr)
        return 1

    print("Capital Bikeshare GBFS fetch succeeded")
    print(f"GBFS version: {feeds.discovery.get('version', 'unknown')}")
    print(
        "Status last updated: "
        f"{formatted_update_time(feeds.station_status.get('last_updated'))}"
    )
    print(f"Station information records: {summary.information_count}")
    print(f"Station status records: {summary.status_count}")
    print(f"Records that join by station_id: {summary.matching_count}")

    if summary.stations_without_status:
        print(
            "Warning: stations without status: "
            f"{len(summary.stations_without_status)}"
        )
    if summary.statuses_without_station:
        print(
            "Warning: statuses without station information: "
            f"{len(summary.statuses_without_station)}"
        )

    matching_ids = sorted(set(information) & set(statuses))
    if matching_ids:
        station_id = matching_ids[0]
        station = information[station_id]
        status = statuses[station_id]
        bikes = status.get(
            "num_bikes_available", status.get("num_vehicles_available", "unknown")
        )
        docks = status.get("num_docks_available", "unknown")
        print("\nExample joined station:")
        print(f"  ID: {station_id}")
        print(f"  Name: {station_display_name(station.get('name'))}")
        print(f"  Capacity: {station.get('capacity', 'unknown')}")
        print(f"  Bikes available now: {bikes}")
        print(f"  Docks available now: {docks}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
