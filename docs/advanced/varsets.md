# Varsets

Varsets are named bundles of `$variable` bindings selected at invocation time.
They eliminate the per-cluster / per-target mode duplication that arises when
the only difference between several modes is a handful of paths or numeric
parameters.

## When to reach for varsets

Look at your fobos for modes that differ **only** in `$variable` values
(library paths, GPU architectures, install prefixes). If you find a cluster
of mode blocks like:

```ini
[mode-prism-leonardo]
template = template-nvf-oac
target   = adam_prism_fnl.F90
libs     = $HDF5_leonardo_nvf/lib/libhdf5_fortran.a $HDF5_leonardo_nvf/lib/libhdf5.a
lib_dir  = $HDF5_leonardo_nvf/lib
include  = $HDF5_leonardo_nvf/include

[mode-prism-iac]
template = template-nvf-oac
target   = adam_prism_fnl.F90
libs     = $HDF5_iac_nvf/lib/libhdf5_fortran.a $HDF5_iac_nvf/lib/libhdf5.a
lib_dir  = $HDF5_iac_nvf/lib
include  = $HDF5_iac_nvf/include
```

…that is the varset use case in textbook form. With varsets the per-cluster
modes collapse to a single mode plus N varsets:

```ini
[varset:leonardo]
$HDF5_PREFIX = /leonardo/prod/spack/.../hdf5-1.14.3

[varset:iac]
$HDF5_PREFIX = lib/hdf5/develop/nvf/25.5-iac

[mode-prism]
template = template-nvf-oac
target   = adam_prism_fnl.F90
libs     = $HDF5_PREFIX/lib/libhdf5_fortran.a $HDF5_PREFIX/lib/libhdf5.a
lib_dir  = $HDF5_PREFIX/lib
include  = $HDF5_PREFIX/include
```

```bash
fobis build --mode mode-prism --varset leonardo
fobis build --mode mode-prism --varset iac
```

## Defining a varset

A varset is a section named `[varset:NAME]` whose keys are `$variable`
bindings. Any key without a leading `$` is reported as a warning and
ignored; well-formed sibling keys still apply.

```ini
[varset:cuda-cc89]
$ARCH        = cc89
$CUDA_VER    = cuda12.8
$GPU_FLAGS   = -gpu=cc89,cuda12.8,ptxinfo
```

The variables defined inside a `[varset:NAME]` section **do not leak** into
the implicit global pool. They apply only when the varset is selected via
`--varset` or via a fobos-declared default. Variables defined in other
sections (e.g. `[common-variables]`) continue to behave as before — they bind
globally and are visible to every mode.

### Overlapping variable names

Substitution respects identifier boundaries. Defining both `$HDF5` and
`$HDF5_PREFIX` in the same fobos is safe — the shorter name will not match
inside the longer one, regardless of declaration order:

```ini
[varset:legacy]
$HDF5        = /opt/hdf5

[varset:modern]
$HDF5_PREFIX = /opt/hdf5-1.14
```

Either varset can be active and both names resolve correctly.

## Activating varsets

```bash
# Activate a single varset
fobis build --mode mode-prism --varset leonardo

# Multiple varsets, last write wins on shared variable names
fobis build --mode mode-prism --varset leonardo,cuda-cc89

# Mix space and comma separators
fobis build --mode mode-prism --varset "leonardo cuda-cc89"
```

When multiple varsets define the same `$NAME`, the rightmost one in the list
wins. Variables defined in only one varset always apply.

## Default varset (fobos-declared fallback)

Declare a fobos-level default in a `[varsets]` section so users get a sensible
configuration without having to remember `--varset`:

```ini
[varsets]
default = local

[varset:local]
$HDF5_PREFIX = lib/hdf5/develop/nvf/26.1

[varset:leonardo]
$HDF5_PREFIX = /leonardo/prod/spack/.../hdf5-1.14.3
```

```bash
fobis build --mode mode-prism                    # uses local (the default)
fobis build --mode mode-prism --varset leonardo  # overrides default; leonardo wins
```

The default is applied **only** when `--varset` is not supplied. CLI varsets
do not stack with the default — an explicit user choice overrides it
entirely.

The `default = ...` value accepts space- or comma-separated multiple varsets,
applied left-to-right with last-write-wins, exactly like the CLI form.

## Resolution order

For a given mode, `$variables` are resolved in this order:

1. Implicit global pool: every `$NAME = value` defined in any section
   *other than* `[varset:*]`.
2. If `--varset NAMES` is present on the CLI: each named varset is overlaid
   in order (last write wins).
3. Otherwise, if `[varsets] default = NAMES` is set in the fobos: those
   varsets are overlaid as the implicit fallback.

The resulting variable dictionary is substituted into every value in the
active mode block before the rest of the build configuration is resolved.

## Diagnostics

| Situation | Behaviour |
|---|---|
| `--varset NAME` for an undefined name | Hard error. Exit 1. The error lists available varsets. |
| `[varsets] default = NAME` references an undefined varset | Same hard error as above. |
| `[varset:NAME]` has a key without a leading `$` | Warning. The malformed key is ignored. Other keys still apply. |
| `[varset:NAME]` has no `$`-keys at all | Warning. The varset is empty (likely a typo). |
| Variable used in a mode but not bound by any source | The literal `$NAME` token is left in the value (unchanged from current behaviour). |

## Listing available varsets

```bash
fobis introspect --varsets
```

Returns JSON with:

- `default`: the list of varsets declared by `[varsets] default = ...` (empty
  list if none).
- `varsets`: a map of `name -> {$VAR: value, ...}` for every `[varset:NAME]`
  section in the fobos.

Combine with `--all` to include varset information alongside other project
metadata in a single payload.

## Varsets and feature flags

Varsets and feature flags are orthogonal mechanisms that compose cleanly:

- **Varsets** bind `$variables` substituted into the mode block (paths, numeric
  parameters, build prefixes).
- **Feature flags** add tokens to `cflags`/`lflags` (defines, optimization
  flags, capability switches).

```bash
# leonardo paths + production feature bundle
fobis build --mode mode-prism --varset leonardo --features prod
```

::: tip Why varsets, not more modes
The modes-as-Cartesian-product trap is real: every new cluster, every new GPU
arch, every new install prefix doubles the number of mode blocks and pins the
duplication. Varsets break the trap by exposing the *axis* directly. One mode
+ N varsets = N invocations, instead of N mode blocks.
:::
