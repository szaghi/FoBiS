# Feature Flags

Feature flags let you define named compile-time options in the fobos file and
activate them selectively — without maintaining separate build modes for every
combination.

## Defining features

Add a `[features]` section to the fobos file. Each key is a feature name; the
value is the flags that feature contributes (cflags and lflags are separated
automatically):

```ini
[features]
default = mpi                     ; features active when none are explicitly requested

mpi    = -DUSE_MPI                ; pure define — goes to cflags
hdf5   = -DUSE_HDF5 -I/opt/hdf5/include
omp    = -DUSE_OMP -fopenmp       ; -fopenmp goes to lflags, -DUSE_OMP to cflags
netcdf = -DUSE_NETCDF

[default]
compiler = gnu
cflags   = -c -O2
```

## Activating features

```bash
# Default features only (from fobos [features] default =)
fobis build

# Explicitly request features (comma or space separated)
fobis build --features hdf5
fobis build --features "mpi,hdf5"

# Add features on top of defaults
fobis build --features netcdf        # defaults + netcdf

# Suppress defaults, use only what you specify
fobis build --no-default-features --features hdf5

# No features at all
fobis build --no-default-features

# Drop a feature from the active set (works on defaults, modes, or composites)
fobis build --features -coverage     # see "Negating features" below
```

A mode can also declare its own active feature set with `features = a b c`;
see [Integration with modes](#integration-with-modes) for the merge order.
Compose larger bundles with [composite features](#composite-features) and
constrain combinations with [Required features](#required-features),
[Conflicting features](#conflicting-features), and [Mutually-exclusive groups](#mutually-exclusive-groups).

## Flag routing

Flags in a feature value are routed automatically:

| Flag pattern | Goes to | Reason |
|---|---|---|
| `-D...` | `cflags` | preprocessor define |
| `-I...` | `cflags` | include path |
| `-L...` | `lflags` | library search path |
| `-l...` | `lflags` | library name |
| `-Wl,...` | `lflags` | linker option |
| OpenMP flags (see below) | **both** `cflags` and `lflags` | needed at compile and link time |
| everything else | `cflags` | default |

### OpenMP flags are dual-destination

When a feature value contains an OpenMP flag written as a raw string, FoBiS
routes it to both cflags and lflags automatically. The recognized flags are:

| Compiler | OpenMP flag |
|---|---|
| `gnu`, `opencoarrays-gnu`, `amd` | `-fopenmp` |
| `intel`, `intel_nextgen` | `-qopenmp` |
| `intel_nextgen` (link-phase variant) | `-fiopenmp` |
| `nvfortran`, `pgi` | `-mp` |
| `ibm` | `-qsmp=omp` |
| `nag` | `-openmp` |

## Implicit (compiler-agnostic) features

FoBiS recognises a set of **implicit** feature names that map directly to
compiler capabilities already defined in the compiler table — the same
abstraction used by `--openmp`, `--mpi`, and `--coarray`. You can activate
these without a `[features]` section and without writing a single
compiler-specific flag:

| Feature name | Alias | Activates |
|---|---|---|
| `openmp` | `omp` | OpenMP for the active compiler |
| `mpi` | — | MPI compiler wrapper |
| `coarray` | — | Coarray support |
| `coverage` | — | Coverage instrumentation |
| `profile` | — | Profiling instrumentation |
| `openmp_offload` | `omp_offload` | OpenMP offload |

```bash
# Compiler-agnostic — works correctly with gnu, intel, nvfortran, ...
fobis build --compiler gnu   --features openmp
fobis build --compiler intel --features openmp
fobis build --compiler nvfortran --features omp
```

FoBiS resolves `openmp` to the flag appropriate for the active compiler,
passes it to both cflags and lflags, and selects the MPI wrapper or coarray
runtime accordingly — identical to passing `--openmp` / `--mpi` / `--coarray`
on the command line.

### No `[features]` section required

Implicit features work even when the fobos file has no `[features]` section:

```ini
[default]
compiler = intel
cflags   = -c -O2
```

```bash
fobis build --features openmp,mpi   # resolves -qopenmp and mpiifort correctly
```

### Explicit definition always wins

If you define an implicit feature name explicitly in `[features]`, the explicit
definition is used as-is and the implicit mechanism is bypassed:

```ini
[features]
; Add a preprocessor define alongside OpenMP — explicit wins over implicit
openmp = -DUSE_OMP -fopenmp
```

```bash
fobis build --compiler gnu --features openmp
# → routes -DUSE_OMP to cflags, -fopenmp to both cflags and lflags
# → does NOT set cliargs.openmp via the implicit mechanism
```

### Combining implicit and explicit features

Implicit and explicit features compose freely:

```ini
[features]
hdf5 = -DUSE_HDF5 -I/opt/hdf5/include -L/opt/hdf5/lib -lhdf5
```

```bash
# openmp resolved implicitly, hdf5 resolved explicitly
fobis build --features openmp,hdf5
```

### Preprocessor defines with implicit features

Implicit features activate the compiler capability but do not add a
preprocessor define. If `#ifdef USE_OMP` guards are needed, add a separate
explicit feature for the define and combine both:

```ini
[features]
omp_defs = -DUSE_OMP
```

```bash
fobis build --features openmp,omp_defs
```

## Composite features

A feature value may **reference other features** with the `@` prefix. The
referenced features are expanded recursively, so a single name can pull in a
whole bundle:

```ini
[features]
release  = -O3 -DNDEBUG
debug    = -g -O0 -fcheck=all
hdf5     = -DUSE_HDF5 -I/opt/hdf5/include

prod     = @release @hdf5            ; bundle of two leaves
dev-mpi  = @debug @mpi -DEXTRA_LOG   ; mix references and own flags
```

Activating `prod` is equivalent to activating `release` and `hdf5`. Activating
`dev-mpi` activates `debug` (explicit), `mpi` (implicit), AND contributes the
literal flag `-DEXTRA_LOG` from `dev-mpi`'s own value.

Rules:

- Only `@`-prefixed tokens recurse. A bare `coverage` inside a feature value is
  treated as a literal flag string, not as a reference. Use `@coverage` to
  reference the implicit `coverage` feature.
- Cycles are detected and ignored with a warning (`feature cycle detected:
  a -> b -> a`).
- Composites can reference both explicit features and implicit ones (`@openmp`,
  `@mpi`, etc.).

## Negating features

Prefix a feature name with `-` on the CLI to **drop** it from the active set,
even if it was added by `default`, by a mode-level `features = ...`, or by a
composite expansion. Negation is applied **after** all expansion, so it works
identically regardless of where the feature came from:

```ini
[features]
default  = release coverage
release  = -O3
prod     = @release @coverage
```

```bash
fobis build --features -coverage             # release only (drops default)
fobis build --features prod,-coverage        # prod expanded, then coverage dropped
fobis build --features prod,-release         # prod's own flags only (release dropped)
```

A negation that doesn't match any active feature emits a warning — usually a
typo:

```
Warning: --features negation '-cobverage' does not match any active feature. Ignored.
```

## Unknown features

Requesting a feature name that is not defined in `[features]` and is not an
implicit name emits a warning and is otherwise ignored — the build continues:

```
Warning: unknown feature 'cuda'. Known features: hdf5, mpi, netcdf, omp. Ignored.
```

## Integration with modes

Features work across all modes, and a mode can declare its own active set
inline with `features = a b c`. The merge order is, from most general to most
specific:

1. `[features] default = ...` (skipped when `--no-default-features` is given)
2. `[mode-X] features = ...` from the active mode
3. `--features ...` from the CLI

Each step appends names not already present; CLI negation tokens are applied
after the full expansion to drop entries from any earlier step.

```ini
[features]
release  = -O3 -DNDEBUG
debug    = -g -O0
hdf5     = -DUSE_HDF5 -I/opt/hdf5/include
prod     = @release @hdf5
dev      = @debug @hdf5

[modes]
modes = prod-mode dev-mode

[mode-prod-mode]
compiler = gnu
cflags   = -c
features = prod

[mode-dev-mode]
compiler = gnu
cflags   = -c
features = dev
```

```bash
fobis build --mode prod-mode                    # release + hdf5
fobis build --mode dev-mode                     # debug + hdf5
fobis build --mode prod-mode --features mpi     # release + hdf5 + mpi
fobis build --mode dev-mode --features -hdf5    # debug only
```

The `--no-default-features` CLI flag affects only the `[features] default =`
line; mode-level and CLI activations always apply.

## Required features

A feature can declare prerequisites with `[feature:NAME] requires = ...`.
Activating the feature auto-activates each named prerequisite (transitively),
so the user does not have to remember the chain:

```ini
[features]
hdf5 = -DUSE_HDF5
mpi  = -DUSE_MPI

[feature:hdf5]
requires = mpi
```

```bash
fobis build --features hdf5
# → activates hdf5 AND mpi
# → emits: Activating 'mpi' required by 'hdf5'.
```

The auto-pull is recursive (A requires B, B requires C → activating A pulls
all three) and cycle-safe (mutual `requires` are reported with a warning,
not an infinite loop). A `requires` target that does not resolve to a known
feature surfaces the same unknown-feature warning as a direct activation —
typos are caught.

::: tip Why auto-pull instead of fail
A common pattern is "this option needs that one to make sense" — letting the
build system fill the dependency is more useful than failing and asking the
user to retry with both names. To express "these two cannot coexist", use
`conflicts` (below) instead.
:::

## Conflicting features

A feature can declare incompatibility with others via
`[feature:NAME] conflicts = ...`. Activating both at the same time aborts
the build with a verbose error message that traces each side back to its
*root originator* — the feature that started the chain that pulled it in
(via `default`, mode-level `features =`, [composite expansion](#composite-features),
or [`requires`](#required-features)):

```ini
[features]
static   = -static
shared   = -shared
embedded = -DEMBEDDED
plugin   = -DPLUGIN

[feature:embedded]
requires = static

[feature:plugin]
requires = shared

[feature:static]
conflicts = shared
```

```bash
fobis build --features embedded,plugin
# → Error: features 'static' (required by 'embedded') and
#          'shared' (required by 'plugin') conflict.
#          Resolve in fobos or pass --features -static (or -shared) to drop one side.
```

A symmetric declaration (`[feature:A] conflicts = B` AND
`[feature:B] conflicts = A`) is fine but redundant — the conflict is detected
either way, and the error is reported once.

A self-conflict (`[feature:X] conflicts = X`) emits a warning and is otherwise
ignored.

## Mutually-exclusive groups

When a project has a small set of *alternative* features (e.g. precision:
single / double / quad; linkage: static / shared) and exactly one should be
active, declare a feature-group:

```ini
[features]
single = -DPRECISION_SINGLE
double = -DPRECISION_DOUBLE
quad   = -DPRECISION_QUAD

[feature-group:precision]
members = single double quad
default = double
```

Without a `default`, the group is enforced **at most one**: zero active members
is fine, two or more is a hard error:

```bash
fobis build --features single,double
# → Error: feature-group 'precision' is mutually-exclusive but has
#          2 active members: 'single', 'double'. Activate exactly one.
```

When the optional `default = X` key is set, the group becomes **exactly one**:
the default fills the group whenever no member would otherwise be active —
including when the group is left empty by composites, `requires`, or modes.
An explicit choice from the user (or any earlier resolution step) suppresses
the default:

```bash
fobis build                     # 'double' auto-activated as group default
fobis build --features single   # 'single' wins; 'double' default suppressed
fobis build --features -double  # group left empty (negation = explicit choice)
```

A group whose `default` was negated stays empty. This is the only way to
opt out of the group while it has a declared default.

::: warning Hard errors stop the build
Conflicts and group violations exit with status 1. They report the user's
own declared invariants — the right behaviour when those break is to fail
loudly so the user fixes the fobos rather than chasing a compile error.
:::

## Combining with build profiles

Features and profiles are independent and compose freely:

```bash
fobis build --build-profile debug --features hdf5
```
