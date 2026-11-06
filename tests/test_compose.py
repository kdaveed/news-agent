"""Optional Compose rendering check; no daemon or containers required."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from newsalert.collector.config import CollectorSettings


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker CLI needed to render Compose")
@pytest.mark.parametrize("override", [False, True])
def test_compose_collector_settings_reach_configuration(tmp_path, monkeypatch, override):
    if subprocess.run(["docker", "compose", "version"], check=False, capture_output=True, timeout=10).returncode:
        pytest.skip("Docker Compose plugin is unavailable")
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("NEWSALERT_", "MAILPIT_"))
    }
    env_file = tmp_path / "review.env"
    env_file.write_text("NEWSALERT_SECRET_KEY=compose-test-session-secret-0123456789\n")
    values = {
        "NEWSALERT_HTTP_USER_AGENT": "newsalert-review (+https://example.com/newsalert)",
        "NEWSALERT_AUTO_MIN_OUTLETS": "125",
        "NEWSALERT_AUTO_MIN_RSS": "3",
        "NEWSALERT_REVIEW_MIN_OUTLETS": "45",
    }
    if override:
        # Verify the documented .env route, not only shell interpolation.
        with env_file.open("a") as stream:
            stream.write("".join(f"{key}={value}\n" for key, value in values.items()))
    compose_file = Path(__file__).resolve().parents[1] / "docker-compose.yml"
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "-f",
            str(compose_file),
            "config",
            "--format",
            "json",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    configured = json.loads(result.stdout)["services"]["collector"]["environment"]
    for key in values:
        monkeypatch.setenv(key, configured[key])
    settings = CollectorSettings(_env_file=None)
    if override:
        assert settings.http_user_agent == values["NEWSALERT_HTTP_USER_AGENT"]
        assert (settings.auto_min_outlets, settings.auto_min_rss, settings.review_min_outlets) == (
            125,
            3,
            45,
        )
    else:
        assert settings.http_user_agent.startswith("newsalert-collector/0.1")
        assert (settings.auto_min_outlets, settings.auto_min_rss, settings.review_min_outlets) == (
            100,
            2,
            30,
        )
