"""Run test setup in a fresh interpreter to catch import-order regressions."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_setup(test_url):
    env = os.environ.copy()
    # Neither URL is contacted: these tests only load definitions/configuration.
    env["DATABASE_URL"] = "postgresql://unused:unused@127.0.0.1:1/operon_dev"
    env["TEST_DATABASE_URL"] = test_url
    return subprocess.run(
        [
            sys.executable,
            "-c",
            """
import runpy
runpy.run_path('tests/conftest.py')
from sqlalchemy import make_url
from src.db import engine
import os
expected = make_url(os.environ['TEST_DATABASE_URL'])
assert engine.url.database == expected.database
assert engine.url.port == expected.port
print('test database configured before model imports')
""",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        check=False,
        text=True,
        timeout=15,
    )


def test_test_database_overrides_development_url_before_model_import():
    result = run_setup("postgresql://unused:unused@127.0.0.1:2/setup_test")
    assert result.returncode == 0, result.stderr
    assert "configured before model imports" in result.stdout


def test_non_test_database_is_rejected_without_exposing_password():
    result = run_setup("postgresql://unused:do-not-print-this@127.0.0.1:2/operon_dev")
    assert result.returncode != 0
    assert "must point to a *_test database" in result.stderr
    assert "do-not-print-this" not in result.stderr + result.stdout
