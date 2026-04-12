# Build Cache

FoBiS maintains a content-addressed build cache to skip recompilation when
sources and flags have not changed — even across clean builds or switched
working trees.

## How it works

Before compiling a source file, FoBiS computes a **cache key** from:

| Component | How it is captured |
|---|---|
| Source file commit SHA | `git hash-object` (or file mtime if outside git) |
| Active compiler name | e.g. `gnu`, `intel` |
| Effective `cflags` (normalised) | sorted, whitespace-collapsed |
| FoBiS version | current installed version |

The key is hashed with SHA-256. If a matching object file exists in the cache
store, it is copied directly to the build directory — the compiler is never
invoked.

## Cache location

By default the cache lives at `.fobis_cache/` in the project root. Override
with `--cache-dir` or the `cache_dir` fobos key:

```ini
[default]
compiler  = gnu
cache_dir = ~/.cache/fobis   # shared across projects
```

## `fobis cache` subcommands

```bash
# List cached entries with sizes and timestamps
fobis cache list

# Remove entries older than N days
fobis cache clean --older-than 30

# Show the cache directory path and total size
fobis cache show
```

## Disabling the cache

```bash
# Disable for one build
fobis build --no-cache

# Always disable via fobos
[default]
no_cache = true
```

## When the cache invalidates

A cache entry is invalidated (and the file is recompiled) when any of the
key components change:

- the source file is modified (new commit SHA or mtime)
- `cflags` change (e.g. switching from `-O0` to `-O3`)
- the compiler changes (e.g. `gnu` → `intel`)
- FoBiS itself is upgraded to a new version

## CI usage

The cache is most useful in local development. In CI, share it between runs
using an artifact cache:

```yaml
- uses: actions/cache@v4
  with:
    path: .fobis_cache
    key: fobis-${{ runner.os }}-${{ hashFiles('fobos', '**/*.F90') }}
    restore-keys: fobis-${{ runner.os }}-
```

## Cache maintenance

Old entries accumulate over time. Prune them periodically:

```bash
# Remove entries not accessed in 60 days
fobis cache clean --older-than 60
```

Or add this to your CI cleanup step to keep the cached artifact small.
