# Includes

The `[include]` directive pulls the contents of one or more sibling fobos
files into the current one before any other processing. It lets you split a
large fobos into thematic chunks, share configuration across sibling repos,
and keep machine-local overrides outside of version control.

## Quick example

```ini
# fobos
[include]
paths = templates.fobos
        rules.fobos
        ?fobos.local                ; optional — silently skipped if absent

[modes]
modes = release debug

[release]
compiler = gnu
cflags   = -c -O3
target   = main.F90
```

Each path is resolved relative to the including file's directory (after
`${ENV}` and `~` expansion, or used as-is if absolute). After resolution,
every section from every included file is merged into the parent and the
`[include]` section itself is dropped.

## When to reach for `[include]`

Three patterns this makes possible:

### Splitting a large fobos by concern

A 500-line fobos can become a 20-line `fobos` plus four thematic files:

```ini
# fobos
[include]
paths = templates.fobos
        features.fobos
        modes.fobos
        rules.fobos
```

Each included file owns one kind of section, easier to navigate and review.

### Sharing across sibling repos

If several projects use the same compiler templates, check them into a
shared location and include from each:

```ini
# project-A/fobos
[include]
paths = ../shared-templates/gnu-and-nvf.fobos
```

This is *additive* — each project still has its own modes, rules, project
metadata, etc. — but the shared bits stay in sync via the shared file.

### Machine-local overrides

A common pattern: project defaults committed to git, plus a per-developer
override file that's git-ignored:

```ini
# fobos (committed)
[include]
paths = defaults.fobos          ; required — error if missing
        ?fobos.local            ; optional — present only on dev machines

[modes]
modes = release
```

```ini
# fobos.local (gitignored, per-developer)
[paths]
$HDF5_PREFIX = /home/me/my-custom-hdf5-build
```

CI and fresh checkouts skip the missing `?fobos.local` silently; developers
override paths without touching the committed file.

## Syntax

```ini
[include]
paths = a.fobos b.fobos             ; space-separated
        c.fobos                     ; or newline-continued
        ${HOME}/.fobis/local.fobos  ; env-vars expand
        ~/.fobis/global.fobos       ; ~ expands
        ?optional.fobos             ; '?' prefix → optional
```

The single key is `paths`. Tokens are separated by any whitespace (spaces,
tabs, newlines). A leading `?` marks the include as optional — if the file
doesn't exist, the directive is silently skipped. Without `?`, a missing
file aborts the build with `exit 1`.

Path resolution order:

1. Strip the `?` prefix if present.
2. Expand `${ENVVAR}` references via `os.path.expandvars`.
3. Expand a leading `~` via `os.path.expanduser`.
4. If the result is relative, resolve it against the including file's
   directory.

## Naming convention

The include resolver does not require any particular file name or extension —
any readable file with valid INI syntax will work. By **convention**, however,
included fragments use the `.fobos` suffix:

```
project/
├── fobos                      ; main entry point (no extension)
├── templates.fobos            ; included fragment
├── rules.fobos
└── prism/
    └── modes.fobos            ; nested fragment
```

This mirrors the `Makefile` + `*.mk` and `CMakeLists.txt` + `*.cmake` patterns
already established in build-tooling and gives you three concrete benefits:

- **Editor support.** Any editor that highlights `fobos` as INI will extend
  the same syntax to `*.fobos` with one filetype association.
- **Globbing.** `*.fobos` matches every fragment without false positives.
  Untracked-file patterns like `?fobos.local` work naturally for
  developer-local overrides.
- **Searchability.** `grep -r --include='*.fobos'` walks the include graph
  cleanly without picking up stray text files.

This is a recommendation, not a rule — `[include] paths = fobos_prism` works
exactly the same as `[include] paths = prism.fobos`. Pick what fits your
project; if you don't have a strong preference, prefer `.fobos`.

## Merge semantics

Includes are merged with **key-level granularity**, never whole-section
replacement.

| Conflict | Winner |
|---|---|
| Parent file vs. any include | **Parent wins.** The file you're reading is authoritative. |
| Earlier include vs. later include | **Later wins.** The last sibling in `paths = ...` overrides earlier ones. |
| Two unrelated keys in the same section | Both are kept. |

Concretely, if the parent has `[template-gnu] cflags = -O3` and an include
has `[template-gnu] cflags = -O0`, the result is `-O3`. If the include also
declares `[template-gnu] mod_dir = ./mod/`, that key flows through to the
merged template (the parent didn't declare it).

## Recursion and cycles

An included file may itself include other files. Inclusion is processed
depth-first: deepest leaves are absorbed first, sibling-collectives are
built from inside out.

Cycles are detected and abort with `exit 1`:

```
Error: include cycle detected: /repo/fobos -> /repo/a.fobos -> /repo/fobos.
```

A self-include (a file listing itself in `paths = ...`) is treated as a
cycle. A diamond (two distinct paths reach the same leaf) is **not** a
cycle — the leaf is loaded twice along independent branches and merged
correctly.

The maximum nesting depth is capped at 16 to fail fast on pathological
configurations:

```
Error: include depth exceeded (16) at 'd.fobos'. Likely a recursion bug.
```

## Composition with other features

`[include]` runs as a pre-processing pass before any other fobos logic.
Once includes are merged, the rest of the system sees a single combined
config — so every other fobos feature works transparently across includes:

| Feature | How it composes |
|---|---|
| `$variable` substitution | Variables defined in any included section bind globally, exactly as if declared in the main file. |
| `[features]` and `[feature:NAME]` | Feature definitions in includes are honoured by `--features` activation in the main mode. |
| `[varset:NAME]` | Varsets in includes are selectable via `--varset` from the CLI. |
| Templates (`template = template-X`) | Templates declared in includes are usable as `template = ...` references in the main file's modes. |
| `[varsets] default = ...` | Honoured wherever it lives — main file or included file. |

## Diagnostics

| Situation | Behaviour |
|---|---|
| `paths = does-not-exist.fobos` (required) | Hard error. Exit 1. Error suggests the `?` optional prefix. |
| `paths = ?does-not-exist.fobos` (optional) | Silent. Build proceeds. |
| Include cycle (`A → B → A` or self-include) | Hard error. Exit 1. The cycle path is named. |
| Depth exceeds 16 | Hard error. Exit 1. |
| Empty `[include]` or no `paths =` key | No-op. |

## What `[include]` doesn't do

- It is not a *macro* facility — there is no parameterised expansion. Each
  included file is loaded once with its literal content.
- It does not provide *namespacing*. All sections live in a single flat
  namespace; conflicting section names follow the merge rules above.
- It does not enable *conditional* inclusion based on mode/CLI flags. If
  conditional behaviour is needed, reach for varsets or feature flags
  (which are designed for that).

::: tip Composition with varsets
For *value*-level parameterisation (cluster paths, GPU arch, install
prefixes), prefer [varsets](/advanced/varsets) — they're designed for it
and don't require extra files.

For *structure*-level decomposition (splitting one config into many,
sharing across projects), reach for `[include]`.
:::
