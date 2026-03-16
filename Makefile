.PHONY: dev test lint fmt clean

## Install package in editable mode with dev extras
dev:
	pip install -e ".[dev]"

## Run test suite
test:
	pytest

## Check linting (no fixes)
lint:
	ruff check .
	ruff format --check .

## Auto-fix lint and format
fmt:
	ruff check --fix .
	ruff format .

## Remove build artifacts
clean:
	rm -rf dist/ *.egg-info/ .pytest_cache/ .ruff_cache/ __pycache__/
