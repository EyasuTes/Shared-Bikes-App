"""Extract Capital Bikeshare data from its public GBFS feeds."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_DISCOVERY_URL = (
    "https://gbfs.capitalbikeshare.com/gbfs/2.3/gbfs.json"
)


class GbfsError(RuntimeError):
    """Raised when a GBFS response cannot be fetched or validated."""


@dataclass(frozen=True)
class GbfsFeeds:
    """The two Capital Bikeshare feeds needed by this project."""

    discovery: dict[str, Any]
    station_information: dict[str, Any]
    station_status: dict[str, Any]
    station_information_url: str
    station_status_url: str


@dataclass(frozen=True)
class FeedSummary:
    """Validation result for a pair of station feeds."""

    information_count: int
    status_count: int
    matching_count: int
    stations_without_status: tuple[str, ...]
    statuses_without_station: tuple[str, ...]


def fetch_json(url: str, timeout_seconds: float = 15) -> dict[str, Any]:
    """Fetch one JSON document and provide a useful error if it fails."""

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "my-app-learning-pipeline/1.0",
        },
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            document = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise GbfsError(f"Could not fetch valid JSON from {url}: {error}") from error

    if not isinstance(document, dict):
        raise GbfsError(f"Expected a JSON object from {url}")

    return document


def discover_feed_urls(
    discovery: dict[str, Any], language: str = "en"
) -> dict[str, str]:
    """Read feed URLs from either a GBFS 2.x or 3.x discovery document."""

    data = discovery.get("data")
    if not isinstance(data, dict):
        raise GbfsError("Discovery document is missing the 'data' object")

    # GBFS 2.x groups feeds by language; GBFS 3.x places them in data.feeds.
    if isinstance(data.get("feeds"), list):
        feed_list = data["feeds"]
    else:
        localized_data = data.get(language)
        if not isinstance(localized_data, dict):
            available = ", ".join(sorted(str(key) for key in data)) or "none"
            raise GbfsError(
                f"Language '{language}' is unavailable; available entries: {available}"
            )
        feed_list = localized_data.get("feeds")

    if not isinstance(feed_list, list):
        raise GbfsError("Discovery document is missing the 'feeds' array")

    urls: dict[str, str] = {}
    for feed in feed_list:
        if not isinstance(feed, dict):
            continue
        name = feed.get("name")
        url = feed.get("url")
        if isinstance(name, str) and isinstance(url, str):
            urls[name] = url

    required = {"station_information", "station_status"}
    missing = sorted(required - urls.keys())
    if missing:
        raise GbfsError(f"Discovery document is missing feeds: {', '.join(missing)}")

    return urls


def fetch_station_feeds(
    discovery_url: str = DEFAULT_DISCOVERY_URL, language: str = "en"
) -> GbfsFeeds:
    """Discover and fetch station information and live station status."""

    discovery = fetch_json(discovery_url)
    urls = discover_feed_urls(discovery, language)
    information_url = urls["station_information"]
    status_url = urls["station_status"]

    return GbfsFeeds(
        discovery=discovery,
        station_information=fetch_json(information_url),
        station_status=fetch_json(status_url),
        station_information_url=information_url,
        station_status_url=status_url,
    )


def stations_from(document: dict[str, Any], feed_name: str) -> list[dict[str, Any]]:
    """Extract and validate the station array from a GBFS document."""

    data = document.get("data")
    stations = data.get("stations") if isinstance(data, dict) else None
    if not isinstance(stations, list):
        raise GbfsError(f"{feed_name} is missing data.stations")
    if not all(isinstance(station, dict) for station in stations):
        raise GbfsError(f"{feed_name} contains a station that is not an object")
    return stations


def index_stations(
    stations: list[dict[str, Any]], feed_name: str
) -> dict[str, dict[str, Any]]:
    """Index stations by ID and reject missing or duplicate IDs."""

    indexed: dict[str, dict[str, Any]] = {}
    for station in stations:
        station_id = station.get("station_id")
        if not isinstance(station_id, str) or not station_id.strip():
            raise GbfsError(f"{feed_name} contains a missing or invalid station_id")
        if station_id in indexed:
            raise GbfsError(f"{feed_name} contains duplicate station_id {station_id}")
        indexed[station_id] = station
    return indexed


def validate_station_relationship(feeds: GbfsFeeds) -> FeedSummary:
    """Check that station information and status records can be joined by ID."""

    information = index_stations(
        stations_from(feeds.station_information, "station_information"),
        "station_information",
    )
    statuses = index_stations(
        stations_from(feeds.station_status, "station_status"),
        "station_status",
    )

    information_ids = set(information)
    status_ids = set(statuses)
    return FeedSummary(
        information_count=len(information_ids),
        status_count=len(status_ids),
        matching_count=len(information_ids & status_ids),
        stations_without_status=tuple(sorted(information_ids - status_ids)),
        statuses_without_station=tuple(sorted(status_ids - information_ids)),
    )


def station_display_name(value: Any) -> str:
    """Return a readable station name for GBFS 2.x strings or 3.x translations."""

    if isinstance(value, str):
        return value
    if isinstance(value, list):
        for translation in value:
            if isinstance(translation, dict) and isinstance(translation.get("text"), str):
                return translation["text"]
    return "Unknown station"
