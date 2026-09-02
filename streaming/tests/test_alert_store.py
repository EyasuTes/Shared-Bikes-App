import unittest

from streaming.alert_rules import AlertDecision
from streaming.alert_store import apply_alert_decision
from streaming.tests.test_alert_rules import observations


class FakeCursor:
    def __init__(self, active_alert):
        self.active_alert = active_alert
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False

    def execute(self, statement, parameters):
        self.executions.append((statement, parameters))

    def fetchone(self):
        return self.active_alert


class FakeConnection:
    def __init__(self, active_alert=None):
        self.test_cursor = FakeCursor(active_alert)

    def cursor(self):
        return self.test_cursor


def decision(severity):
    return AlertDecision(
        severity=severity,
        bikes_available=4,
        depletion_rate_per_minute=1.0,
        predicted_minutes_to_empty=4.0,
        reason="Test decision",
    )


class AlertStoreTests(unittest.TestCase):
    def test_inserts_a_new_alert(self):
        connection = FakeConnection()

        action = apply_alert_decision(
            connection, observations([4])[0], "event-1", decision("warning")
        )

        self.assertEqual(action, "created")
        self.assertEqual(len(connection.test_cursor.executions), 2)

    def test_updates_an_existing_alert_of_the_same_severity(self):
        connection = FakeConnection(active_alert=(7, "warning"))

        action = apply_alert_decision(
            connection, observations([4])[0], "event-2", decision("warning")
        )

        self.assertEqual(action, "updated")
        self.assertEqual(len(connection.test_cursor.executions), 2)

    def test_resolves_an_alert_when_risk_clears(self):
        connection = FakeConnection(active_alert=(7, "warning"))

        action = apply_alert_decision(
            connection, observations([10])[0], "event-3", decision(None)
        )

        self.assertEqual(action, "resolved")
        self.assertEqual(len(connection.test_cursor.executions), 2)


if __name__ == "__main__":
    unittest.main()
