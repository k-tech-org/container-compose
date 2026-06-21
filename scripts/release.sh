#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/release.sh VERSION [options]

Examples:
  scripts/release.sh 0.1.0
  scripts/release.sh v0.1.0 --skip-tests
  scripts/release.sh 0.1.0 --skip-tap

Options:
  --skip-tests             Do not run make test before building.
  --skip-build             Do not run uv build.
  --skip-git               Do not commit, tag, or push.
  --skip-github-release    Do not create the GitHub release.
  --skip-tap               Do not update the Homebrew tap.
  --tap-dir PATH           Homebrew tap checkout to update.
  --branch NAME            Branch to push. Defaults to the current branch.
  -h, --help               Show this help.

This script updates release metadata, builds artifacts, commits, tags, pushes,
creates the GitHub release, and optionally updates the Homebrew tap.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -lt 1 ]]; then
  usage >&2
  exit 2
fi

VERSION="${1#v}"
shift

RUN_TESTS=1
RUN_BUILD=1
RUN_GIT=1
RUN_GITHUB_RELEASE=1
RUN_TAP=1
TAP_DIR="${HOMEBREW_TAP_DIR:-}"
DEFAULT_TAP_DIR=""
DEFAULT_TAP_REPO="git@github.com:k-tech-org/homebrew-container-compose.git"
TAP_CLONE_DIR=""
BRANCH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-tests)
      RUN_TESTS=0
      ;;
    --skip-build)
      RUN_BUILD=0
      ;;
    --skip-git)
      RUN_GIT=0
      RUN_GITHUB_RELEASE=0
      RUN_TAP=0
      ;;
    --skip-github-release)
      RUN_GITHUB_RELEASE=0
      ;;
    --skip-tap)
      RUN_TAP=0
      ;;
    --tap-dir)
      if [[ $# -lt 2 ]]; then
        echo "--tap-dir requires a value" >&2
        exit 2
      fi
      TAP_DIR="$2"
      shift
      ;;
    --branch)
      if [[ $# -lt 2 ]]; then
        echo "--branch requires a value" >&2
        exit 2
      fi
      BRANCH="$2"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [[ ! "$VERSION" =~ ^[0-9]+[.][0-9]+[.][0-9]+([-.][0-9A-Za-z.]+)?$ ]]; then
  echo "invalid version: $VERSION" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
DEFAULT_TAP_DIR="$(cd "$ROOT_DIR/.." && pwd)/homebrew-container-compose"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required" >&2
  exit 1
fi

if ! command -v shasum >/dev/null 2>&1; then
  echo "shasum is required" >&2
  exit 1
fi

if [[ "$RUN_GIT" -eq 1 || "$RUN_TAP" -eq 1 ]] && ! command -v git >/dev/null 2>&1; then
  echo "git is required" >&2
  exit 1
fi

if [[ "$RUN_GITHUB_RELEASE" -eq 1 ]] && ! command -v gh >/dev/null 2>&1; then
  echo "gh is required to create GitHub releases. Install gh or pass --skip-github-release." >&2
  exit 1
fi

RELEASE_NOTES_FILE="$(mktemp)"

cleanup_release_files() {
  rm -f "$RELEASE_NOTES_FILE"
  if [[ -n "$TAP_CLONE_DIR" ]]; then
    rm -rf "$TAP_CLONE_DIR"
  fi
}
trap cleanup_release_files EXIT

if [[ "$RUN_TAP" -eq 1 && -z "$TAP_DIR" && -d "$DEFAULT_TAP_DIR/.git" ]]; then
  TAP_DIR="$DEFAULT_TAP_DIR"
fi

if [[ "$RUN_TAP" -eq 1 && -z "$TAP_DIR" ]] && command -v brew >/dev/null 2>&1; then
  TAP_DIR="$(brew --repo k-tech-org/container-compose 2>/dev/null || true)"
fi

if [[ "$RUN_TAP" -eq 1 && -z "$TAP_DIR" ]]; then
  TAP_CLONE_DIR="$(mktemp -d)"
  echo "Cloning default Homebrew tap into temporary checkout: $TAP_CLONE_DIR"
  git clone "$DEFAULT_TAP_REPO" "$TAP_CLONE_DIR"
  TAP_DIR="$TAP_CLONE_DIR"
fi

if [[ "$RUN_TAP" -eq 1 && -n "$TAP_DIR" && ! -d "$TAP_DIR/.git" ]]; then
  echo "Homebrew tap directory is not a git checkout: $TAP_DIR" >&2
  exit 1
fi

if [[ "$RUN_GIT" -eq 1 && -z "$BRANCH" ]]; then
  BRANCH="$(git branch --show-current)"
fi

if [[ "$RUN_GIT" -eq 1 && -z "$BRANCH" ]]; then
  echo "could not determine current git branch; pass --branch NAME" >&2
  exit 1
fi

if [[ "$RUN_GIT" -eq 1 ]] && [[ -n "$(git status --porcelain)" ]]; then
  echo "working tree has uncommitted changes; commit or stash them before release" >&2
  exit 1
fi

TAG="v$VERSION"
SDIST="dist/container_compose-$VERSION.tar.gz"
WHEEL="dist/container_compose-$VERSION-py3-none-any.whl"
RELEASE_URL="https://github.com/k-tech-org/container-compose/releases/download/$TAG/container_compose-$VERSION.tar.gz"
COMMIT_MESSAGE="Prepare $TAG release"

if [[ "$RUN_GIT" -eq 1 ]] && git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "tag already exists locally: $TAG" >&2
  exit 1
fi

if [[ "$RUN_GIT" -eq 1 ]] && git ls-remote --exit-code --tags origin "$TAG" >/dev/null 2>&1; then
  echo "tag already exists on origin: $TAG" >&2
  exit 1
fi

python3 - "$VERSION" "$RELEASE_URL" <<'PY'
from __future__ import annotations

from pathlib import Path
import re
import sys

version = sys.argv[1]
release_url = sys.argv[2]

updates = [
    (
        Path("pyproject.toml"),
        [
            (r'^version = ".*"$', f'version = "{version}"'),
        ],
    ),
    (
        Path("src/container_compose_proxy/__init__.py"),
        [
            (r'^__version__ = ".*"$', f'__version__ = "{version}"'),
        ],
    ),
    (
        Path("Formula/container-compose.rb"),
        [
            (r'^\s*url ".*"$', f'  url "{release_url}"'),
            (r'^\s*sha256 ".*"$', '  sha256 "REPLACE_WITH_DIST_SHA256"'),
        ],
    ),
]

for path, replacements in updates:
    text = path.read_text(encoding="utf-8")
    for pattern, replacement in replacements:
        text, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
        if count != 1:
            raise SystemExit(f"failed to update {path}: {pattern}")
    path.write_text(text, encoding="utf-8")
PY

if [[ "$RUN_TESTS" -eq 1 ]]; then
  make test
fi

if [[ "$RUN_BUILD" -eq 1 ]]; then
  rm -rf dist build src/container_compose.egg-info
  uv build

  if [[ ! -f "$SDIST" ]]; then
    echo "missing sdist: $SDIST" >&2
    exit 1
  fi
  if [[ ! -f "$WHEEL" ]]; then
    echo "missing wheel: $WHEEL" >&2
    exit 1
  fi

  SHA256="$(shasum -a 256 "$SDIST" | awk '{print $1}')"

  python3 - "$SHA256" <<'PY'
from __future__ import annotations

from pathlib import Path
import re
import sys

sha256 = sys.argv[1]
path = Path("Formula/container-compose.rb")
text = path.read_text(encoding="utf-8")
text, count = re.subn(
    r'^  sha256 "REPLACE_WITH_DIST_SHA256"$',
    f'  sha256 "{sha256}"',
    text,
    count=1,
    flags=re.MULTILINE,
)
if count != 1:
    raise SystemExit("failed to replace Formula sha256 placeholder")
path.write_text(text, encoding="utf-8")
PY

  ruby -c Formula/container-compose.rb >/dev/null

  echo
  echo "Built release artifacts:"
  echo "  $SDIST"
  echo "  $WHEEL"
  echo "sdist sha256:"
  echo "  $SHA256"
else
  if grep -q 'REPLACE_WITH_DIST_SHA256' Formula/container-compose.rb; then
    echo "skipped build, but Formula sha256 is not set" >&2
    exit 1
  fi
  echo "Skipped build. Existing Formula sha256 was preserved."
fi

if grep -q 'REPLACE_WITH_DIST_SHA256' Formula/container-compose.rb; then
  echo "Formula sha256 placeholder remains; refusing to release" >&2
  exit 1
fi

ruby -c Formula/container-compose.rb >/dev/null

cat >"$RELEASE_NOTES_FILE" <<EOF
Release $TAG.

Install with Homebrew:

brew tap k-tech-org/container-compose
brew install container-compose
EOF

if [[ "$RUN_GIT" -eq 1 ]]; then
  git add pyproject.toml src/container_compose_proxy/__init__.py Formula/container-compose.rb

  if git diff --cached --quiet; then
    echo "nothing staged for release commit" >&2
    exit 1
  fi

  git commit -m "$COMMIT_MESSAGE"
  git tag "$TAG"
  git push origin "$BRANCH"
  git push origin "$TAG"
else
  echo "Skipped git commit, tag, and push."
fi

if [[ "$RUN_GITHUB_RELEASE" -eq 1 ]]; then
  gh release create "$TAG" "$SDIST" "$WHEEL" \
    --repo k-tech-org/container-compose \
    --title "$TAG" \
    --notes-file "$RELEASE_NOTES_FILE"
else
  echo "Skipped GitHub release creation."
fi

if [[ "$RUN_TAP" -eq 1 ]]; then
  if [[ -z "$TAP_DIR" ]]; then
    echo "Homebrew tap checkout was not resolved" >&2
    exit 1
  else
    TAP_DIR="$(cd "$TAP_DIR" && pwd)"
    mkdir -p "$TAP_DIR/Formula"
    cp Formula/container-compose.rb "$TAP_DIR/Formula/container-compose.rb"

    git -C "$TAP_DIR" add Formula/container-compose.rb
    if git -C "$TAP_DIR" diff --cached --quiet; then
      echo "Homebrew tap already up to date: $TAP_DIR"
    else
      git -C "$TAP_DIR" commit -m "Update container-compose to $TAG"
      TAP_BRANCH="$(git -C "$TAP_DIR" branch --show-current)"
      if [[ -z "$TAP_BRANCH" ]]; then
        echo "could not determine Homebrew tap branch" >&2
        exit 1
      fi
      git -C "$TAP_DIR" push origin "$TAP_BRANCH"
    fi
  fi
else
  echo "Skipped Homebrew tap update."
fi

cat <<EOF

Release complete: $TAG

Artifacts:
  $SDIST
  $WHEEL

Formula:
  Formula/container-compose.rb
EOF
