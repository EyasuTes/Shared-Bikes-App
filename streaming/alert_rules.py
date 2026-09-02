"""Pure, testable rules for predicting station bike depletion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence


@dataclass(frozen=True)
class StationObservation:
    station_id: str
    station_name: str
    reported_at: datetime
    bikes_available: int
    is_installed: bool
    is_renting: bool


@dataclass(frozen=True)
class AlertDecision:
    severity: str | None
    bikes_available: int
    depletion_rate_per_minute: float | None
    predicted_minutes_to_empty: float | None
    reason: str


def calculate_depletion_rate(
    observations: Sequence[StationObservation],
) -> float | None:
    """Estimate bikes lost per minute with linear regression."""

    if len(observations) < 3:
        return None

    ordered = sorted(observations, key=lambda item: item.reported_at)
    start = ordered[0].reported_at
    minutes = [
        (observation.reported_at - start).total_seconds() / 60
        for observation in ordered
    ]
    if minutes[-1] - minutes[0] < 2:
        return None

    mean_time = sum(minutes) / len(minutes)
    mean_bikes = sum(item.bikes_available for item in ordered) / len(ordered)
    denominator = sum((minute - mean_time) ** 2 for minute in minutes)
    if denominator == 0:
        return None

    slope = sum(
        (minute - mean_time) * (observation.bikes_available - mean_bikes)
        for minute, observation in zip(minutes, ordered)
    ) / denominator

    # Positive/flat slopes mean the station is not currently depleting.
    if slope >= -0.05:
        return 0.0
    return round(-slope, 3)


def evaluate_station_risk(
    observations: Sequence[StationObservation],
    *,
    warning_bikes: int = 5,
    critical_bikes: int = 2,
    warning_minutes: int = 15,
    critical_minutes: int = 5,
) -> AlertDecision:
    """Classify the latest observation as healthy, warning, or critical."""

    if not observations:
        raise ValueError("At least one station observation is required")

    latest = max(observations, key=lambda item: item.reported_at)
    if not latest.is_installed or not latest.is_renting:
        return AlertDecision(
            severity=None,
            bikes_available=latest.bikes_available,
            depletion_rate_per_minute=None,
            predicted_minutes_to_empty=None,
            reason="Station is not currently available for bike rentals",
        )

    rate = calculate_depletion_rate(observations)
    predicted_minutes = None
    if rate is not None and rate > 0:
        predicted_minutes = round(latest.bikes_available / rate, 1)

    if latest.bikes_available <= critical_bikes:
        severity = "critical"
        reason = f"Only {latest.bikes_available} bike(s) remain"
    elif predicted_minutes is not None and predicted_minutes <= critical_minutes:
        severity = "critical"
        reason = f"Predicted to be empty in about {predicted_minutes:g} minutes"
    elif latest.bikes_available <= warning_bikes:
        severity = "warning"
        reason = f"Only {latest.bikes_available} bike(s) remain"
    elif predicted_minutes is not None and predicted_minutes <= warning_minutes:
        severity = "warning"
        reason = f"Predicted to be empty in about {predicted_minutes:g} minutes"
    else:
        severity = None
        reason = "No near-term depletion risk detected"

    return AlertDecision(
        severity=severity,
        bikes_available=latest.bikes_available,
        depletion_rate_per_minute=rate,
        predicted_minutes_to_empty=predicted_minutes,
        reason=reason,
    )
