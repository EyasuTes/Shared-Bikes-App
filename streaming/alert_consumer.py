"""Consume station status events, predict depletion, and persist alerts."""

from __future__ import annotations

import json
import os
import signal
import sys
from collections import defaultdict, deque
from datetime import datetime
from threading import Event
from typing import Any

from streaming.alert_rules import StationObservation, evaluate_station_risk
from streaming.alert_store import apply_alert_decision


class AlertConsumerError(RuntimeError):
    """Raised for invalid configuration or station events."""


class StationHistory:
    """Keep a bounded, in-memory trend window for each station."""

    def __init__(self, maximum_observations: int = 10):
        self._observations: dict[str, deque[StationObservation]] = defaultdict(
            lambda: deque(maxlen=maximum_observations)
        )

    def add(self, observation: StationObservation) -> tuple[StationObservation, ...] | None:
        history = self._observations[observation.station_id]
        if history and observation.reported_at <= history[-1].reported_at:
            return None
        history.append(observation)
        return tuple(history)


def parse_station_event(value: bytes | str) -> tuple[str, StationObservation]:
    """Validate the producer's JSON contract and return an observation."""

    try:
        event = json.loads(value)
        if event.get("schema_version") != 1 or event.get("event_type") != "station_status":
            raise ValueError("unsupported event schema")

        event_id = str(event["event_id"]).strip()
        station_id = str(event["station_id"]).strip()
        station_name = str(event["station_name"]).strip()
        bikes_available = event["bikes_available"]
        reported_at_text = str(event["reported_at"])
        is_installed = event["is_installed"]
        is_renting = event["is_renting"]

        if not event_id or not station_id or not station_name:
            raise ValueError("event identifiers and station name cannot be empty")
        if isinstance(bikes_available, bool) or not isinstance(bikes_available, int):
            raise ValueError("bikes_available must be an integer")
        if bikes_available < 0:
            raise ValueError("bikes_available cannot be negative")
        if not isinstance(is_installed, bool) or not isinstance(is_renting, bool):
            raise ValueError("station flags must be booleans")

        reported_at = datetime.fromisoformat(reported_at_text.replace("Z", "+00:00"))
        if reported_at.tzinfo is None:
            raise ValueError("reported_at must include a timezone")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise AlertConsumerError(f"Invalid station-status event: {error}") from error

    return event_id, StationObservation(
        station_id=station_id,
        station_name=station_name,
        reported_at=reported_at,
        bikes_available=bikes_available,
        is_installed=is_installed,
        is_renting=is_renting,
    )


def create_consumer(bootstrap_servers: str, group_id: str) -> Any:
    try:
        from confluent_kafka import Consumer
    except ModuleNotFoundError as error:
        raise AlertConsumerError(
            "Kafka driver is missing; install streaming/requirements.txt"
        ) from error

    return Consumer(
        {
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "latest",
            "enable.auto.commit": False,
        }
    )


def connect_to_postgres(database_url: str) -> Any:
    if not database_url.strip():
        raise AlertConsumerError("DATABASE_URL is required")
    try:
        import psycopg
    except ModuleNotFoundError as error:
        raise AlertConsumerError(
            "PostgreSQL driver is missing; install streaming/requirements.txt"
        ) from error

    try:
        return psycopg.connect(database_url)
    except Exception as error:
        raise AlertConsumerError(f"PostgreSQL connection failed: {error}") from error


def main() -> int:
    bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:19092")
    topic = os.getenv("KAFKA_STATION_STATUS_TOPIC", "station-status")
    group_id = os.getenv("KAFKA_ALERT_CONSUMER_GROUP", "station-depletion-alerts-v1")
    database_url = os.getenv("DATABASE_URL", "")

    try:
        consumer = create_consumer(bootstrap_servers, group_id)
        connection = connect_to_postgres(database_url)
    except AlertConsumerError as error:
        print(f"Alert consumer configuration failed: {error}", file=sys.stderr, flush=True)
        return 1

    stop_event = Event()

    def request_stop(signum: int, frame: Any) -> None:
        del signum, frame
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    consumer.subscribe([topic])
    histories = StationHistory()
    processed_count = 0

    print(f"Alert consumer started: topic={topic}, group={group_id}", flush=True)
    try:
        while not stop_event.is_set():
            message = consumer.poll(1.0)
            if message is None:
                continue
            if message.error():
                print(f"Kafka consumer error: {message.error()}", file=sys.stderr, flush=True)
                continue

            try:
                event_id, observation = parse_station_event(message.value())
                history = histories.add(observation)
                if history is not None:
                    decision = evaluate_station_risk(history)
                    with connection.transaction():
                        action = apply_alert_decision(
                            connection, observation, event_id, decision
                        )
                    if action in {"created", "severity_changed", "resolved"}:
                        print(
                            f"Alert {action}: station={observation.station_id}, "
                            f"severity={decision.severity or 'none'}, "
                            f"bikes={observation.bikes_available}, reason={decision.reason}",
                            flush=True,
                        )
                consumer.commit(message=message, asynchronous=False)
                processed_count += 1
                if processed_count % 500 == 0:
                    print(f"Processed {processed_count} station status event(s)", flush=True)
            except AlertConsumerError as error:
                # Invalid messages are poison events: report and skip them so the
                # consumer can continue processing later valid observations.
                print(str(error), file=sys.stderr, flush=True)
                consumer.commit(message=message, asynchronous=False)
            except Exception as error:
                print(f"Alert processing failed: {error}", file=sys.stderr, flush=True)
                return 1
    finally:
        connection.close()
        consumer.close()

    print("Alert consumer stopped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
