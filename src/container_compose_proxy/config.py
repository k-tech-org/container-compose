from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
import re


DEFAULT_ENGINE_IMAGE = "docker:28-dind"
DEFAULT_MEMORY = "4g"
DEFAULT_CPUS = "4"
DEFAULT_CAP_ADD = ["ALL"]
DEFAULT_STORAGE = "volume"
WORKSPACE = Path("/workspace")
DEFAULT_COMPOSE_FILES = (
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",
)
MAX_GENERATED_NAME_LENGTH = 63


@dataclass
class ProxyConfig:
    compose_files: list[Path] = field(default_factory=list)
    compose_args: list[str] = field(default_factory=list)
    project_directory: Path | None = None
    engine_image: str = DEFAULT_ENGINE_IMAGE
    engine_name: str | None = None
    memory: str = DEFAULT_MEMORY
    cpus: str = DEFAULT_CPUS
    cap_add: list[str] | None = field(default_factory=lambda: list(DEFAULT_CAP_ADD))
    storage: str = DEFAULT_STORAGE
    docker_volume: str | None = None
    docker_volume_size: str | None = None
    rosetta: bool = False
    platform: str | None = None
    publishes: list[str] = field(default_factory=list)
    auto_publish: bool = True
    verbose: bool = False


def resolve_project_directory(config: ProxyConfig) -> Path:
    if config.project_directory is not None:
        return config.project_directory.expanduser().resolve()
    if config.compose_files:
        return config.compose_files[0].expanduser().resolve().parent
    return Path.cwd().resolve()


def resolve_compose_files(config: ProxyConfig, project_dir: Path) -> list[Path]:
    if config.compose_files:
        return [path.expanduser().resolve() for path in config.compose_files]
    for name in DEFAULT_COMPOSE_FILES:
        candidate = project_dir / name
        if candidate.exists():
            return [candidate]
    return []


def default_engine_name(project_dir: Path) -> str:
    return generated_project_name(project_dir)


def default_docker_volume_name(project_dir: Path) -> str:
    return f"{generated_project_name(project_dir)}-docker"


def default_compose_project_name(project_dir: Path) -> str:
    return slugify(project_dir.name).replace(".", "-") or "project"


def generated_project_name(project_dir: Path) -> str:
    slug = slugify(project_dir.name) or "project"
    base = f"cc-{slug}"
    if len(base) <= MAX_GENERATED_NAME_LENGTH:
        return base
    digest = project_digest(project_dir)
    keep = MAX_GENERATED_NAME_LENGTH - len("cc-") - len(digest) - 1
    return f"cc-{slug[:keep].rstrip('-')}-{digest}"


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-_.")
    return slug


def project_digest(project_dir: Path) -> str:
    return hashlib.sha1(str(project_dir.resolve()).encode("utf-8")).hexdigest()[:8]
