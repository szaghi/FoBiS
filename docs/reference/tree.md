# `tree` command

Print the resolved inter-project dependency tree.

```bash
fobis tree [options]
```

`fobis tree` reads the `[dependencies]` section of the active fobos file and
renders the full dependency hierarchy — including transitive dependencies — as
an annotated ASCII tree.

## Options

| Option | Default | Description |
|---|---|---|
| `--depth N` | unlimited | Limit tree expansion to N levels deep |
| `--no-dedupe` | `False` | Show duplicate nodes in full instead of collapsing with `(*)` |

## fobos options

| Option | Description |
|---|---|
| `-f`, `--fobos` | Specify a fobos file with a different name or path |
| `--mode` | Select a fobos mode |

## Output format

```
myproject  v1.2.0
└── PENF  v1.5.0  (tag=v1.5.0)
├── stdlib  v0.5.0  (tag=v0.5.0)
│   └── test-drive  (branch=main) [no fobos — cannot read transitive deps]
└── json-fortran  (branch=main)
    └── PENF  (*) [already shown]
```

| Annotation | Meaning |
|---|---|
| `[not fetched — run fobis fetch]` | Dependency directory is absent; run `fobis fetch` first |
| `[no fobos — cannot read transitive deps]` | Directory exists but contains no fobos; transitive deps unknown |
| `(*) [already shown]` | Node appeared earlier; children collapsed to avoid infinite loops |

## Examples

```bash
# Show the full dependency tree
fobis tree

# Limit to direct dependencies only
fobis tree --depth 1

# Show all duplicate nodes expanded
fobis tree --no-dedupe
```

::: tip Fetch before tree
Run `fobis fetch` before `fobis tree` to see the full transitive tree.
Without fetching, each unfetched node shows `[not fetched]` and its children
are unknown.
:::
