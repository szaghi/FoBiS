# `coverage` command

Generate HTML/XML coverage reports from instrumented test runs.

```bash
fobis coverage [options]
```

`fobis coverage` calls `gcovr` or `lcov/genhtml` (auto-detected) on the `.gcda`
files produced by an instrumented build, and writes the report to an output
directory.

## Prerequisites

1. Build with coverage instrumentation:
   ```bash
   fobis build --build-profile coverage
   # or in fobos: build_profile = coverage
   ```
2. Run the tests to generate `.gcda` files:
   ```bash
   fobis test
   ```
3. Generate the report:
   ```bash
   fobis coverage
   ```

## Options

| Option | Default | Description |
|---|---|---|
| `--format FMT` | `html` | Output format: `html`, `xml`, `text`, `all` (repeatable) |
| `--output-dir DIR` | `coverage/` | Directory for the generated report files |
| `--source-dir DIR` | `.` | Root source directory for coverage filtering |
| `--exclude GLOB` | — | Glob patterns for files to exclude (repeatable) |
| `--fail-under N` | — | Exit 1 if line coverage is below N percent |
| `--tool TOOL` | (auto) | Force a specific backend: `gcovr` or `lcov` |

## fobos options

| Option | Description |
|---|---|
| `-f`, `--fobos` | Specify a fobos file with a different name or path |
| `--mode` | Select a fobos mode |

## Backend tool priority

1. `gcovr` (preferred — pip install gcovr)
2. `lcov` + `genhtml`
3. Error if neither is available

## Examples

```bash
# Generate an HTML report (default)
fobis coverage

# Generate both HTML and Cobertura XML (for CI upload to Codecov)
fobis coverage --format html --format xml

# Generate all formats at once
fobis coverage --format all

# Fail CI if coverage drops below 80 %
fobis coverage --format xml --fail-under 80

# Exclude test files from the coverage report
fobis coverage --exclude "test/*" --exclude "examples/*"

# Specify the output directory
fobis coverage --output-dir reports/coverage
```

## `[coverage]` fobos section

```ini
[coverage]
output_dir  = coverage/
source_dir  = src/
fail_under  = 75
exclude     = test/*
             examples/*
```

## Full workflow

```bash
# 1. Build with the coverage profile
fobis build --build-profile coverage

# 2. Run tests (generates .gcda files)
fobis test

# 3. Generate the report
fobis coverage --format html --fail-under 80

# Open the report
xdg-open coverage/index.html   # Linux
open coverage/index.html        # macOS
```

::: tip CI integration (GitHub Actions)
```yaml
- run: fobis build --build-profile coverage
- run: fobis test
- run: fobis coverage --format xml --fail-under 75
- uses: codecov/codecov-action@v4
  with:
    files: coverage/coverage.xml
```
:::
