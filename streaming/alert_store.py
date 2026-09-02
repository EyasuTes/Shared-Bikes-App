"""Persist the current alert state while retaining resolved alert history."""

from __future__ import annotations

from typing import Any

from streaming.alert_rules import AlertDecision, StationObservation


FIND_ACTIVE_ALERT_SQL = """
    SELECT id, severity
    FROM station_alerts
    WHERE station_id = %s AND resolved_at IS NULL
    FOR UPDATE
"""

RESOLVE_ALERT_SQL = """
    UPDATE station_alerts
    SET resolved_at = CURRENT_TIMESTAMP,
        updated_at = CURRENT_TIMESTAMP,
        last_reported_at = %s,
        bikes_available = %s,
        last_event_id = %s
    WHERE id = %s
"""

UPDATE_ALERT_SQL = """
    UPDATE station_alerts
    SET station_name = %s,
        bikes_available = %s,
        depletion_rate_per_minute = %s,
        predicted_minutes_to_empty = %s,
        reason = %s,
        last_reported_at = %s,
        last_event_id = %s,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = %s
"""

INSERT_ALERT_SQL = """
    INSERT INTO station_alerts (
      station_id, station_name, severity, bikes_available,
      depletion_rate_per_minute, predicted_minutes_to_empty, reason,
      first_reported_at, last_reported_at, last_event_id
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def apply_alert_decision(
    connection: Any,
    observation: StationObservation,
    event_id: str,
    decision: AlertDecision,
) -> str:
    """Create, update, change, or resolve the station's active alert."""

    with connection.cursor() as cursor:
        cursor.execute(FIND_ACTIVE_ALERT_SQL, (observation.station_id,))
        active_alert = cursor.fetchone()

        if decision.severity is None:
            if active_alert is None:
                return "healthy"
            cursor.execute(
                RESOLVE_ALERT_SQL,
                (
                    observation.reported_at,
                    observation.bikes_available,
                    event_id,
                    active_alert[0],
                ),
            )
            return "resolved"

        if active_alert is not None and active_alert[1] == decision.severity:
            cursor.execute(
                UPDATE_ALERT_SQL,
                (
                    observation.station_name,
                    observation.bikes_available,
                    decision.depletion_rate_per_minute,
                    decision.predicted_minutes_to_empty,
                    decision.reason,
                    observation.reported_at,
                    event_id,
                    active_alert[0],
                ),
            )
            return "updated"

        changed_severity = active_alert is not None
        if active_alert is not None:
            cursor.execute(
                RESOLVE_ALERT_SQL,
                (
                    observation.reported_at,
                    observation.bikes_available,
                    event_id,
                    active_alert[0],
                ),
            )

        cursor.execute(
            INSERT_ALERT_SQL,
            (
                observation.station_id,
                observation.station_name,
                decision.severity,
                observation.bikes_available,
                decision.depletion_rate_per_minute,
                decision.predicted_minutes_to_empty,
                decision.reason,
                observation.reported_at,
                observation.reported_at,
                event_id,
            ),
        )
        return "severity_changed" if changed_severity else "created"
