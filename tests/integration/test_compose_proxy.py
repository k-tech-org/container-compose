from __future__ import annotations

import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import uuid
from urllib.request import urlopen

import pytest


ROOT_DIR = Path(__file__).resolve().parents[2]
FIXTURES_DIR = ROOT_DIR / "tests" / "fixtures"


pytestmark = pytest.mark.integration


def run_command(
    args: list[str],
    *,
    check: bool = True,
    cwd: Path = ROOT_DIR,
    timeout: int = 180,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT_DIR / "src")
    try:
        return subprocess.run(
            args,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=check,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as exc:
        if is_docker_hub_rate_limited(exc.output):
            pytest.skip("Docker Hub unauthenticated pull rate limit reached")
        raise


def is_docker_hub_rate_limited(output: str | None) -> bool:
    if not output:
        return False
    return "toomanyrequests" in output and "unauthenticated pull rate limit" in output


def run_proxy(
    *args: str,
    cwd: Path = ROOT_DIR,
    timeout: int = 180,
) -> subprocess.CompletedProcess[str]:
    return run_command(
        ["container-compose", *args],
        cwd=cwd,
        timeout=timeout,
    )


def run_container(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run_command(["container", *args], check=check)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def fetch_text(port: int) -> str:
    with urlopen(f"http://127.0.0.1:{port}", timeout=5) as response:
        return response.read().decode("utf-8")


def wait_until(assertion, *, timeout: int = 60) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            assertion()
            return
        except Exception as exc:  # noqa: BLE001 - preserve last integration failure
            last_error = exc
            time.sleep(1)
    if last_error is not None:
        raise last_error
    raise AssertionError("condition was not met before timeout")


@pytest.fixture(scope="module", autouse=True)
def require_container_cli() -> None:
    if shutil.which("container") is None:
        pytest.skip("Apple container CLI is not installed")


@pytest.fixture(scope="module")
def shared_docker_volume():
    suffix = uuid.uuid4().hex[:10]
    docker_volume = f"cc-compose-test-{suffix}-docker"
    yield docker_volume
    run_container("volume", "delete", docker_volume, check=False)


@pytest.fixture()
def engine_resources(shared_docker_volume):
    suffix = uuid.uuid4().hex[:10]
    engine_name = f"cc-compose-test-{suffix}"
    project_dir: Path | None = None

    def configure(path: Path) -> tuple[str, str, Path]:
        nonlocal project_dir
        project_dir = path
        return engine_name, shared_docker_volume, path

    yield configure

    if project_dir is not None:
        run_command(
            [
                sys.executable,
                "-m",
                "container_compose_proxy",
                "--engine-name",
                engine_name,
                "--docker-volume",
                shared_docker_volume,
                "--project-directory",
                str(project_dir),
                "engine",
                "rm",
            ],
            check=False,
            timeout=120,
        )


def test_basic_compose_lifecycle_and_persistent_engine_storage(engine_resources) -> None:
    project_dir = FIXTURES_DIR / "basic"
    engine_name, docker_volume, _ = engine_resources(project_dir)
    host_port = free_port()
    common_args = [
        "--engine-name",
        engine_name,
        "--docker-volume",
        docker_volume,
        "--no-auto-publish",
        "--publish",
        f"127.0.0.1:{host_port}:8080",
        "-f",
        str(project_dir / "compose.yml"),
    ]

    run_proxy(*common_args, "up", "-d")
    wait_until(lambda: assert_contains(fetch_text(host_port), "container-compose test service"))

    run_proxy(*common_args, "down")
    run_proxy(
        "--engine-name",
        engine_name,
        "--docker-volume",
        docker_volume,
        "-f",
        str(project_dir / "compose.yml"),
        "engine",
        "rm",
    )
    run_proxy(
        "--engine-name",
        engine_name,
        "--docker-volume",
        docker_volume,
        "--no-auto-publish",
        "--publish",
        f"127.0.0.1:{host_port}:8080",
        "-f",
        str(project_dir / "compose.yml"),
        "engine",
        "start",
    )

    storage = run_proxy(
        "--engine-name",
        engine_name,
        "--docker-volume",
        docker_volume,
        "-f",
        str(project_dir / "compose.yml"),
        "engine",
        "storage",
    )
    assert_contains(storage.stdout, f"volume: {docker_volume}")
    run_container("exec", engine_name, "docker", "image", "inspect", "nginx:1.27-alpine")


def test_complex_compose_features_and_rosetta(engine_resources) -> None:
    project_dir = FIXTURES_DIR / "complex"
    engine_name, docker_volume, _ = engine_resources(project_dir)
    host_port = free_port()
    common_args = [
        "--engine-name",
        engine_name,
        "--docker-volume",
        docker_volume,
        "--rosetta",
        "--no-auto-publish",
        "--publish",
        f"127.0.0.1:{host_port}:18087",
    ]

    run_proxy(*common_args, "build", "app", cwd=project_dir, timeout=300)
    run_proxy(*common_args, "up", "-d", "app", "backend", cwd=project_dir, timeout=240)

    def assert_backend_healthy() -> None:
        result = run_container(
            "exec",
            engine_name,
            "docker",
            "inspect",
            "-f",
            "{{.State.Health.Status}}",
            "complex-backend-1",
        )
        assert result.stdout.strip() == "healthy"

    wait_until(assert_backend_healthy, timeout=90)
    wait_until(lambda: assert_contains(fetch_text(host_port), "Built by Docker Compose"))

    run_proxy(*common_args, "up", "writer", cwd=project_dir, timeout=180)
    run_container("exec", engine_name, "docker", "volume", "inspect", "complex_app-data")
    run_container(
        "exec",
        engine_name,
        "docker",
        "run",
        "--rm",
        "-v",
        "complex_app-data:/data",
        "nginx:1.27-alpine",
        "grep",
        "-q",
        "named-volume-ok",
        "/data/result.txt",
    )

    run_proxy(
        *common_args,
        "--profile",
        "checks",
        "run",
        "--rm",
        "dnscheck",
        cwd=project_dir,
        timeout=180,
    )
    run_proxy(
        *common_args,
        "--profile",
        "checks",
        "run",
        "--rm",
        "featurecheck",
        cwd=project_dir,
        timeout=180,
    )
    run_proxy(
        *common_args,
        "--profile",
        "amd64",
        "run",
        "--rm",
        "amd64check",
        cwd=project_dir,
        timeout=240,
    )
    run_proxy(*common_args, "down", "--volumes", cwd=project_dir, timeout=180)


def assert_contains(text: str, expected: str) -> None:
    assert expected in text
