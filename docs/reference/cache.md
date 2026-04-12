# `cache` command

Manage the FoBiS build artifact cache.

```bash
fobis cache <subcommand> [options]
```

The artifact cache stores compiled `use=fobos` dependencies keyed by a
SHA-256 hash of `(source commit | compiler | cflags | FoBiS version)`.
When the key matches, the cached artifacts are restored instead of rebuilding.

## Subcommands

### `fobis cache list`

List all cached entries with key, compiler, size, and date.

```bash
fobis cache list
```

Example output:

```
  key            compiler          size   date
  ---            --------          ----   ----
  a1b2c3d4e5f6   gfortran-13     1234 KB 2026-04-11
  9f8e7d6c5b4a   ifort-2024      2048 KB 2026-03-22
```

### `fobis cache clean`

Purge stale cache entries. Without `--older-than`, the entire cache directory is removed.

```bash
fobis cache clean [--older-than DAYS]
```

| Option | Default | Description |
|---|---|---|
| `--older-than DAYS` | — | Delete only entries older than this many days; omit to wipe the full cache |

### `fobis cache show`

Show cache status for a specific dependency by name.

```bash
fobis cache show DEP_NAME
```

## Cache location

| Source | Path |
|---|---|
| Default | `~/.fobis/cache/` |
| `FOBIS_CACHE_DIR` env var | Overrides the default path |
| `--cache-dir` (on `build` or `fetch`) | Per-invocation override |

Sharing a cache directory across projects on an NFS mount allows multiple
projects on an HPC cluster to reuse compiled dependencies without rebuilding.

## Cache key components

The cache key is `SHA-256(source_commit | compiler | normalised_cflags | fobis_version)`.

- **`source_commit`**: the git `HEAD` SHA of the dependency repository
- **`compiler`**: the compiler executable name (e.g. `gfortran-13`)
- **`normalised_cflags`**: compilation flags sorted and deduplicated so `-O2 -g` and `-g -O2` produce the same key
- **`fobis_version`**: ensures entries are invalidated after a FoBiS upgrade that changes build semantics

## Disabling the cache

```bash
# Bypass cache for a single build
fobis build --no-cache
fobis fetch --no-cache

# Disable permanently via environment variable
export FOBIS_CACHE_DIR=/dev/null
```

::: warning Cache and reproducibility
The cache does **not** replace `fobos.lock`. A cache hit restores artifacts
built from a specific locked commit; the lock file is still required to
guarantee which commit was used. Use both together for fully reproducible builds.
:::
