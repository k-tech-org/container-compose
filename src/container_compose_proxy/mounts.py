from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .config import WORKSPACE
from .errors import ProxyError


COMPOSE_COMMANDS_WITH_MOUNTS = {"up", "run", "create"}
OPTIONS_WITH_VALUES = {
    "-f",
    "--file",
    "-p",
    "--project-name",
    "--project-directory",
    "--profile",
    "--env-file",
    "--ansi",
    "--compatibility",
    "--parallel",
    "--progress",
}


@dataclass(frozen=True)
class BindMountSource:
    source: str
    compose_file: Path
    reason: str


def validate_compose_bind_mounts(compose_files: list[Path], project_dir: Path) -> None:
    missing: list[str] = []
    outside: list[str] = []
    absolute: list[str] = []

    for mount in collect_bind_mount_sources(compose_files):
        resolved = resolve_bind_source(mount.source, mount.compose_file, project_dir)
        if resolved is None:
            absolute.append(f"{mount.compose_file}: {mount.source} ({mount.reason})")
            continue
        if not is_relative_to(resolved, project_dir):
            outside.append(f"{mount.compose_file}: {mount.source} -> {resolved}")
            continue
        if not resolved.exists():
            missing.append(f"{mount.compose_file}: {mount.source} -> {resolved}")

    if missing or outside or absolute:
        details: list[str] = []
        if missing:
            details.append("missing bind sources:\n  " + "\n  ".join(missing))
        if outside:
            details.append("bind sources outside project directory:\n  " + "\n  ".join(outside))
        if absolute:
            details.append(
                "absolute bind sources are not mounted into dind; use relative paths "
                f"under the project directory or {WORKSPACE} paths:\n  "
                + "\n  ".join(absolute)
            )
        raise ProxyError("\n".join(details))


def collect_bind_mount_sources(compose_files: list[Path]) -> list[BindMountSource]:
    mounts: list[BindMountSource] = []
    for compose_file in compose_files:
        if not compose_file.exists():
            continue
        data = yaml.safe_load(compose_file.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            continue
        services = data.get("services") or {}
        if isinstance(services, dict):
            mounts.extend(collect_service_bind_mounts(compose_file, services))
        volumes = data.get("volumes") or {}
        if isinstance(volumes, dict):
            mounts.extend(collect_top_level_bind_volumes(compose_file, volumes))
    return mounts


def collect_service_bind_mounts(
    compose_file: Path,
    services: dict[str, Any],
) -> list[BindMountSource]:
    mounts: list[BindMountSource] = []
    for service in services.values():
        if not isinstance(service, dict):
            continue
        volumes = service.get("volumes") or []
        if not isinstance(volumes, list):
            continue
        for volume in volumes:
            source = service_volume_bind_source(volume)
            if source:
                mounts.append(BindMountSource(source, compose_file, "service volume"))
    return mounts


def collect_top_level_bind_volumes(
    compose_file: Path,
    volumes: dict[str, Any],
) -> list[BindMountSource]:
    mounts: list[BindMountSource] = []
    for volume in volumes.values():
        if not isinstance(volume, dict):
            continue
        driver_opts = volume.get("driver_opts") or volume.get("driver-opts") or {}
        if not isinstance(driver_opts, dict):
            continue
        device = driver_opts.get("device")
        if not isinstance(device, str) or not is_path_like_source(device):
            continue
        opt_type = str(driver_opts.get("type", ""))
        options = str(driver_opts.get("o", ""))
        if opt_type == "none" or "bind" in options.split(","):
            mounts.append(BindMountSource(device, compose_file, "top-level bind volume"))
    return mounts


def service_volume_bind_source(volume: Any) -> str | None:
    if isinstance(volume, str):
        source = split_short_volume_source(volume)
        if source and is_path_like_source(source):
            return source
        return None
    if not isinstance(volume, dict):
        return None
    mount_type = str(volume.get("type", ""))
    source = volume.get("source") or volume.get("src")
    if not isinstance(source, str) or not source:
        return None
    if mount_type == "bind" or is_path_like_source(source):
        return source
    return None


def split_short_volume_source(spec: str) -> str | None:
    parts = spec.split(":")
    if len(parts) < 2:
        return None
    source = parts[0]
    return source or None


def is_path_like_source(source: str) -> bool:
    return (
        source.startswith(".")
        or source.startswith("/")
        or source.startswith("~")
        or "/" in source
    )


def resolve_bind_source(source: str, compose_file: Path, project_dir: Path) -> Path | None:
    if source.startswith(str(WORKSPACE)):
        return project_dir / Path(source).relative_to(WORKSPACE)
    path = Path(source).expanduser()
    if path.is_absolute():
        return None
    return (compose_file.parent / path).resolve()


def should_validate_mounts(compose_args: list[str]) -> bool:
    command = compose_command(compose_args)
    return command in COMPOSE_COMMANDS_WITH_MOUNTS


def compose_command(compose_args: list[str]) -> str | None:
    i = 0
    while i < len(compose_args):
        arg = compose_args[i]
        if arg == "--":
            return compose_args[i + 1] if i + 1 < len(compose_args) else None
        if arg.startswith("--") and "=" in arg:
            option = arg.split("=", 1)[0]
            if option in OPTIONS_WITH_VALUES:
                i += 1
                continue
        if arg in OPTIONS_WITH_VALUES:
            i += 2
            continue
        if arg.startswith("-"):
            i += 1
            continue
        return arg
    return None


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
