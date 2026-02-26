# Flag Heritage

By default, FoBiS.py uses file timestamps to decide whether to recompile an object. This works well when source files change, but if you only change compiler flags (e.g. switching from `-O0` to `-O3`) the timestamps are unchanged and nothing is recompiled — even though all objects should be rebuilt with the new flags.

*Flag heritage* solves this by saving the current flags to a hidden file and forcing a full recompile whenever they differ from the saved value.

## Enabling flag heritage

### Command line

```bash
FoBiS.py build --cflags_heritage -cflags "-c -O1"
# or the short form
FoBiS.py build -ch -cflags "-c -O1"
```

### fobos file

```ini
[debug]
compiler        = gnu
cflags          = -c -O0 -g
cflags_heritage = True

[release]
compiler        = gnu
cflags          = -c -O3
cflags_heritage = True
```

## Heritage file location

FoBiS.py saves the flags in a hidden file:

- `<build_dir>/<target>.cflags.heritage` — when a target is set
- `<build_dir>/.cflags.heritage` — when no target is set

## Example walkthrough

Given a source tree:

```
src/
├── main.f90
└── lib/
    └── utils.f90
```

**First build** — flags `-c -O1`:

```bash
FoBiS.py build -ch -cflags "-c -O1"
```

FoBiS.py compiles everything and writes `-c -O1` to `.cflags.heritage`.

**Second build** — flags unchanged:

```bash
FoBiS.py build -ch -cflags "-c -O1"
```

FoBiS.py reads `.cflags.heritage`, sees no change, and skips recompilation (timestamps are also up to date).

**Third build** — flags changed to `-c -O3`:

```bash
FoBiS.py build -ch -cflags "-c -O3"
```

FoBiS.py reads `.cflags.heritage`, detects the difference, forces a full recompile, and updates the heritage file to contain `-c -O3`.

**Fourth build** — heritage disabled:

```bash
FoBiS.py build -cflags "-c -O1"
```

Without `-ch`, FoBiS.py checks only timestamps. Since all objects are up to date with respect to sources, nothing is recompiled and the heritage file is **not** updated.

## Notes

- Leading and trailing whitespace in the flags string is ignored during comparison.
- The heritage file is always updated after a successful build (when heritage is enabled).
- Combine with `-force_compile` to unconditionally rebuild regardless of flags or timestamps.
