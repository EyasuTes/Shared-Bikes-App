import tempfile
import unittest
from pathlib import Path

from pipeline.artifacts import (
    create_run_directory,
    read_extracted_artifact,
    read_transformed_artifact,
    remove_run_artifacts,
    write_extracted_artifact,
    write_transformed_artifact,
)
from pipeline.tests.test_transform import sample_feeds
from pipeline.transform import transform_station_feeds


class ArtifactTests(unittest.TestCase):
    def test_round_trip_and_cleanup(self):
        feeds = sample_feeds()
        transformed = transform_station_feeds(feeds)

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run_directory = create_run_directory(root)
            extracted_path = write_extracted_artifact(feeds, run_directory)
            transformed_path = write_transformed_artifact(transformed, run_directory)

            restored_feeds = read_extracted_artifact(extracted_path)
            restored_transformed = read_transformed_artifact(transformed_path)

            self.assertEqual(restored_feeds.discovery, feeds.discovery)
            self.assertEqual(restored_transformed, transformed)

            remove_run_artifacts(extracted_path, root)
            self.assertFalse(run_directory.exists())

    def test_cleanup_refuses_a_file_directly_under_root(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            unsafe_path = root / "extracted.json"
            unsafe_path.write_text("{}", encoding="utf-8")

            with self.assertRaises(ValueError):
                remove_run_artifacts(unsafe_path, root)


if __name__ == "__main__":
    unittest.main()
