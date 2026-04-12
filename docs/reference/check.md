# `check` command

Validate the project's dependency graph without compiling anything.

```bash
fobis check [options]
```

`fobis check` scans sources, resolves modules, and reports any dependency
problems — missing modules, unresolved includes, circular dependencies — as
structured diagnostics. Exit code 0 means no errors.

## Options

| Option | Description |
|---|---|
| `--src SRC` | Source directory (repeatable) |
| `--strict` | Treat warnings as errors (exit 1 on any warning) |

## fobos options

| Option | Description |
|---|---|
| `-f`, `--fobos` | Specify a fobos file with a different name or path |
| `--fci`, `--fobos-case-insensitive` | Case-insensitive fobos option parsing |
| `--mode` | Select a fobos mode |

## Diagnostics

| Code | Severity | Meaning |
|---|---|---|
| `E001` | Error | `use` statement refers to a module that cannot be found in any source file or dependency |
| `E002` | Error | Circular dependency detected between two or more source files |
| `E003` | Error | `include` directive references a file that does not exist |
| `W001` | Warning | `[dependencies]` section present but no `fobos.lock` — builds are not reproducible |
| `W002` | Warning | A declared dependency directory is absent — run `fobis fetch` |

Warnings become errors when `--strict` is passed.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | No errors found |
| `1` | One or more errors found (or warnings with `--strict`) |

## Examples

```bash
# Validate the project graph
fobis check

# Strict mode — warnings become errors (suitable for CI)
fobis check --strict

# Check a specific source directory
fobis check --src ./src
```

::: tip Use in CI
Add `fobis check --strict` as a pre-build gate in CI. It runs in milliseconds
(no compilation), catches unresolved modules before the compiler does, and
reports missing lock files so your builds stay reproducible.
:::
