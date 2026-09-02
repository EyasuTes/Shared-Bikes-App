"""Serialize small ETL run artifacts shared between Airflow tasks."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pipeline.extract import GbfsFeeds
from pipeline.transform import (
    StationRecord,
    StationStatusRecord,
    TransformedFeeds,
    parse_gbfs_timestamp,
)


def write_json(path: Path, value: Any) -> None:
    """Write JSON atomically so another task never sees a partial artifact."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(value, separators=(",", ":"), default=_json_default),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value).__name__} to JSON")


def create_run_directory(artifact_root: Path) -> Path:
    run_directory = artifact_root / str(uuid4())
    run_directory.mkdir(parents=True, exist_ok=False)
    return run_directory


def write_extracted_artifact(feeds: GbfsFeeds, run_directory: Path) -> Path:
    path = run_directory / "extracted.json"
    write_json(path, asdict(feeds))
    return path


def read_extracted_artifact(path: Path) -> GbfsFeeds:
    value = json.loads(path.read_text(encoding="utf-8"))
    return GbfsFeeds(**value)


def write_transformed_artifact(
    transformed: TransformedFeeds, run_directory: Path
) -> Path:
    path = run_directory / "transformed.json"
    write_json(path, asdict(transformed))
    return path


def read_transformed_artifact(path: Path) -> TransformedFeeds:
    value = json.loads(path.read_text(encoding="utf-8"))
    stations = tuple(
        StationRecord(
            **{
                **station,
                "source_last_updated": parse_gbfs_timestamp(
                    station["source_last_updated"], "station.source_last_updated"
                ),
            }
        )
        for station in value["stations"]
    )
    statuses = tuple(
        StationStatusRecord(
            **{
                **status,
                "reported_at": parse_gbfs_timestamp(
                    status["reported_at"], "status.reported_at"
                ),
            }
        )
        for status in value["statuses"]
    )
    return TransformedFeeds(
        stations=stations,
        statuses=statuses,
        skipped_status_ids=tuple(value["skipped_status_ids"]),
    )


def remove_run_artifacts(extracted_path: Path, artifact_root: Path) -> None:
    """Remove only files inside the generated run directory after a successful load."""

    resolved_root = artifact_root.resolve()
    run_directory = extracted_path.resolve().parent
    if run_directory.parent != resolved_root:
        raise ValueError(f"Refusing to clean artifacts outside {resolved_root}")

    for filename in ("extracted.json", "transformed.json"):
        artifact_path = run_directory / filename
        if artifact_path.exists():
            artifact_path.unlink()
    run_directory.rmdir()
