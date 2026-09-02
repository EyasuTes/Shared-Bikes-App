"""Transform raw GBFS documents into records matching the PostgreSQL schema."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pipeline.extract import GbfsError, GbfsFeeds, index_stations, stations_from


class TransformError(ValueError):
    """Raised when a required GBFS value cannot be cleaned safely."""


@dataclass(frozen=True)
class StationRecord:
    station_id: str
    name: str
    short_name: str | None
    latitude: float
    longitude: float
    capacity: int
    source_last_updated: datetime


@dataclass(frozen=True)
class StationStatusRecord:
    station_id: str
    reported_at: datetime
    bikes_available: int
    bikes_disabled: int
    docks_available: int
    docks_disabled: int
    is_installed: bool
    is_renting: bool
    is_returning: bool


@dataclass(frozen=True)
class TransformedFeeds:
    stations: tuple[StationRecord, ...]
    statuses: tuple[StationStatusRecord, ...]
    skipped_status_ids: tuple[str, ...]


def parse_gbfs_timestamp(value: Any, field_name: str) -> datetime:
    """Convert a GBFS 2.x Unix timestamp or GBFS 3.x RFC3339 value to UTC."""

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value, timezone.utc)
        except (OverflowError, OSError, ValueError) as error:
            raise TransformError(f"{field_name} is outside the valid date range") from error

    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise TransformError(f"{field_name} is not a valid timestamp") from error
        if parsed.tzinfo is None:
            raise TransformError(f"{field_name} must include a timezone")
        return parsed.astimezone(timezone.utc)

    raise TransformError(f"{field_name} is missing or invalid")


def localized_text(value: Any, field_name: str, required: bool = True) -> str | None:
    """Clean a GBFS 2.x string or select a GBFS 3.x localized string."""

    text: str | None = None
    if isinstance(value, str):
        text = value.strip()
    elif isinstance(value, list):
        for translation in value:
            if isinstance(translation, dict) and isinstance(translation.get("text"), str):
                candidate = translation["text"].strip()
                if candidate:
                    text = candidate
                    break

    if text:
        return text
    if required:
        raise TransformError(f"{field_name} is missing or empty")
    return None


def non_negative_integer(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TransformError(f"{field_name} must be a non-negative integer")
    return value


def number_in_range(value: Any, field_name: str, minimum: float, maximum: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TransformError(f"{field_name} must be a number")
    result = float(value)
    if not minimum <= result <= maximum:
        raise TransformError(f"{field_name} must be between {minimum} and {maximum}")
    return result


def gbfs_boolean(value: Any, field_name: str) -> bool:
    """Normalize GBFS 2.x integer flags and GBFS 3.x JSON booleans."""

    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    raise TransformError(f"{field_name} must be true/false or 0/1")


def transform_station_feeds(feeds: GbfsFeeds) -> TransformedFeeds:
    """Clean both feeds and retain only statuses with matching station details."""

    try:
        information = index_stations(
            stations_from(feeds.station_information, "station_information"),
            "station_information",
        )
        statuses = index_stations(
            stations_from(feeds.station_status, "station_status"),
            "station_status",
        )
    except GbfsError as error:
        raise TransformError(str(error)) from error

    information_updated_at = parse_gbfs_timestamp(
        feeds.station_information.get("last_updated"),
        "station_information.last_updated",
    )
    status_feed_updated_at = parse_gbfs_timestamp(
        feeds.station_status.get("last_updated"),
        "station_status.last_updated",
    )

    station_records: list[StationRecord] = []
    for station_id, station in information.items():
        station_records.append(
            StationRecord(
                station_id=station_id,
                name=localized_text(station.get("name"), f"station {station_id} name") or "",
                short_name=localized_text(
                    station.get("short_name"),
                    f"station {station_id} short_name",
                    required=False,
                ),
                latitude=number_in_range(
                    station.get("lat"), f"station {station_id} lat", -90, 90
                ),
                longitude=number_in_range(
                    station.get("lon"), f"station {station_id} lon", -180, 180
                ),
                capacity=non_negative_integer(
                    station.get("capacity"), f"station {station_id} capacity"
                ),
                source_last_updated=information_updated_at,
            )
        )

    status_records: list[StationStatusRecord] = []
    skipped_status_ids: list[str] = []
    for station_id, status in statuses.items():
        if station_id not in information:
            skipped_status_ids.append(station_id)
            continue

        bikes_available = status.get(
            "num_bikes_available", status.get("num_vehicles_available")
        )
        bikes_disabled = status.get(
            "num_bikes_disabled", status.get("num_vehicles_disabled", 0)
        )
        reported_at_value = status.get("last_reported", status_feed_updated_at)
        status_records.append(
            StationStatusRecord(
                station_id=station_id,
                reported_at=parse_gbfs_timestamp(
                    reported_at_value, f"station {station_id} last_reported"
                ),
                bikes_available=non_negative_integer(
                    bikes_available, f"station {station_id} bikes available"
                ),
                bikes_disabled=non_negative_integer(
                    bikes_disabled, f"station {station_id} bikes disabled"
                ),
                docks_available=non_negative_integer(
                    status.get("num_docks_available"),
                    f"station {station_id} docks available",
                ),
                docks_disabled=non_negative_integer(
                    status.get("num_docks_disabled", 0),
                    f"station {station_id} docks disabled",
                ),
                is_installed=gbfs_boolean(
                    status.get("is_installed"), f"station {station_id} is_installed"
                ),
                is_renting=gbfs_boolean(
                    status.get("is_renting"), f"station {station_id} is_renting"
                ),
                is_returning=gbfs_boolean(
                    status.get("is_returning"), f"station {station_id} is_returning"
                ),
            )
        )

    return TransformedFeeds(
        stations=tuple(station_records),
        statuses=tuple(status_records),
        skipped_status_ids=tuple(sorted(skipped_status_ids)),
    )
