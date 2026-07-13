import subprocess
from unittest.mock import patch

import pytest

import run_desktop


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.fixture(autouse=True)
def database_url(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://user:password@localhost:5432/contact_db"
    )


def test_creates_container_when_missing():
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "inspect" in cmd:
            return _completed(returncode=1, stderr="No such object")
        if "pg_isready" in cmd:
            return _completed(returncode=0)
        return _completed(returncode=0)

    with patch("run_desktop.subprocess.run", side_effect=fake_run):
        run_desktop.ensure_postgres_container()

    assert any(c[:2] == ["docker", "run"] for c in calls)
    assert not any(c[:2] == ["docker", "start"] for c in calls)


def test_starts_container_when_stopped():
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "inspect" in cmd:
            return _completed(returncode=0, stdout="false\n")
        if "pg_isready" in cmd:
            return _completed(returncode=0)
        return _completed(returncode=0)

    with patch("run_desktop.subprocess.run", side_effect=fake_run):
        run_desktop.ensure_postgres_container()

    assert any(c[:2] == ["docker", "start"] for c in calls)
    assert not any(c[:2] == ["docker", "run"] for c in calls)


def test_does_nothing_when_already_running():
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "inspect" in cmd:
            return _completed(returncode=0, stdout="true\n")
        if "pg_isready" in cmd:
            return _completed(returncode=0)
        return _completed(returncode=0)

    with patch("run_desktop.subprocess.run", side_effect=fake_run):
        run_desktop.ensure_postgres_container()

    assert not any(c[:2] == ["docker", "run"] for c in calls)
    assert not any(c[:2] == ["docker", "start"] for c in calls)


def test_skips_when_database_url_points_elsewhere(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://user:password@db.example.com:5432/contact_db"
    )
    with patch("run_desktop.subprocess.run") as mock_run:
        run_desktop.ensure_postgres_container()

    mock_run.assert_not_called()
