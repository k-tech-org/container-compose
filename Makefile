.PHONY: sync test test-unit test-integration test-all build release clean

UV ?= uv
PYTEST ?= $(UV) run pytest
VERSION ?=
RELEASE_POSITIONAL := $(filter-out release,$(MAKECMDGOALS))
RELEASE_VERSION := $(if $(VERSION),$(VERSION),$(firstword $(RELEASE_POSITIONAL)))
RELEASE_POSITIONAL_ARGS := $(wordlist 2,$(words $(RELEASE_POSITIONAL)),$(RELEASE_POSITIONAL))
RELEASE_ARGS ?= $(RELEASE_POSITIONAL_ARGS)

sync:
	$(UV) sync --dev

test: test-unit test-integration

test-unit:
	$(PYTEST) -m "not integration"

test-integration:
	$(PYTEST) -m integration -s

test-all:
	$(PYTEST) -s

build:
	$(UV) build

release:
	@if [ -z "$(RELEASE_VERSION)" ]; then \
		echo "Usage: make release VERSION=0.1.0"; \
		echo "   or: make release 0.1.0"; \
		echo "Options can be passed with RELEASE_ARGS, for example:"; \
		echo "  make release VERSION=0.1.0 RELEASE_ARGS=\"--skip-tests --skip-tap\""; \
		exit 2; \
	fi
	scripts/release.sh "$(RELEASE_VERSION)" $(RELEASE_ARGS)

clean:
	rm -rf build dist src/*.egg-info .pytest_cache
	find src tests -type d -name __pycache__ -prune -exec rm -rf {} +

%:
	@:
