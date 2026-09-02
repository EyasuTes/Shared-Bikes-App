"""Airflow DAG orchestrating the reusable Capital Bikeshare ETL functions."""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.sdk import dag, task

from pipeline.artifacts import (
    create_run_directory,
    read_extracted_artifact,
    read_transformed_artifact,
    remove_run_artifacts,
    write_extracted_artifact,
    write_transformed_artifact,
)
from pipeline.extract import DEFAULT_DISCOVERY_URL, fetch_station_feeds
from pipeline.load import load_to_postgres
from pipeline.transform import transform_station_feeds


ARTIFACT_ROOT = Path(os.getenv("ETL_ARTIFACT_DIR", "/opt/airflow/etl-artifacts"))


@dag(
    dag_id="capital_bikeshare_etl",
    description="Fetch, clean, and store Capital Bikeshare station availability",
    schedule="*/5 * * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(seconds=30)},
    tags=["capital-bikeshare", "gbfs", "etl", "postgres"],
)
def capital_bikeshare_etl():
    @task(task_id="extract")
    def extract_task() -> str:
        """Fetch raw GBFS data and write it to this run's shared directory."""

        discovery_url = os.getenv("GBFS_DISCOVERY_URL", DEFAULT_DISCOVERY_URL)
        feeds = fetch_station_feeds(discovery_url)
        run_directory = create_run_directory(ARTIFACT_ROOT)
        return str(write_extracted_artifact(feeds, run_directory))

    @task(task_id="transform")
    def transform_task(extracted_path: str) -> str:
        """Clean raw feeds and write database-ready records for the load task."""

        extracted_file = Path(extracted_path)
        feeds = read_extracted_artifact(extracted_file)
        transformed = transform_station_feeds(feeds)
        return str(write_transformed_artifact(transformed, extracted_file.parent))

    @task(task_id="load")
    def load_task(extracted_path: str, transformed_path: str) -> dict[str, int]:
        """Load one transaction into PostgreSQL, then remove temporary artifacts."""

        database_url = os.environ["DATABASE_URL"]
        feeds = read_extracted_artifact(Path(extracted_path))
        transformed = read_transformed_artifact(Path(transformed_path))
        summary = load_to_postgres(database_url, feeds, transformed)
        remove_run_artifacts(Path(extracted_path), ARTIFACT_ROOT)
        return {
            "raw_feeds_processed": summary.raw_feeds_processed,
            "stations_processed": summary.stations_processed,
            "statuses_processed": summary.statuses_processed,
        }

    extracted_path = extract_task()
    transformed_path = transform_task(extracted_path)
    load_task(extracted_path, transformed_path)


capital_bikeshare_etl()
