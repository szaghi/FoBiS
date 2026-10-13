# `gate` command

One verdict for a change: build, review, test, verify, diff-run, bench, assess and matrix as stages, each with its
first failing fact. Guide: [The gate](/advanced/gate).

```bash
fobis gate [options]
```

| Option | Description |
|--------|-------------|
| `--stage S` | Run only these stages, in this order (repeatable or comma-separated) |
| `--skip S` | Stages not to run (repeatable) |
| `--advisory S` | Stages reported but not failing the gate (repeatable) |
| `--base REF` | Compare with the merge base of HEAD and REF, uncommitted changes included [default: the working tree against HEAD] |
| `--mode M` | Mode for build, review and test |
| `--fail-fast` | Stop at the first blocking failure |
| `--json` | One JSON object (see [JSON output](/advanced/json-output#fobis-gate-json)) |
| `-f/--fobos`, `--fci` | The fobos file |

Stages: `build`, `review`, `test`, `verify`, `diff-run`, `bench`, `assess`, `matrix`. fobos `[gate]` keys:
`stages`, `skip`, `advisory`, `base`, `mode`, `matrix_modes`, `matrix_shadows`.

Exit code 0 (pass), 1 (a non-advisory stage failed or gave no result), 2 (declaration error, unknown base).
