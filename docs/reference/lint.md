# `lint` command

Report bug-prone and obsolescent Fortran constructs.

```bash
fobis lint [PATHS...] [options]
```

`PATHS` are files or directories; without them the sources of the fobos mode are linted (default `./`).
Guide: [Linting](/ai/lint). Rules: [Lint Rules](/lint-rules/).

## Options

| Option | Description |
|---|---|
| `--select IDS` | Rule ids or prefixes to run (repeatable, comma-separated; `ALL` for every rule). Replaces the default set and the fobos `select`; enables opt-in rules |
| `--ignore IDS` | Rule ids or prefixes to skip (repeatable, comma-separated); added to the fobos `ignore` |
| `--format FMT` | `text` (default), `json`, `sarif` or `github` |
| `--baseline FILE` | Baseline file: findings recorded there are not reported [default: fobos `baseline`, else `.fobis-lint-baseline.json` when present] |
| `--update-baseline` | Record all current findings into the baseline file and exit |
| `--exit-zero` | Exit 0 even when findings are reported |
| `--list-rules` | List every rule (id, name, severity, default, Fortitude equivalent) and exit |
| `--explain ID` | Print the documentation of a rule and exit |
| `--src SRC` | Source directory (repeatable) when no `PATHS` are given |
| `--varset NAMES` | Apply `[varset:NAME]` sections' `$variable` bindings before linting. See [Varsets](/advanced/varsets) |

## fobos options

| Option | Description |
|---|---|
| `-f`, `--fobos` | Specify a fobos file with a different name or path |
| `--fci`, `--fobos-case-insensitive` | Case-insensitive fobos option parsing |
| `--mode` | Select a fobos mode: its sources, exclusions and `-D` defines are used |

Project settings: the fobos [`[lint]` section](/fobos/lint).

## Exit codes

| Code | Meaning |
|---|---|
| `0` | No warning- or error-level finding (or `--exit-zero`) |
| `1` | Findings reported, a file could not be read, or invalid options (unknown rule, format, malformed baseline) |

## Examples

```bash
# Default rules on the fobos mode's sources
fobis lint

# Only obsolescent features, JSON output
fobis lint --select OBS --format json

# Adopt on an existing code: record today's findings, report only new ones
fobis lint --update-baseline
fobis lint

# Why is COR020 reported?
fobis lint --explain COR020
```
