# `run` command

Build a target and execute it in a single step.

```bash
fobis run [TARGET] [options] [-- BINARY_ARGS...]
```

If `TARGET` is omitted, the output name from the active fobos mode is used.
Arguments after `--` are forwarded verbatim to the binary.

## Options

| Option | Default | Description |
|---|---|---|
| `TARGET` | (fobos `output`) | Name of the target to build and run |
| `--no-build` | `False` | Skip the build step; execute the binary directly |
| `--dry-run` | `False` | Print the build and run commands without executing either |
| `--example NAME` | — | Run a `[[example.NAME]]` target from the fobos file |
| `--explain` | `False` | When the program fails, explain why (see [Explaining failures](/ai/explain#runtime-failures)); also passed to the build |
| `--explain-context` | `False` | Like `--explain`, but print what the model would receive instead of running it |

## fobos options

| Option | Description |
|---|---|
| `-f`, `--fobos` | Specify a fobos file with a different name or path |
| `--mode` | Select a fobos mode — tab-completable from the active fobos file |
| `--shadow NAME` | Rebuild the mode as a [shadow](/advanced/matrix#shadow-modes): `checks`, `sanitize`, `strict` (or `none`), in `.fobis/shadow/<mode>-<shadow>/` |

## Examples

```bash
# Build (if needed) and run the default target
fobis run

# Run with arguments forwarded to the binary
fobis run -- --input data.dat --nproc 8

# Run a named target
fobis run solver

# Skip rebuild, just run
fobis run --no-build

# Dry run: see what would be executed
fobis run --dry-run

# Run a named example
fobis run --example demo
```

## Exit codes

`fobis run` exits with the binary's own exit code. A non-zero exit from the
build step causes an immediate abort before execution.

::: tip Quick iteration
`fobis run` is equivalent to `fobis build && ./myapp`. Use it during
development to tighten the edit→compile→run loop without leaving the terminal.
:::
