# `case` command

List and run the cases declared in the fobos (`[case:NAME]` sections). Guide:
[Cases, quantities and provenance](/advanced/cases).

```bash
fobis case list [options]
fobis case run [NAME...] [options]
```

## `case list`

| Option | Description |
|--------|-------------|
| `--json` | The cases as JSON |
| `-f/--fobos`, `--fci` | The fobos file |

## `case run`

Build (for a `target`) and run each case (all by default) in a fresh run directory, and report its quantities.

| Option | Description |
|--------|-------------|
| `--mode M` | Build with this mode instead of the case's own |
| `--json` | One JSON object: `results`, each with status, exit code, elapsed time, command, run directory, quantities, probe errors, output tails, provenance and, when the build failed, the build's diagnoses |
| `-f/--fobos`, `--fci` | The fobos file |

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Every run is `ok` |
| 1 | A run failed, timed out, did not build or missed a quantity |
| 2 | A case is declared incorrectly, or an unknown case is named |
