import unittest

from pipeline.extract import (
    GbfsError,
    GbfsFeeds,
    discover_feed_urls,
    validate_station_relationship,
)


class DiscoverFeedUrlsTests(unittest.TestCase):
    def test_discovers_version_2_localized_feeds(self):
        discovery = {
            "data": {
                "en": {
                    "feeds": [
                        {"name": "station_information", "url": "https://example/info"},
                        {"name": "station_status", "url": "https://example/status"},
                    ]
                }
            }
        }

        urls = discover_feed_urls(discovery)

        self.assertEqual(urls["station_information"], "https://example/info")
        self.assertEqual(urls["station_status"], "https://example/status")

    def test_discovers_version_3_feeds(self):
        discovery = {
            "data": {
                "feeds": [
                    {"name": "station_information", "url": "https://example/info"},
                    {"name": "station_status", "url": "https://example/status"},
                ]
            }
        }

        urls = discover_feed_urls(discovery)

        self.assertEqual(urls["station_status"], "https://example/status")

    def test_rejects_missing_required_feed(self):
        discovery = {"data": {"en": {"feeds": []}}}

        with self.assertRaises(GbfsError):
            discover_feed_urls(discovery)


class ValidateStationRelationshipTests(unittest.TestCase):
    def test_counts_matching_and_unmatched_station_ids(self):
        feeds = GbfsFeeds(
            discovery={},
            station_information={
                "data": {"stations": [{"station_id": "A"}, {"station_id": "B"}]}
            },
            station_status={
                "data": {"stations": [{"station_id": "A"}, {"station_id": "C"}]}
            },
            station_information_url="https://example/info",
            station_status_url="https://example/status",
        )

        summary = validate_station_relationship(feeds)

        self.assertEqual(summary.matching_count, 1)
        self.assertEqual(summary.stations_without_status, ("B",))
        self.assertEqual(summary.statuses_without_station, ("C",))


if __name__ == "__main__":
    unittest.main()
