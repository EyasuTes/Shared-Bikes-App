"""Continuously publish cleaned Capital Bikeshare station status events."""

from __future__ import annotations

import json
import os
import signal
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event
from typing import Any, Iterable

from pipeline.extract import DEFAULT_DISCOVERY_URL, GbfsError, fetch_station_feeds
from pipeline.transform import TransformError, TransformedFeeds, transform_station_feeds


class PublishError(RuntimeError):
    """Raised when Kafka cannot accept or deliver a station event."""


@dataclass(frozen=True)
class KafkaEvent:
    key: str
    value: dict[str, Any]


def isoformat_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_station_events(transformed: TransformedFeeds) -> tuple[KafkaEvent, ...]:
    """Join station details to status records and build versioned Kafka events."""

    stations_by_id = {station.station_id: station for station in transformed.stations}
    produced_at = isoformat_utc(datetime.now(timezone.utc))
    events: list[KafkaEvent] = []

    for status in transformed.statuses:
        station = stations_by_id[status.station_id]
        reported_at = isoformat_utc(status.reported_at)
        events.append(
            KafkaEvent(
                key=status.station_id,
                value={
                    "schema_version": 1,
                    "event_type": "station_status",
                    "event_id": f"{status.station_id}:{reported_at}",
                    "station_id": status.station_id,
                    "station_name": station.name,
                    "latitude": station.latitude,
                    "longitude": station.longitude,
                    "capacity": station.capacity,
                    "reported_at": reported_at,
                    "produced_at": produced_at,
                    "bikes_available": status.bikes_available,
                    "bikes_disabled": status.bikes_disabled,
                    "docks_available": status.docks_available,
                    "docks_disabled": status.docks_disabled,
                    "is_installed": status.is_installed,
                    "is_renting": status.is_renting,
                    "is_returning": status.is_returning,
                },
            )
        )

    return tuple(events)


def changed_events(
    events: Iterable[KafkaEvent], last_event_ids: dict[str, str]
) -> tuple[KafkaEvent, ...]:
    """Avoid republishing an unchanged station observation during the same process."""

    return tuple(
        event
        for event in events
        if last_event_ids.get(event.key) != event.value["event_id"]
    )


def publish_events(producer: Any, topic: str, events: Iterable[KafkaEvent]) -> int:
    """Publish a batch and wait until Kafka confirms every delivery."""

    event_list = tuple(events)
    delivery_errors: list[str] = []

    def delivery_callback(error: Any, message: Any) -> None:
        del message
        if error is not None:
            delivery_errors.append(str(error))

    for event in event_list:
        encoded_value = json.dumps(event.value, separators=(",", ":"))
        while True:
            try:
                producer.produce(
                    topic=topic,
                    key=event.key,
                    value=encoded_value,
                    on_delivery=delivery_callback,
                )
                break
            except BufferError:
                producer.poll(1)
        producer.poll(0)

    undelivered = producer.flush(30)
    if undelivered:
        raise PublishError(f"Kafka did not deliver {undelivered} event(s) before timeout")
    if delivery_errors:
        raise PublishError(f"Kafka delivery failed: {delivery_errors[0]}")
    return len(event_list)


def create_kafka_producer(bootstrap_servers: str) -> Any:
    try:
        from confluent_kafka import Producer
    except ModuleNotFoundError as error:
        raise PublishError(
            "Kafka driver is missing; install streaming/requirements.txt"
        ) from error

    return Producer(
        {
            "bootstrap.servers": bootstrap_servers,
            "client.id": "capital-bikeshare-station-producer",
            "enable.idempotence": True,
            "acks": "all",
        }
    )


def parse_poll_seconds(value: str) -> int:
    try:
        seconds = int(value)
    except ValueError as error:
        raise PublishError("GBFS_POLL_SECONDS must be an integer") from error
    if not 10 <= seconds <= 3600:
        raise PublishError("GBFS_POLL_SECONDS must be between 10 and 3600")
    return seconds


def main() -> int:
    bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:19092")
    topic = os.getenv("KAFKA_STATION_STATUS_TOPIC", "station-status")
    discovery_url = os.getenv("GBFS_DISCOVERY_URL", DEFAULT_DISCOVERY_URL)

    try:
        poll_seconds = parse_poll_seconds(os.getenv("GBFS_POLL_SECONDS", "60"))
        producer = create_kafka_producer(bootstrap_servers)
    except PublishError as error:
        print(f"Station producer configuration failed: {error}", file=sys.stderr, flush=True)
        return 1

    stop_event = Event()

    def request_stop(signum: int, frame: Any) -> None:
        del signum, frame
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    print(
        f"Station producer started: topic={topic}, interval={poll_seconds}s",
        flush=True,
    )
    last_event_ids: dict[str, str] = {}

    while not stop_event.is_set():
        try:
            feeds = fetch_station_feeds(discovery_url)
            transformed = transform_station_feeds(feeds)
            events = changed_events(build_station_events(transformed), last_event_ids)
            published_count = publish_events(producer, topic, events)
            for event in events:
                last_event_ids[event.key] = event.value["event_id"]
            print(
                f"Published {published_count} changed station status event(s)",
                flush=True,
            )
        except (GbfsError, TransformError, PublishError) as error:
            print(f"Station producer cycle failed: {error}", file=sys.stderr, flush=True)

        stop_event.wait(poll_seconds)

    producer.flush(10)
    print("Station producer stopped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
