from pathlib import Path
from unittest.mock import patch

import pytest

from container_compose_proxy.compose import (
    has_compose_project_name,
    is_foreground_up,
    run_compose,
)


def test_is_foreground_up_detects_attached_up() -> None:
    assert is_foreground_up(["up"])
    assert is_foreground_up(["--profile", "db", "up"])
    assert not is_foreground_up(["up", "-d"])
    assert not is_foreground_up(["up", "--detach"])
    assert not is_foreground_up(["ps"])


def test_run_compose_stops_foreground_up_on_keyboard_interrupt() -> None:
    def fake_run(cmd, **kwargs):
        if "up" in cmd:
            raise KeyboardInterrupt
        return None

    with patch("container_compose_proxy.compose.run", side_effect=fake_run) as run:
        with pytest.raises(KeyboardInterrupt):
            run_compose("engine", Path("/project"), [Path("/project/compose.yml")], ["up"])

    stop_cmd = run.call_args_list[1].args[0]
    assert "--project-name" in stop_cmd
    assert "project" in stop_cmd
    assert stop_cmd[-1] == "stop"


def test_run_compose_sets_project_name_from_host_project_dir() -> None:
    with patch("container_compose_proxy.compose.run") as run:
        run.return_value.returncode = 0
        run_compose(
            "engine",
            Path("/projects/example-service"),
            [Path("/projects/example-service/docker-compose.yml")],
            ["up", "-d"],
        )

    cmd = run.call_args.args[0]
    assert "--project-name" in cmd
    assert "example-service" in cmd


def test_run_compose_preserves_explicit_project_name() -> None:
    with patch("container_compose_proxy.compose.run") as run:
        run.return_value.returncode = 0
        run_compose(
            "engine",
            Path("/projects/example-service"),
            [Path("/projects/example-service/docker-compose.yml")],
            ["--project-name", "custom", "up", "-d"],
        )

    cmd = run.call_args.args[0]
    assert cmd.count("--project-name") == 1
    assert "custom" in cmd


def test_has_compose_project_name_detects_explicit_long_option() -> None:
    assert has_compose_project_name(["--project-name", "custom", "up"])
    assert has_compose_project_name(["--project-name=custom", "up"])
    assert not has_compose_project_name(["up", "-d"])
