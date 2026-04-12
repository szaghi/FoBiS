# Convention-Based Source Discovery

FoBiS can discover source directories automatically when your project follows
common layout conventions — no `src =` entry required in the fobos file.

## Detected layouts

When no explicit `src` setting is present, FoBiS checks the project root for
these directories in order:

| Directory | Convention |
|---|---|
| `src/` | Most common layout for libraries and tools |
| `source/` | Alternative used by some legacy projects |
| `app/` | Fortran-package-manager (fpm) style |

The first directory that exists and contains at least one Fortran source file
is used. If none of the candidates are found, FoBiS falls back to scanning
the current directory (`.`), which is the pre-discovery behaviour.

A discovery message is printed so you can see what was selected:

```
[auto-discover] using source directory: src/
```

## Explicit `src` always wins

Auto-discovery **never overrides** an explicit `src` setting. If your fobos
file has `src = ./my_sources`, or you pass `--src` on the command line,
discovery is skipped entirely.

## Disabling discovery

```bash
fobis build --no-auto-discover
```

Or in the fobos file:

```ini
[default]
no_auto_discover = true
```

## Example

Given:

```
myproject/
├── fobos
├── src/
│   ├── solver.F90
│   └── mesh.F90
└── tests/
    └── test_solver.F90
```

Running `fobis build` with no `src =` in the fobos file automatically scans
`src/` and compiles `solver.F90` and `mesh.F90`.

Running `fobis test` (which also calls the builder) scans `tests/` explicitly
via the test runner and `src/` for library sources.
