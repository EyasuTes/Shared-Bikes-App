# Kafka learning setup

This increment adds a single Apache Kafka broker and one topic:

```text
station-status
```

The broker uses KRaft mode, so it does not need a separate ZooKeeper service.
This single-node configuration is for local development and demonstrations, not
for a production Kafka cluster.

## Services

- `kafka` is the long-running broker.
- `kafka-init` waits for the broker to become healthy, creates
  `station-status` if necessary, and exits successfully.

Containers in this Compose project will connect to `kafka:19092`. Programs run
directly on Windows will connect to `localhost:9092`.

## Start Kafka and create the topic

```bash
docker compose up -d kafka kafka-init
```

The `kafka-init` container is expected to show `Exited (0)` after it creates or
checks the topic. That means its one-time job succeeded.

Verify the topic:

```bash
MSYS_NO_PATHCONV=1 docker compose exec kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server kafka:19092 \
  --describe \
  --topic station-status
```

## Publish one manual test event

From Git Bash:

```bash
echo 'demo-station|{"schema_version":1,"station_id":"demo-station","station_name":"Demo station","reported_at":"2026-09-02T16:00:00Z","bikes_available":2,"docks_available":18,"is_renting":true}' | \
  MSYS_NO_PATHCONV=1 docker compose exec -T kafka /opt/kafka/bin/kafka-console-producer.sh \
  --bootstrap-server kafka:19092 \
  --topic station-status \
  --property parse.key=true \
  --property key.separator='|'
```

The station ID is the Kafka message key. Using the same key keeps events for a
station in partition order.

## Consume the test event

```bash
MSYS_NO_PATHCONV=1 docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server kafka:19092 \
  --topic station-status \
  --from-beginning \
  --max-messages 1 \
  --formatter-property print.key=true \
  --formatter-property key.separator=' | '
```

## Publish real Capital Bikeshare events

Build and start the continuous producer:

```bash
docker compose up -d --build station-producer
```

Watch its logs:

```bash
docker compose logs -f station-producer
```

The first successful cycle normally publishes one event for every station.
Later cycles publish only stations whose `reported_at` observation changed.

Inspect five real events already stored in the topic:

```bash
MSYS_NO_PATHCONV=1 docker compose exec kafka \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server kafka:19092 \
  --topic station-status \
  --from-beginning \
  --max-messages 5 \
  --formatter-property print.key=true \
  --formatter-property key.separator=' | '
```

The producer polls once per minute by default. Change `GBFS_POLL_SECONDS` in
`.env` if a different local demonstration interval is needed.

## Detect bike-depletion risk

The `alert-consumer` subscribes to `station-status`. It keeps the latest ten
observations for each station in memory and estimates the rate at which bikes
are disappearing. It creates a warning when a station has five or fewer bikes,
or is predicted to become empty within 15 minutes. It creates a critical alert
at two bikes, or when depletion is predicted within five minutes.

Start the producer and consumer:

```bash
docker compose up -d --build station-producer alert-consumer
```

Watch alert activity:

```bash
docker compose logs -f alert-consumer
```

Inspect active alerts in PostgreSQL from Git Bash:

```bash
docker compose exec db psql -U my_app_user -d my_app -c \
  "SELECT station_name, severity, bikes_available, predicted_minutes_to_empty, reason FROM station_alerts WHERE resolved_at IS NULL ORDER BY severity, bikes_available;"
```

The consumer uses a Kafka consumer group, commits a message only after its
database work succeeds, and retains resolved rows for later analysis. Because
its trend window starts empty after a restart, prediction-based alerts need at
least three new observations; low-bike alerts can appear immediately.
