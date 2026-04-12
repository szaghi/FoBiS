# Build Profiles

Named build profiles give you a one-word shorthand for compiler flag sets that
are tedious to type and easy to get wrong — debug, release, address-sanitizer,
and coverage instrumentation.

## Quick start

```bash
# Build with debug flags (bounds checking, backtracing, FP exception trapping)
fobis build --build-profile debug

# Build optimised for production
fobis build --build-profile release

# Build with AddressSanitizer and UndefinedBehaviourSanitizer
fobis build --build-profile asan

# Build with coverage instrumentation (pairs with fobis coverage)
fobis build --build-profile coverage
```

Or set the profile in your fobos mode so you never have to type it:

```ini
[debug]
compiler      = gnu
cflags        = -c
build_profile = debug

[release]
compiler      = gnu
cflags        = -c
build_profile = release
```

## Supported profiles

| Profile | Purpose |
|---|---|
| `debug` | Full checking, backtracing, FP exception traps, maximum warnings |
| `release` | Aggressive optimisation (`-O3`) |
| `asan` | AddressSanitizer + UndefinedBehaviourSanitizer |
| `coverage` | `--coverage` / `-fprofile-arcs` for `gcovr`/`lcov` reports |

## Built-in flag table

List the full flag table at any time:

```bash
fobis build --list-profiles
```

Excerpt:

| Compiler | Profile | cflags |
|---|---|---|
| `gnu` | `debug` | `-O0 -g -fcheck=all -fbacktrace -ffpe-trap=invalid,zero,overflow -Wall -Wextra` |
| `gnu` | `release` | `-O3 -funroll-loops` |
| `gnu` | `asan` | `-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer` |
| `gnu` | `coverage` | `-O0 -g --coverage` |
| `intel` | `debug` | `-O0 -g -check all -traceback -fp-stack-check -warn all` |
| `intel` | `release` | `-O3 -ip -ipo` |
| `nvfortran` | `debug` | `-O0 -g -C -traceback -Minfo=all` |
| `nvfortran` | `release` | `-O4 -fast` |

Supported compilers: `gnu`, `intel`, `intel_nextgen`, `nvfortran`, `nag`, `amd`.

## Flag ordering

Profile flags are **prepended** before your own `cflags`, so your explicit flags
always win:

```ini
[debug]
cflags        = -c -DDEBUG
build_profile = debug
# effective cflags: -O0 -g -fcheck=all ... -c -DDEBUG
```

## Fallback behaviour

- If the `(compiler, profile)` pair is not in the table, FoBiS falls back to the
  `gnu` flags for that profile with a warning.
- An entirely unknown profile name emits a warning and applies no extra flags.
- If no profile is set, behaviour is unchanged from the pre-profile FoBiS.

## CLI override

The `--build-profile` flag always overrides the fobos `build_profile` setting:

```bash
fobis build --mode debug --build-profile release   # uses release flags
```

Note: `--build-profile` is distinct from the existing `--profile` flag, which
enables compiler profiling instrumentation (`-pg`).
