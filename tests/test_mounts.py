from pathlib import Path

import pytest

from container_compose_proxy.errors import ProxyError
from container_compose_proxy.mounts import (
    collect_bind_mount_sources,
    compose_command,
    should_validate_mounts,
    validate_compose_bind_mounts,
)


def test_collect_bind_mount_sources_ignores_named_volumes(tmp_path: Path) -> None:
    compose = tmp_path / "compose.yml"
    compose.write_text(
        """
services:
  app:
    image: busybox
    volumes:
      - app-data:/data
volumes:
  app-data:
""",
        encoding="utf-8",
    )

    assert collect_bind_mount_sources([compose]) == []


def test_validate_compose_bind_mounts_accepts_existing_relative_path(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    compose = tmp_path / "compose.yml"
    compose.write_text(
        """
services:
  app:
    image: busybox
    volumes:
      - ./data:/data
""",
        encoding="utf-8",
    )

    validate_compose_bind_mounts([compose], tmp_path)


def test_validate_compose_bind_mounts_rejects_missing_relative_path(tmp_path: Path) -> None:
    compose = tmp_path / "compose.yml"
    compose.write_text(
        """
services:
  app:
    image: busybox
    volumes:
      - ./missing:/data
""",
        encoding="utf-8",
    )

    with pytest.raises(ProxyError, match="missing bind sources"):
        validate_compose_bind_mounts([compose], tmp_path)


def test_validate_compose_bind_mounts_rejects_paths_outside_project(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    compose = tmp_path / "compose.yml"
    compose.write_text(
        """
services:
  app:
    image: busybox
    volumes:
      - ../outside:/data
""".replace("../outside", f"../{outside.name}"),
        encoding="utf-8",
    )

    with pytest.raises(ProxyError, match="outside project directory"):
        validate_compose_bind_mounts([compose], tmp_path)


def test_validate_compose_bind_mounts_rejects_absolute_host_path(tmp_path: Path) -> None:
    compose = tmp_path / "compose.yml"
    compose.write_text(
        """
services:
  app:
    image: busybox
    volumes:
      - /tmp/data:/data
""",
        encoding="utf-8",
    )

    with pytest.raises(ProxyError, match="absolute bind sources"):
        validate_compose_bind_mounts([compose], tmp_path)


def test_validate_compose_bind_mounts_checks_top_level_bind_volume(tmp_path: Path) -> None:
    compose = tmp_path / "compose.yml"
    compose.write_text(
        """
services:
  app:
    image: busybox
    volumes:
      - app-data:/data
volumes:
  app-data:
    driver_opts:
      type: none
      o: bind
      device: ./missing
""",
        encoding="utf-8",
    )

    with pytest.raises(ProxyError, match="missing bind sources"):
        validate_compose_bind_mounts([compose], tmp_path)


def test_compose_command_skips_global_options() -> None:
    assert compose_command(["--profile", "checks", "run", "--rm", "app"]) == "run"
    assert should_validate_mounts(["--profile", "checks", "run", "--rm", "app"])
    assert not should_validate_mounts(["--profile", "checks", "down"])
