# `review` command

Report the lint findings on the changed lines only: staged, since a base, or uncommitted.

```bash
fobis review [PATHS...] [options]
```

`PATHS` are the sources to lint (default: the sources of the fobos mode, else `./`). Guide:
[Reviewing a change](/ai/review).

## Options

| Option | Description |
|--------|-------------|
| `--staged` | Review the staged change (pre-commit hook) |
| `--base REF` | Review the commits since the merge base with `REF` (pull request) |
| `--context N` | Also report findings up to `N` lines away from a changed line (default 0) |
| `--select IDS`, `--ignore IDS` | Rule selection, as for `fobis lint` (repeatable, comma-separated) |
| `--format FMT` | `text` (default), `markdown`, `json`, `sarif`, `github` |
| `--compiler-feedback LOG` | Build log with compiler optimisation reports, as for `fobis lint` |
| `--deep` | Add an LLM risk summary of the change, with citations (text, markdown, json) |
| `--deep-context` | Print what the model would receive for `--deep`, run no model |
| `--exit-zero` | Exit 0 even when findings are reported |
| `--varset NAME` | Apply `[varset:NAME]` bindings |

Without `--staged` or `--base`, every uncommitted change (staged or not) is reviewed.

## fobos options

| Option | Description |
|--------|-------------|
| `-f`, `--fobos` | Specify a fobos file with a different name or path |
| `--fci`, `--fobos-case-insensitive` | Case-insensitive fobos option parsing |
| `--mode` | Select a fobos mode (sources, exclusions, `-D` flags, `[lint]` section) |

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | No finding of severity error or warning on the changed lines (or `--exit-zero`) |
| 1 | Findings on the changed lines, an unreadable file, or an error (not a git repository, unknown base) |
