.PHONY: dev test lint fmt clean standalone

VENV   := .venv
PYTHON := $(VENV)/bin/python
PIP    := $(VENV)/bin/pip

$(VENV)/bin/activate:
	python3 -m venv $(VENV)

## Install package in editable mode with dev extras
dev: $(VENV)/bin/activate
	$(PIP) install -e ".[dev]"

## Run test suite
test: dev
	$(VENV)/bin/pytest

## Check linting (no fixes)
lint: dev
	$(VENV)/bin/ruff check fobis/ tests/
	$(VENV)/bin/ruff format --check fobis/ tests/

## Auto-fix lint and format
fmt: dev
	$(VENV)/bin/ruff check --fix fobis/ tests/
	$(VENV)/bin/ruff format fobis/ tests/

## Build a single-file, offline zipapp (dist/fobis.pyz) with the full runtime closure vendored
standalone: $(VENV)/bin/activate
	rm -rf build/standalone
	mkdir -p build/standalone dist
	$(PIP) install --target build/standalone .
	cp fobis/__main__.py build/standalone/__main__.py
	$(PYTHON) -m zipapp build/standalone -o dist/fobis.pyz -p "/usr/bin/env python3" -c
	$(PYTHON) -I dist/fobis.pyz -v
	@echo "Built dist/fobis.pyz"

## Remove build artifacts
clean:
	rm -rf dist/ build/ *.egg-info .pytest_cache .ruff_cache .coverage coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
