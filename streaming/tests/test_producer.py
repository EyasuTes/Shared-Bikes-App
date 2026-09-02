import json
import unittest

from pipeline.tests.test_transform import sample_feeds
from pipeline.transform import transform_station_feeds
from streaming.producer import (
    build_station_events,
    changed_events,
    parse_poll_seconds,
    publish_events,
)


class FakeProducer:
    def __init__(self):
        self.messages = []

    def produce(self, **message):
        self.messages.append(message)
        message["on_delivery"](None, object())

    def poll(self, timeout):
        return timeout

    def flush(self, timeout):
        return 0


class StationProducerTests(unittest.TestCase):
    def test_builds_versioned_event_keyed_by_station(self):
        transformed = transform_station_feeds(sample_feeds())

        events = build_station_events(transformed)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].key, "A")
        self.assertEqual(events[0].value["schema_version"], 1)
        self.assertEqual(events[0].value["station_name"], "Example Station")
        self.assertEqual(events[0].value["bikes_available"], 4)
        self.assertTrue(events[0].value["reported_at"].endswith("Z"))

    def test_filters_observations_already_published_by_this_process(self):
        events = build_station_events(transform_station_feeds(sample_feeds()))
        seen = {events[0].key: events[0].value["event_id"]}

        self.assertEqual(changed_events(events, seen), ())

    def test_publishes_json_and_waits_for_delivery(self):
        events = build_station_events(transform_station_feeds(sample_feeds()))
        producer = FakeProducer()

        count = publish_events(producer, "station-status", events)

        self.assertEqual(count, 1)
        self.assertEqual(producer.messages[0]["topic"], "station-status")
        self.assertEqual(producer.messages[0]["key"], "A")
        self.assertEqual(json.loads(producer.messages[0]["value"])["station_id"], "A")

    def test_poll_interval_is_bounded(self):
        self.assertEqual(parse_poll_seconds("60"), 60)
        with self.assertRaises(Exception):
            parse_poll_seconds("5")


if __name__ == "__main__":
    unittest.main()
