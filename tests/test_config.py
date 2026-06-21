from pathlib import Path
import tempfile

from container_compose_proxy.config import (
    ProxyConfig,
    default_compose_project_name,
    default_docker_volume_name,
    default_engine_name,
    resolve_compose_files,
    resolve_project_directory,
    slugify,
)


def test_default_engine_name_is_stable_and_namespaced() -> None:
    assert default_engine_name(Path("/tmp/sample_app")) == "cc-sample_app"
    assert default_engine_name(Path("/tmp/My Project")) == "cc-my-project"
    assert default_engine_name(Path("/tmp/sample_app")) == default_engine_name(
        Path("/tmp/sample_app")
    )


def test_default_docker_volume_name_matches_readable_engine_name() -> None:
    assert (
        default_docker_volume_name(Path("/tmp/sample_app"))
        == "cc-sample_app-docker"
    )


def test_default_compose_project_name_matches_host_project_directory() -> None:
    assert default_compose_project_name(Path("/tmp/sample_app")) == "sample_app"
    assert default_compose_project_name(Path("/tmp/My Project")) == "my-project"


def test_default_engine_name_hashes_only_when_too_long() -> None:
    name = default_engine_name(Path("/tmp/" + "a" * 80))
    assert name.startswith("cc-")
    assert len(name) <= 63


def test_slugify_removes_unsupported_name_characters() -> None:
    assert slugify(" My Project!! ") == "my-project"


def test_project_directory_defaults_to_first_compose_file_parent() -> None:
    config = ProxyConfig(compose_files=[Path("tests/fixtures/basic/compose.yml")])
    assert resolve_project_directory(config) == Path("tests/fixtures/basic").resolve()


def test_resolve_compose_files_finds_default_name() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project_dir = Path(tmp)
        compose_file = project_dir / "compose.yml"
        compose_file.write_text("services: {}\n", encoding="utf-8")
        assert resolve_compose_files(ProxyConfig(), project_dir) == [compose_file]
