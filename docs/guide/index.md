# About FoBiS.py

**FoBiS.py** (Fortran Building System for poor people) is a KISS build tool for modern Fortran projects. It automatically resolves inter-module dependency hierarchies so you never have to track them manually in makefiles.

## The problem it solves

Consider this project layout:

```
└── src
    ├── main.f90          ! program, uses nested_1
    └── nested-1
        ├── first_dep.f90 ! module nested_1, includes second_dep.inc
        └── nested-2
            └── second_dep.inc
```

Writing a correct `Makefile` for this requires knowing the full compilation order, tracking which `.mod` files exist and where, and updating every rule whenever the dependency graph changes. As project size grows, this becomes error-prone and tedious.

**FoBiS.py parses sources on every invocation, builds the complete dependency graph, and compiles in the correct order automatically:**

```bash
FoBiS.py build
```

That single command:

1. Recursively scans `./` for all Fortran sources
2. Parses each file for `module`, `use`, `include`, and `program` statements
3. Resolves the full dependency hierarchy
4. Compiles in the correct order, skipping up-to-date objects
5. Links all programs found

## Key capabilities

- **Automatic dependency resolution** — parses `use` and `include` statements across the full source tree, regardless of nesting or file naming mismatches between modules and files
- **Timestamp-based incremental builds** — only recompiles what changed
- **Multi-compiler support** — GNU, Intel, AMD, IBM, NAG, PGI, NVIDIA, custom
- **Parallel compilation** — independent translation units compiled concurrently with `-j N`
- **fobos configuration file** — INI-style makefile replacement with modes, templates, variables, and custom rules
- **Advanced auto-rebuild triggers** — recompile when flags change (`cflags_heritage`), when libraries change (volatile libs), or when upstream projects change (`dependon`)
- **GitHub dependency fetching** — `FoBiS.py fetch` clones and builds external FoBiS projects declared in the fobos `[dependencies]` section
- **Doctests** — introspective micro unit tests embedded in Fortran doc comments, Python-doctest style
- **GNU Makefile export** — generate a standard `Makefile` from the resolved dependency graph

## How it works

```
CLI args + fobos file
        │
        ▼
  FoBiSConfig      ← parses options, fobos modes, loads fetched deps
        │
        ▼
  parse_files()    ← walks src dirs, parses each .f90/.F90/... file
        │
        ▼
dependency_hiearchy()  ← resolves module/include graph, orders compilation
        │
        ▼
  Builder.build()  ← parallel compile → link
```

## Design philosophy

FoBiS.py follows the KISS principle throughout:

- **Configuration-file-free by default** — `FoBiS.py build` works without any configuration for most projects
- **INI-style fobos** — when configuration is needed, the fobos file uses a simple, human-readable format with no special syntax
- **Same options everywhere** — fobos option names are identical to their CLI switch names; there is no separate concept to learn
- **Composable** — fobos modes, templates, variables, and rules compose cleanly without hidden interactions
