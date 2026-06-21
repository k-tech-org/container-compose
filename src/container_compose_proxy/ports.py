from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


KEY_VALUE = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(?P<value>.*)$")


@dataclass(frozen=True)
class ComposePort:
    host_ip: str | None
    published: str
    target: str | None = None
    protocol: str = "tcp"


def auto_publish_specs(compose_files: list[Path]) -> list[str]:
    publishes: list[str] = []
    for compose_file in compose_files:
        if not compose_file.exists():
            continue
        for port in parse_compose_ports(compose_file):
            publishes.append(compose_port_to_publish(port))
    return publishes


def parse_compose_ports(compose_file: Path) -> list[ComposePort]:
    lines = compose_file.read_text(encoding="utf-8").splitlines()
    ports: list[ComposePort] = []
    in_ports = False
    ports_indent = 0
    current_long: dict[str, str] | None = None

    def flush_current() -> None:
        nonlocal current_long
        if current_long is not None:
            port = long_port_to_model(current_long)
            if port:
                ports.append(port)
            current_long = None

    for raw_line in lines:
        line = strip_comment(raw_line).rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip(" "))
        if stripped == "ports:":
            flush_current()
            in_ports = True
            ports_indent = indent
            continue
        if in_ports and indent <= ports_indent and not stripped.startswith("-"):
            flush_current()
            in_ports = False
        if not in_ports:
            continue

        if stripped.startswith("-"):
            flush_current()
            item = stripped[1:].strip()
            if not item:
                current_long = {}
                continue
            match = KEY_VALUE.match(item)
            if match:
                current_long = {
                    normalize_key(match.group("key")): clean_scalar(match.group("value"))
                }
                continue
            port = short_port_to_model(clean_scalar(item))
            if port:
                ports.append(port)
            continue

        if current_long is not None and indent > ports_indent:
            match = KEY_VALUE.match(stripped)
            if match:
                current_long[normalize_key(match.group("key"))] = clean_scalar(
                    match.group("value")
                )
    flush_current()
    return ports


def compose_port_to_container_publish(spec: str) -> str | None:
    port = short_port_to_model(spec)
    if not port:
        return None
    return compose_port_to_publish(port)


def short_port_to_model(spec: str) -> ComposePort | None:
    protocol = "tcp"
    if "/" in spec:
        spec, protocol = spec.rsplit("/", 1)
    parts = spec.rsplit(":", 2)
    if len(parts) == 2:
        host_ip = "127.0.0.1"
        host_port, container_port = parts
    elif len(parts) == 3:
        host_ip, host_port, container_port = parts
        host_ip = host_ip.strip("[]") if host_ip.startswith("[") else host_ip
    else:
        return None
    if not host_port.isdigit():
        return None
    return ComposePort(
        host_ip=host_ip,
        published=host_port,
        target=container_port,
        protocol=protocol,
    )


def long_port_to_model(values: dict[str, str]) -> ComposePort | None:
    published = values.get("published")
    if not published:
        return None
    protocol = values.get("protocol", "tcp")
    return ComposePort(
        host_ip=values.get("host_ip") or values.get("hostip") or "127.0.0.1",
        published=published,
        target=values.get("target"),
        protocol=protocol,
    )


def compose_port_to_publish(port: ComposePort) -> str:
    suffix = "" if port.protocol == "tcp" else f"/{port.protocol}"
    host_ip = port.host_ip or "127.0.0.1"
    return f"{host_ip}:{port.published}:{port.published}{suffix}"


def normalize_publish_spec(spec: str) -> str:
    proto = ""
    if "/" in spec:
        spec, proto = spec.rsplit("/", 1)
        proto = "" if proto == "tcp" else f"/{proto}"
    parts = spec.rsplit(":", 2)
    if len(parts) == 1:
        return f"127.0.0.1:{parts[0]}:{parts[0]}{proto}"
    if len(parts) == 2:
        return f"127.0.0.1:{parts[0]}:{parts[1]}{proto}"
    return f"{parts[0]}:{parts[1]}:{parts[2]}{proto}"


def strip_comment(line: str) -> str:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char in {"'", '"'}:
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
            continue
        if char == "#" and quote is None:
            return line[:index]
    return line


def clean_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def normalize_key(key: str) -> str:
    return key.replace("-", "_")


def format_published_port(port: dict) -> str | None:
    host_address = port.get("hostAddress") or "127.0.0.1"
    host_port = port.get("hostPort")
    container_port = port.get("containerPort")
    proto = port.get("proto") or "tcp"
    if host_port is None or container_port is None:
        return None
    suffix = "" if proto == "tcp" else f"/{proto}"
    return f"{host_address}:{host_port}:{container_port}{suffix}"


def dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
