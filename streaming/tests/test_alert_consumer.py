import json
import unittest
from datetime import datetime, timezone

from streaming.alert_consumer import (
    AlertConsumerError,
    StationHistory,
    parse_station_event,
)


def event(reported_at="2026-09-02T12:00:00Z"):
    return {
        "schema_version": 1,
        "event_type": "station_status",
        "event_id": f"A:{reported_at}",
        "station_id": "A",
        "station_name": "Example Station",
        "reported_at": reported_at,
        "bikes_available": 4,
        "is_installed": True,
        "is_renting": True,
    }


class AlertConsumerTests(unittest.TestCase):
    def test_parses_producer_event_contract(self):
        event_id, observation = parse_station_event(json.dumps(event()).encode())

        self.assertEqual(event_id, "A:2026-09-02T12:00:00Z")
        self.assertEqual(observation.station_id, "A")
        self.assertEqual(observation.bikes_available, 4)
        self.assertEqual(
            observation.reported_at,
            datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
        )

    def test_rejects_an_unsupported_event(self):
        invalid = event()
        invalid["schema_version"] = 2

        with self.assertRaises(AlertConsumerError):
            parse_station_event(json.dumps(invalid))

    def test_history_ignores_duplicate_or_older_observations(self):
        history = StationHistory()
        _, first = parse_station_event(json.dumps(event()))
        _, older = parse_station_event(
            json.dumps(event("2026-09-02T11:59:00Z"))
        )

        self.assertEqual(len(history.add(first)), 1)
        self.assertIsNone(history.add(first))
        self.assertIsNone(history.add(older))


if __name__ == "__main__":
    unittest.main()
