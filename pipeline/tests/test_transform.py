import unittest
from datetime import timezone

from pipeline.extract import GbfsFeeds
from pipeline.transform import TransformError, transform_station_feeds


def sample_feeds() -> GbfsFeeds:
    return GbfsFeeds(
        discovery={"version": "2.3"},
        station_information={
            "version": "2.3",
            "last_updated": 1_700_000_000,
            "data": {
                "stations": [
                    {
                        "station_id": "A",
                        "name": "  Example Station  ",
                        "short_name": "001",
                        "lat": 38.9,
                        "lon": -77.0,
                        "capacity": 15,
                    }
                ]
            },
        },
        station_status={
            "version": "2.3",
            "last_updated": 1_700_000_060,
            "data": {
                "stations": [
                    {
                        "station_id": "A",
                        "last_reported": 1_700_000_050,
                        "num_bikes_available": 4,
                        "num_bikes_disabled": 1,
                        "num_docks_available": 10,
                        "num_docks_disabled": 0,
                        "is_installed": 1,
                        "is_renting": 1,
                        "is_returning": 0,
                    },
                    {"station_id": "UNKNOWN"},
                ]
            },
        },
        station_information_url="https://example/info",
        station_status_url="https://example/status",
    )


class TransformStationFeedsTests(unittest.TestCase):
    def test_cleans_station_and_status_records(self):
        transformed = transform_station_feeds(sample_feeds())

        self.assertEqual(len(transformed.stations), 1)
        self.assertEqual(transformed.stations[0].name, "Example Station")
        self.assertEqual(transformed.stations[0].source_last_updated.tzinfo, timezone.utc)
        self.assertEqual(len(transformed.statuses), 1)
        self.assertEqual(transformed.statuses[0].bikes_available, 4)
        self.assertTrue(transformed.statuses[0].is_renting)
        self.assertFalse(transformed.statuses[0].is_returning)
        self.assertEqual(transformed.skipped_status_ids, ("UNKNOWN",))

    def test_rejects_negative_capacity(self):
        feeds = sample_feeds()
        feeds.station_information["data"]["stations"][0]["capacity"] = -1

        with self.assertRaises(TransformError):
            transform_station_feeds(feeds)


if __name__ == "__main__":
    unittest.main()
