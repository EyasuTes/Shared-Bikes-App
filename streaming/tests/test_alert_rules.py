import unittest
from datetime import datetime, timedelta, timezone

from streaming.alert_rules import (
    StationObservation,
    calculate_depletion_rate,
    evaluate_station_risk,
)


START = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)


def observations(bike_counts, *, installed=True, renting=True):
    return tuple(
        StationObservation(
            station_id="A",
            station_name="Example Station",
            reported_at=START + timedelta(minutes=index * 3),
            bikes_available=count,
            is_installed=installed,
            is_renting=renting,
        )
        for index, count in enumerate(bike_counts)
    )


class AlertRulesTests(unittest.TestCase):
    def test_calculates_depletion_rate_from_three_observations(self):
        rate = calculate_depletion_rate(observations([16, 13, 10]))

        self.assertAlmostEqual(rate, 1.0)

    def test_warns_when_trend_predicts_depletion_within_fifteen_minutes(self):
        decision = evaluate_station_risk(observations([16, 13, 10]))

        self.assertEqual(decision.severity, "warning")
        self.assertEqual(decision.predicted_minutes_to_empty, 10.0)

    def test_marks_two_remaining_bikes_as_critical_without_waiting_for_history(self):
        decision = evaluate_station_risk(observations([2]))

        self.assertEqual(decision.severity, "critical")
        self.assertIsNone(decision.predicted_minutes_to_empty)

    def test_does_not_alert_for_healthy_stable_inventory(self):
        decision = evaluate_station_risk(observations([12, 12, 13]))

        self.assertIsNone(decision.severity)
        self.assertEqual(decision.depletion_rate_per_minute, 0.0)

    def test_does_not_create_depletion_alert_for_offline_station(self):
        decision = evaluate_station_risk(observations([1], renting=False))

        self.assertIsNone(decision.severity)


if __name__ == "__main__":
    unittest.main()
