from __future__ import annotations

from pathlib import Path

from .config import WORKSPACE, default_compose_project_name
from .errors import ProxyError
from .mounts import compose_command
from .process import run


def run_compose(
    engine_name: str,
    project_dir: Path,
    compose_files: list[Path],
    compose_args: list[str],
) -> int:
    file_args: list[str] = []
    for compose_file in compose_files:
        file_args.extend(["-f", str(to_workspace_path(project_dir, compose_file))])
    project_name_args: list[str] = []
    if not has_compose_project_name(compose_args):
        project_name_args = ["--project-name", default_compose_project_name(project_dir)]
    cmd = [
        "container",
        "exec",
        "--workdir",
        str(WORKSPACE),
        engine_name,
        "docker",
        "compose",
        *project_name_args,
        *file_args,
        "--project-directory",
        str(WORKSPACE),
        *compose_args,
    ]
    try:
        return run(cmd, check=False, isolate_signals=True).returncode
    except KeyboardInterrupt:
        if is_foreground_up(compose_args):
            run(
                compose_stop_command(engine_name, project_name_args, file_args),
                check=False,
            )
        raise


def compose_stop_command(
    engine_name: str,
    project_name_args: list[str],
    file_args: list[str],
) -> list[str]:
    return [
        "container",
        "exec",
        "--workdir",
        str(WORKSPACE),
        engine_name,
        "docker",
        "compose",
        *project_name_args,
        *file_args,
        "--project-directory",
        str(WORKSPACE),
        "stop",
    ]


def is_foreground_up(compose_args: list[str]) -> bool:
    return compose_command(compose_args) == "up" and not any(
        arg in {"-d", "--detach"} or arg.startswith("--detach=") for arg in compose_args
    )


def has_compose_project_name(compose_args: list[str]) -> bool:
    return any(
        arg == "--project-name" or arg.startswith("--project-name=")
        for arg in compose_args
    )


def to_workspace_path(project_dir: Path, path: Path) -> Path:
    try:
        return WORKSPACE / path.resolve().relative_to(project_dir)
    except ValueError as exc:
        raise ProxyError(f"{path} is outside project directory {project_dir}") from exc
