# container-compose

Docker Compose compatibility wrapper for Apple's `container` CLI.

`container-compose` starts a project-scoped Docker-in-Docker engine with Apple
`container`, mounts the Compose project into it, and proxies `docker compose`
commands through that engine.

## Requirements

- macOS with Apple `container` CLI 1.0+
- Network access for the first `docker:28-dind` pull and Compose image pulls

Start Apple `container` before using Compose projects:

```bash
container system start
```

## Installation

Install with Homebrew:

```bash
brew tap k-tech-org/container-compose
brew install k-tech-org/container-compose/container-compose
```

## Usage

Run from a directory containing `compose.yml` or `docker-compose.yml`:

```bash
container-compose up -d
container-compose ps
container-compose logs
container-compose down
```

Select a Compose file explicitly:

```bash
container-compose -f docker-compose.yml up -d
container-compose -f path/to/compose.yml ps
```

Most Docker Compose subcommands are passed through to the inner Docker engine.

## Engine Commands

The wrapper creates one Apple `container` dind engine per project directory.
The default engine name is `cc-<project-name>`.

```bash
container-compose engine status
container-compose engine logs
container-compose engine stop
container-compose engine rm
container-compose engine storage
container-compose engine prune-storage
```

By default, inner Docker data is stored in an Apple `container` volume named
`cc-<project-name>-docker`.

## Common Options

```bash
container-compose --publish 127.0.0.1:18081:8080 up -d
container-compose --rosetta --profile amd64 run --rm app
container-compose --engine-name cc-custom engine status
```

- `--publish`: pre-publish a dind VM port to macOS.
- `--rosetta`: create/use an engine that supports `linux/amd64` services.
- `--engine-name`: override the project-scoped engine name.
- `--docker-volume`: override the Apple `container` volume used for
  `/var/lib/docker`.

## Notes

- Compose named volumes are Docker volumes inside the inner dind engine and
  persist through the project-scoped `/var/lib/docker` volume.
- Bind mounts must resolve under the Compose project directory.
- If Compose ports change, recreate the engine so Apple `container` receives the
  new host port mappings.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for design details and
runtime constraints.

## Development

Development uses `uv` and `pytest`.

```bash
uv sync --dev
make test
```

Run the CLI from the checkout:

```bash
PYTHONPATH=src uv run python -m container_compose_proxy --help
```
