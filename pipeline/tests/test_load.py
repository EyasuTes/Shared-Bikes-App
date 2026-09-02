import unittest

from pipeline.load import load_feeds
from pipeline.tests.test_transform import sample_feeds
from pipeline.transform import transform_station_feeds


class FakeCursor:
    def __init__(self):
        self.executions = []
        self.batch_executions = []

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False

    def execute(self, statement, parameters):
        self.executions.append((statement, parameters))

    def executemany(self, statement, parameters):
        self.batch_executions.append((statement, parameters))


class FakeConnection:
    def __init__(self):
        self.test_cursor = FakeCursor()

    def cursor(self):
        return self.test_cursor


class LoadFeedsTests(unittest.TestCase):
    def test_loads_two_raw_documents_stations_then_statuses(self):
        feeds = sample_feeds()
        transformed = transform_station_feeds(feeds)
        connection = FakeConnection()

        summary = load_feeds(connection, feeds, transformed)

        self.assertEqual(len(connection.test_cursor.executions), 2)
        self.assertEqual(len(connection.test_cursor.batch_executions), 2)
        self.assertEqual(summary.raw_feeds_processed, 2)
        self.assertEqual(summary.stations_processed, 1)
        self.assertEqual(summary.statuses_processed, 1)


if __name__ == "__main__":
    unittest.main()
