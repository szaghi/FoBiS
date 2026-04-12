# `introspect` command

Output machine-readable JSON describing the project structure.

```bash
fobis introspect [options]
```

`fobis introspect` is designed for IDE integrations, editor plugins, CI
dashboards, and AI agent workflows. All output is written to stdout as JSON
(or TOML with `--format toml`).

## Query flags

At least one flag must be provided. Multiple flags combine their output into
a single JSON object.

| Flag | Description |
|---|---|
| `--sources` | List all discovered source files with metadata |
| `--compiler` | Active compiler name and all resolved flags |
| `--dependencies` | Resolved dependency list from `[dependencies]` section |
| `--targets` | Named targets from `[target.*]` sections |
| `--include-dirs` | Effective include search directories |
| `--buildoptions` | Full resolved build options namespace |
| `--projectinfo` | Project metadata from `[project]` section |
| `--all` | All of the above |

## Output options

| Option | Default | Description |
|---|---|---|
| `--format FORMAT` | `json` | Output format: `json` or `toml` |
| `--write` | `False` | Write individual `intro-*.json` files into `.fobis-info/` |

## fobos options

| Option | Description |
|---|---|
| `-f`, `--fobos` | Specify a fobos file with a different name or path |
| `--mode` | Select a fobos mode |

## Examples

```bash
# Show all project information as JSON
fobis introspect --all

# Show only the compiler and flags
fobis introspect --compiler

# Show project metadata
fobis introspect --projectinfo

# Write individual JSON files for IDE consumption
fobis introspect --all --write

# Use with jq to extract a specific field
fobis introspect --compiler | jq '.compiler.name'

# TOML output
fobis introspect --all --format toml
```

## Example output

```json
{
  "compiler": {
    "name": "gnu",
    "fc": "gfortran",
    "cflags": "-c -O2 -J mod",
    "lflags": "-J mod",
    "mpi": false,
    "openmp": false
  },
  "projectinfo": {
    "name": "myproject",
    "version": "1.2.0",
    "authors": ["Stefano Zaghi"]
  }
}
```

::: tip Claude Code integration
`fobis introspect --all` feeds the project graph directly to AI assistants.
It is the data source used by the bundled `/fobis` Claude Code skill.
See [Claude Code Skill](/guide/claude-skill) for details.
:::
