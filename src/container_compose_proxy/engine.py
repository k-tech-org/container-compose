from __future__ import annotations

import json
from pathlib import Path
import time

from .config import (
    ProxyConfig,
    default_docker_volume_name,
)
from .errors import ProxyError
from .ports import format_published_port
from .process import run


def ensure_engine(
    config: ProxyConfig,
    engine_name: str,
    project_dir: Path,
    publishes: list[str],
) -> None:
    state = inspect_container(engine_name)
    if state and container_state(state) == "running":
        validate_running_engine(state, project_dir, publishes, config)
        wait_for_docker(engine_name)
        return
    if state:
        delete_engine(engine_name, check=False)

    ensure_storage(config, project_dir)
    run(build_engine_run_command(config, engine_name, project_dir, publishes))
    wait_for_docker(engine_name)


def start_engine(
    config: ProxyConfig,
    engine_name: str,
    project_dir: Path,
    publishes: list[str],
) -> None:
    ensure_engine(config, engine_name, project_dir, publishes)


def stop_engine(engine_name: str) -> None:
    state = inspect_container(engine_name)
    if not state:
        raise ProxyError(f"engine not found: {engine_name}")
    if container_state(state) != "running":
        return
    run(["container", "stop", engine_name])


def delete_engine(engine_name: str, *, check: bool = True) -> None:
    run(["container", "delete", engine_name], check=check)


def remove_engine(engine_name: str) -> None:
    state = inspect_container(engine_name)
    if not state:
        return
    if container_state(state) == "running":
        stop_engine(engine_name)
    delete_engine(engine_name)


def remove_engine_storage(config: ProxyConfig, project_dir: Path) -> None:
    docker_volume = resolve_docker_volume(config, project_dir)
    if docker_volume and volume_exists(docker_volume):
        run(["container", "volume", "delete", docker_volume])


def recreate_engine(
    config: ProxyConfig,
    engine_name: str,
    project_dir: Path,
    publishes: list[str],
) -> None:
    remove_engine(engine_name)
    ensure_engine(config, engine_name, project_dir, publishes)


def engine_logs(engine_name: str) -> int:
    return run(["container", "logs", engine_name], check=False).returncode


def build_engine_run_command(
    config: ProxyConfig,
    engine_name: str,
    project_dir: Path,
    publishes: list[str],
) -> list[str]:
    cmd = [
        "container",
        "run",
        "-d",
        "--name",
        engine_name,
        "--memory",
        config.memory,
        "--cpus",
        config.cpus,
        "--tmpfs",
        "/run",
        "--tmpfs",
        "/var/run",
        "--volume",
        f"{project_dir}:/workspace",
    ]
    if config.platform:
        cmd.extend(["--platform", config.platform])
    if config.rosetta:
        cmd.append("--rosetta")
    docker_volume = resolve_docker_volume(config, project_dir)
    if docker_volume:
        cmd.extend(["--volume", f"{docker_volume}:/var/lib/docker"])
    if config.cap_add:
        for cap in config.cap_add:
            cmd.extend(["--cap-add", cap])
    for publish in publishes:
        cmd.extend(["-p", publish])
    cmd.append(config.engine_image)
    return cmd


def ensure_storage(config: ProxyConfig, project_dir: Path) -> None:
    docker_volume = resolve_docker_volume(config, project_dir)
    if not docker_volume:
        return
    if volume_exists(docker_volume):
        return
    cmd = [
        "container",
        "volume",
        "create",
        "--label",
        "app=container-compose",
    ]
    if config.docker_volume_size:
        cmd.extend(["-s", config.docker_volume_size])
    cmd.append(docker_volume)
    run(cmd)


def resolve_docker_volume(config: ProxyConfig, project_dir: Path) -> str | None:
    if config.storage == "none":
        return None
    if config.storage != "volume":
        raise ProxyError(f"unsupported storage mode: {config.storage}")
    if config.docker_volume:
        return config.docker_volume
    return default_docker_volume_name(project_dir)


def volume_exists(name: str) -> bool:
    proc = run(["container", "volume", "inspect", name], check=False, capture=True)
    return proc.returncode == 0


def describe_storage(config: ProxyConfig, project_dir: Path) -> str:
    docker_volume = resolve_docker_volume(config, project_dir)
    if not docker_volume:
        return "storage: none"
    state = "exists" if volume_exists(docker_volume) else "not-found"
    return f"storage: volume\nvolume: {docker_volume}\nstate: {state}"


def inspect_container(name: str) -> dict | None:
    proc = run(["container", "inspect", name], check=False, capture=True)
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ProxyError(f"failed to parse container inspect output: {exc}") from exc
    if not data:
        return None
    return data[0]


def container_state(state: dict) -> str | None:
    status = state.get("status")
    if isinstance(status, str):
        return status
    if isinstance(status, dict):
        value = status.get("state")
        return str(value) if value is not None else None
    return None


def validate_running_engine(
    state: dict,
    project_dir: Path,
    publishes: list[str],
    expected: ProxyConfig | None = None,
) -> None:
    container_config = state.get("configuration", {})
    mounts = container_config.get("mounts", [])
    mounted = any(
        mount.get("destination") == "/workspace"
        and Path(str(mount.get("source", ""))).resolve() == project_dir
        for mount in mounts
    )
    if not mounted:
        raise ProxyError(
            "engine container is already running with a different /workspace mount; "
            f"stop/delete {container_config.get('id', 'the engine')} or use --engine-name"
        )

    if expected and expected.rosetta and not container_config.get("rosetta"):
        raise ProxyError(
            "engine container is already running without Rosetta enabled. "
            "Recreate the engine or pass a different --engine-name."
        )

    existing = {
        format_published_port(port)
        for port in container_config.get("publishedPorts", [])
        if format_published_port(port)
    }
    missing = [publish for publish in publishes if publish not in existing]
    if missing:
        raise ProxyError(
            "engine container is already running without required published ports: "
            + ", ".join(missing)
            + ". Recreate the engine or pass a different --engine-name."
        )


def wait_for_docker(engine_name: str) -> None:
    last_output = ""
    for _ in range(60):
        proc = run(
            ["container", "exec", engine_name, "docker", "version"],
            check=False,
            capture=True,
        )
        if proc.returncode == 0:
            return
        last_output = (proc.stderr or proc.stdout).strip()
        time.sleep(1)
    logs = run(["container", "logs", engine_name], check=False, capture=True)
    detail = logs.stdout.strip() or logs.stderr.strip() or last_output
    raise ProxyError(f"Docker daemon did not become ready in {engine_name}: {detail}")


def describe_engine(engine_name: str) -> str:
    state = inspect_container(engine_name)
    if not state:
        return f"engine: {engine_name}\nstate: not-found"

    config = state.get("configuration", {})
    lines = [
        f"engine: {engine_name}",
        f"state: {container_state(state) or 'unknown'}",
        f"image: {config.get('image', {}).get('reference', 'unknown')}",
    ]

    workspace = next(
        (
            mount.get("source")
            for mount in config.get("mounts", [])
            if mount.get("destination") == "/workspace"
        ),
        None,
    )
    if workspace:
        lines.append(f"workspace: {workspace}")

    docker_storage = next(
        (
            mount.get("source")
            for mount in config.get("mounts", [])
            if mount.get("destination") == "/var/lib/docker"
        ),
        None,
    )
    if docker_storage:
        lines.append(f"docker-storage: {docker_storage}")

    ports = [
        formatted
        for port in config.get("publishedPorts", [])
        if (formatted := format_published_port(port))
    ]
    if ports:
        lines.append("ports:")
        lines.extend(f"  {port}" for port in ports)

    caps = config.get("capAdd") or []
    if caps:
        lines.append("capabilities:")
        lines.extend(f"  {cap}" for cap in caps)
    if config.get("rosetta"):
        lines.append("rosetta: enabled")
    return "\n".join(lines)
