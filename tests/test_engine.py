from pathlib import Path
from unittest.mock import patch

import pytest

from container_compose_proxy.config import ProxyConfig
from container_compose_proxy.engine import (
    build_engine_run_command,
    container_state,
    describe_storage,
    describe_engine,
    resolve_docker_volume,
    validate_running_engine,
)
from container_compose_proxy.errors import ProxyError


def test_container_state_reads_container_1_status_shape() -> None:
    assert container_state({"status": {"state": "running"}}) == "running"


def test_container_state_reads_plain_status_shape() -> None:
    assert container_state({"status": "running"}) == "running"


def test_build_engine_run_command_includes_container_1_defaults() -> None:
    cmd = build_engine_run_command(
        ProxyConfig(),
        "cc-test",
        Path("/project"),
        ["127.0.0.1:8080:8080"],
    )
    assert "--cap-add" in cmd
    assert "ALL" in cmd
    assert "--tmpfs" in cmd
    assert "/run" in cmd
    assert "/var/run" in cmd
    assert "/project:/workspace" in cmd
    assert "cc-project-docker:/var/lib/docker" in cmd
    assert "127.0.0.1:8080:8080" in cmd


def test_build_engine_run_command_allows_ephemeral_storage() -> None:
    cmd = build_engine_run_command(
        ProxyConfig(storage="none"),
        "cc-test",
        Path("/project"),
        [],
    )
    assert "/var/lib/docker" not in " ".join(cmd)


def test_build_engine_run_command_includes_rosetta_and_platform() -> None:
    cmd = build_engine_run_command(
        ProxyConfig(rosetta=True, platform="linux/arm64"),
        "cc-test",
        Path("/project"),
        [],
    )
    assert "--rosetta" in cmd
    assert "--platform" in cmd
    assert "linux/arm64" in cmd


def test_resolve_docker_volume_uses_custom_name() -> None:
    assert (
        resolve_docker_volume(
            ProxyConfig(docker_volume="custom-docker-data"),
            Path("/project"),
        )
        == "custom-docker-data"
    )


def test_describe_storage_for_ephemeral_mode() -> None:
    assert describe_storage(ProxyConfig(storage="none"), Path("/project")) == "storage: none"


def test_describe_storage_for_missing_volume() -> None:
    with patch("container_compose_proxy.engine.volume_exists", return_value=False):
        assert (
            describe_storage(ProxyConfig(docker_volume="cc-data"), Path("/project"))
            == "storage: volume\nvolume: cc-data\nstate: not-found"
        )


def test_validate_running_engine_rejects_missing_ports() -> None:
    state = {
        "configuration": {
            "id": "cc-test",
            "mounts": [
                {"destination": "/workspace", "source": "/project"},
            ],
            "publishedPorts": [],
        }
    }
    with pytest.raises(ProxyError):
        validate_running_engine(state, Path("/project"), ["127.0.0.1:8080:8080"])


def test_validate_running_engine_rejects_missing_rosetta() -> None:
    state = {
        "configuration": {
            "id": "cc-test",
            "rosetta": False,
            "mounts": [
                {"destination": "/workspace", "source": "/project"},
            ],
            "publishedPorts": [],
        }
    }
    with pytest.raises(ProxyError):
        validate_running_engine(state, Path("/project"), [], ProxyConfig(rosetta=True))


def test_describe_engine_not_found() -> None:
    with patch("container_compose_proxy.engine.inspect_container", return_value=None):
        assert describe_engine("missing-engine") == "engine: missing-engine\nstate: not-found"
