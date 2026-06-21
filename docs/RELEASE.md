# Release

This project is distributed as a Python command line application. The preferred
release channel is a Homebrew tap backed by GitHub release assets.

## Prerequisites

- Apple `container` CLI 1.0+ for integration testing
- `uv`
- `brew`
- `gh`, authenticated with access to `k-tech-org/container-compose`
- GitHub repository access to `k-tech-org/container-compose`
- A Homebrew tap repository: `k-tech-org/homebrew-container-compose`

## Release

Run the release command:

```bash
make release VERSION=<version>
```

Example:

```bash
make release VERSION=0.1.0
```

Positional shorthand is also supported:

```bash
make release 0.1.0
```

The command performs the full release flow:

- verifies that the git working tree is clean
- updates version metadata
- runs `make test`
- builds the source distribution and wheel
- computes the sdist checksum
- updates `Formula/container-compose.rb`
- commits the release changes
- creates and pushes the git tag
- pushes the current branch
- creates the GitHub release with `gh`
- uploads the sdist and wheel

To skip tests:

```bash
make release VERSION=0.1.0 RELEASE_ARGS="--skip-tests"
```

To prepare artifacts without publishing:

```bash
make release VERSION=0.1.0 RELEASE_ARGS="--skip-git"
```

`--skip-git` is intended for local verification and does not require a clean git
working tree. A real release does require a clean working tree so unrelated
changes are not included in the release commit.

The release script updates the Homebrew tap from a temporary checkout. It clones
`git@github.com:k-tech-org/homebrew-container-compose.git`, commits the Formula
update, pushes it, and removes the temporary checkout on exit.

Pass `--skip-tap` when the GitHub release should be created without updating the
Homebrew tap.

## Tap Verification

After the tap update, verify installation from the tap:

```bash
brew audit --strict --online k-tech-org/container-compose/container-compose
brew install --build-from-source k-tech-org/container-compose/container-compose
brew test k-tech-org/container-compose/container-compose
```

## Homebrew Notes

Homebrew packages Python applications in a virtual environment rooted at
`libexec`. The formula therefore uses `Language::Python::Virtualenv` and
`virtualenv_install_with_resources`.

When dependencies change, regenerate Python resource stanzas:

```bash
brew update-python-resources Formula/container-compose.rb
```

The formula test intentionally checks only CLI startup. It does not start Apple
`container` or pull `docker:28-dind`, because Homebrew formula tests should be
fast and should not require privileged runtime state.
