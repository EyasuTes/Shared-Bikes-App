import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.load import LoadError
from pipeline.run_etl import build_database_url, read_env_file


class RunEtlConfigurationTests(unittest.TestCase):
    def test_reads_compose_env_and_builds_host_database_url(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_path = Path(temporary_directory) / ".env"
            env_path.write_text(
                "POSTGRES_USER=my_app_user\n"
                "POSTGRES_PASSWORD=local password\n"
                "POSTGRES_DB=my_app\n"
                "POSTGRES_HOST_PORT=5433\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                url = build_database_url(env_path)

        self.assertEqual(
            url,
            "postgresql://my_app_user:local%20password@127.0.0.1:5433/my_app",
        )

    def test_environment_database_url_takes_precedence(self):
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://example/override"},
            clear=True,
        ):
            url = build_database_url(Path("missing.env"))

        self.assertEqual(url, "postgresql://example/override")

    def test_missing_required_settings_is_clear(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(LoadError):
                build_database_url(Path("missing.env"))

    def test_env_reader_ignores_comments_and_blank_lines(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_path = Path(temporary_directory) / ".env"
            env_path.write_text("# comment\n\nVALUE='test'\n", encoding="utf-8")

            values = read_env_file(env_path)

        self.assertEqual(values, {"VALUE": "test"})


if __name__ == "__main__":
    unittest.main()
