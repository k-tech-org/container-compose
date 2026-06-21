from pathlib import Path
import tempfile

from container_compose_proxy.cli import (
    auto_publish_specs,
    compose_port_to_container_publish,
    normalize_publish_spec,
)
from container_compose_proxy.ports import ComposePort, parse_compose_ports


def test_simple_port_maps_host_port_to_dind_port() -> None:
    assert compose_port_to_container_publish("8080:80") == "127.0.0.1:8080:8080"


def test_host_ip_is_preserved() -> None:
    assert (
        compose_port_to_container_publish("0.0.0.0:18080:80/tcp")
        == "0.0.0.0:18080:18080"
    )


def test_manual_publish_defaults_loopback() -> None:
    assert normalize_publish_spec("18081:8080/tcp") == "127.0.0.1:18081:8080"


def test_auto_publish_reads_simple_ports_blocks() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        compose = Path(tmp) / "compose.yml"
        compose.write_text(
            """
services:
  web:
    image: nginx
    ports:
      - "8080:80"
      - '127.0.0.1:8443:443'
""",
            encoding="utf-8",
        )
        assert auto_publish_specs([compose]) == [
            "127.0.0.1:8080:8080",
            "127.0.0.1:8443:8443",
        ]


def test_auto_publish_reads_long_port_syntax() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        compose = Path(tmp) / "compose.yml"
        compose.write_text(
            """
services:
  web:
    image: nginx
    ports:
      - target: 80
        published: "8080"
        host_ip: 0.0.0.0
        protocol: tcp
      - target: 53
        published: "1053"
        protocol: udp
""",
            encoding="utf-8",
        )
        assert auto_publish_specs([compose]) == [
            "0.0.0.0:8080:8080",
            "127.0.0.1:1053:1053/udp",
        ]


def test_parse_compose_ports_ignores_comments_in_quotes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        compose = Path(tmp) / "compose.yml"
        compose.write_text(
            """
services:
  web:
    ports:
      - "8080:80" # public web
      - "127.0.0.1:9000:90#not-comment"
""",
            encoding="utf-8",
        )
        assert parse_compose_ports(compose) == [
            ComposePort(host_ip="127.0.0.1", published="8080", target="80"),
            ComposePort(
                host_ip="127.0.0.1",
                published="9000",
                target="90#not-comment",
            ),
        ]
