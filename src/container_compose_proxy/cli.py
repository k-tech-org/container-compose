from __future__ import annotations

from pathlib import Path
import sys

from .compose import run_compose, to_workspace_path
from .config import (
    DEFAULT_CAP_ADD,
    DEFAULT_CPUS,
    DEFAULT_ENGINE_IMAGE,
    DEFAULT_MEMORY,
    DEFAULT_STORAGE,
    ProxyConfig,
    default_docker_volume_name,
    default_engine_name,
    resolve_compose_files,
    resolve_project_directory,
)
from .engine import (
    build_engine_run_command,
    container_state,
    describe_engine,
    describe_storage,
    ensure_engine,
    engine_logs,
    format_published_port,
    recreate_engine,
    resolve_docker_volume,
    remove_engine,
    remove_engine_storage,
    start_engine,
    stop_engine,
    validate_running_engine,
    wait_for_docker,
)
from .errors import ProxyError
from .ports import (
    auto_publish_specs,
    compose_port_to_container_publish,
    dedupe,
    normalize_publish_spec,
)
from .mounts import should_validate_mounts, validate_compose_bind_mounts


ENGINE_ACTIONS = {
    "start",
    "status",
    "stop",
    "rm",
    "remove",
    "recreate",
    "logs",
    "storage",
    "prune-storage",
}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        config = parse_args(argv)
        project_dir = resolve_project_directory(config)
        compose_files = resolve_compose_files(config, project_dir)
        engine_name = config.engine_name or default_engine_name(project_dir)
        publishes = collect_publishes(config, compose_files)

        if config.compose_args and config.compose_args[0] == "engine":
            return run_engine_command(config, engine_name, project_dir, publishes)

        if not config.compose_args:
            raise ProxyError(
                "compose command required. For example: "
                "container-compose -f docker-compose.yml up -d"
            )

        if should_validate_mounts(config.compose_args):
            validate_compose_bind_mounts(compose_files, project_dir)
        ensure_engine(config, engine_name, project_dir, publishes)
        return run_compose(engine_name, project_dir, compose_files, config.compose_args)
    except ProxyError as exc:
        print(f"container-compose: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


def parse_args(argv: list[str]) -> ProxyConfig:
    config = ProxyConfig()
    passthrough = False
    i = 0
    while i < len(argv):
        arg = argv[i]
        if passthrough:
            config.compose_args.append(arg)
            i += 1
            continue
        if arg == "--":
            passthrough = True
            i += 1
            continue
        if arg in ("-f", "--file"):
            value = require_value(argv, i, arg)
            config.compose_files.append(Path(value))
            i += 2
            continue
        if arg.startswith("--file="):
            config.compose_files.append(Path(arg.split("=", 1)[1]))
            i += 1
            continue
        if arg == "--project-directory":
            value = require_value(argv, i, arg)
            config.project_directory = Path(value)
            i += 2
            continue
        if arg.startswith("--project-directory="):
            config.project_directory = Path(arg.split("=", 1)[1])
            i += 1
            continue
        if arg == "--engine-image":
            config.engine_image = require_value(argv, i, arg)
            i += 2
            continue
        if arg.startswith("--engine-image="):
            config.engine_image = arg.split("=", 1)[1]
            i += 1
            continue
        if arg == "--engine-name":
            config.engine_name = require_value(argv, i, arg)
            i += 2
            continue
        if arg.startswith("--engine-name="):
            config.engine_name = arg.split("=", 1)[1]
            i += 1
            continue
        if arg == "--memory":
            config.memory = require_value(argv, i, arg)
            i += 2
            continue
        if arg.startswith("--memory="):
            config.memory = arg.split("=", 1)[1]
            i += 1
            continue
        if arg == "--cpus":
            config.cpus = require_value(argv, i, arg)
            i += 2
            continue
        if arg.startswith("--cpus="):
            config.cpus = arg.split("=", 1)[1]
            i += 1
            continue
        if arg == "--cap-add":
            if config.cap_add is None:
                config.cap_add = []
            config.cap_add.append(require_value(argv, i, arg))
            i += 2
            continue
        if arg.startswith("--cap-add="):
            if config.cap_add is None:
                config.cap_add = []
            config.cap_add.append(arg.split("=", 1)[1])
            i += 1
            continue
        if arg == "--no-cap-add":
            config.cap_add = None
            i += 1
            continue
        if arg == "--storage":
            config.storage = require_value(argv, i, arg)
            i += 2
            continue
        if arg.startswith("--storage="):
            config.storage = arg.split("=", 1)[1]
            i += 1
            continue
        if arg == "--docker-volume":
            config.docker_volume = require_value(argv, i, arg)
            i += 2
            continue
        if arg.startswith("--docker-volume="):
            config.docker_volume = arg.split("=", 1)[1]
            i += 1
            continue
        if arg == "--docker-volume-size":
            config.docker_volume_size = require_value(argv, i, arg)
            i += 2
            continue
        if arg.startswith("--docker-volume-size="):
            config.docker_volume_size = arg.split("=", 1)[1]
            i += 1
            continue
        if arg == "--rosetta":
            config.rosetta = True
            i += 1
            continue
        if arg == "--platform":
            config.platform = require_value(argv, i, arg)
            i += 2
            continue
        if arg.startswith("--platform="):
            config.platform = arg.split("=", 1)[1]
            i += 1
            continue
        if arg in ("-p", "--publish"):
            config.publishes.append(normalize_publish_spec(require_value(argv, i, arg)))
            i += 2
            continue
        if arg.startswith("--publish="):
            config.publishes.append(normalize_publish_spec(arg.split("=", 1)[1]))
            i += 1
            continue
        if arg == "--no-auto-publish":
            config.auto_publish = False
            i += 1
            continue
        if arg == "--verbose-proxy":
            config.verbose = True
            i += 1
            continue
        if arg in ("-h", "--help") and not config.compose_args:
            print_help()
            raise SystemExit(0)
        config.compose_args.append(arg)
        i += 1
    return config


def collect_publishes(config: ProxyConfig, compose_files: list[Path]) -> list[str]:
    publishes = list(config.publishes)
    if config.auto_publish:
        publishes.extend(auto_publish_specs(compose_files))
    return dedupe(publishes)


def run_engine_command(
    config: ProxyConfig,
    engine_name: str,
    project_dir: Path,
    publishes: list[str],
) -> int:
    if len(config.compose_args) < 2:
        raise ProxyError(
            "engine requires an action: start, status, stop, rm, recreate, logs, "
            "storage, prune-storage"
        )
    action = config.compose_args[1]
    if action not in ENGINE_ACTIONS:
        raise ProxyError(f"unknown engine action: {action}")

    if action == "start":
        start_engine(config, engine_name, project_dir, publishes)
        print(describe_engine(engine_name))
        return 0
    if action == "status":
        print(describe_engine(engine_name))
        return 0
    if action == "stop":
        stop_engine(engine_name)
        print(describe_engine(engine_name))
        return 0
    if action in {"rm", "remove"}:
        remove_engine(engine_name)
        print(f"removed engine: {engine_name}")
        return 0
    if action == "recreate":
        recreate_engine(config, engine_name, project_dir, publishes)
        print(describe_engine(engine_name))
        return 0
    if action == "logs":
        return engine_logs(engine_name)
    if action == "storage":
        print(describe_storage(config, project_dir))
        return 0
    if action == "prune-storage":
        remove_engine(engine_name)
        remove_engine_storage(config, project_dir)
        print(f"removed engine storage for: {engine_name}")
        return 0
    raise ProxyError(f"unhandled engine action: {action}")


def require_value(argv: list[str], index: int, flag: str) -> str:
    if index + 1 >= len(argv):
        raise ProxyError(f"{flag} requires a value")
    return argv[index + 1]


def print_help() -> None:
    print(
        f"""Usage: container-compose [proxy options] [-f COMPOSE_FILE] [compose args...]
       container-compose [proxy options] engine <start|status|stop|rm|recreate|logs|storage|prune-storage>

Proxy options:
  --engine-image IMAGE       dind image to run (default: {DEFAULT_ENGINE_IMAGE})
  --engine-name NAME         Apple container name for the project engine
  --memory SIZE              engine VM memory (default: {DEFAULT_MEMORY})
  --cpus N                   engine VM CPUs (default: {DEFAULT_CPUS})
  --cap-add CAP              Linux capability for dind (default: {",".join(DEFAULT_CAP_ADD)})
  --no-cap-add               do not request extra Linux capabilities
  --storage MODE             Docker data storage: volume or none (default: {DEFAULT_STORAGE})
  --docker-volume NAME       Apple container volume for /var/lib/docker
  --docker-volume-size SIZE  create the Docker data volume with a size limit
  --rosetta                  enable Rosetta in the dind engine
  --platform PLATFORM        Apple container platform for the dind engine
  -p, --publish SPEC         publish dind VM port to macOS host
  --no-auto-publish          do not scan simple compose ports
  --verbose-proxy            reserved for debugging

Examples:
  container-compose up -d
  container-compose ps
  container-compose down
  container-compose engine status
  container-compose engine storage
"""
    )


__all__ = [
    "ProxyConfig",
    "ProxyError",
    "auto_publish_specs",
    "build_engine_run_command",
    "compose_port_to_container_publish",
    "container_state",
    "default_engine_name",
    "default_docker_volume_name",
    "format_published_port",
    "main",
    "normalize_publish_spec",
    "parse_args",
    "resolve_docker_volume",
    "resolve_compose_files",
    "resolve_project_directory",
    "run_compose",
    "to_workspace_path",
    "validate_running_engine",
    "wait_for_docker",
]
