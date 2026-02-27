# Advanced Topics

This section covers FoBiS.py's more powerful features for large or complex Fortran projects.

## What's here

| Topic | Summary |
|---|---|
| [Parallel Compiling](/advanced/parallel) | Speed up builds with `-j` on multi-core machines |
| [External Libraries](/advanced/libraries) | Link static and shared libraries by path or name |
| [Interdependent Projects](/advanced/interdependent) | Auto-rebuild dependencies with `-dependon` |
| [Volatile Libraries](/advanced/volatile-libs) | Trigger rebuilds when linked libraries change |
| [Flag Heritage](/advanced/cflags-heritage) | Force full rebuild when compiler flags change |
| [PreForM Preprocessing](/advanced/preform) | Integrate the PreForM.py template preprocessor |
| [Doctests](/advanced/doctests) | Embed and run micro-tests inside Fortran comments |
| [GNU Makefile Export](/advanced/makefile) | Export a GNU Makefile from your fobos settings |
| [Fetch Dependencies](/advanced/fetch) | Clone and build GitHub-hosted Fortran deps |
| [GitHub Install](/advanced/install) | One-shot install of a GitHub-hosted FoBiS project |

## When to use advanced features

Most projects only need the basics covered in [Quick Start](/guide/quickstart). Consider the advanced features when you:

- Have a large codebase and want faster incremental builds — **Parallel Compiling**
- Link against pre-built Fortran libraries — **External Libraries**
- Maintain a multi-repo project where library A must be rebuilt before program B — **Interdependent Projects**
- Use external libraries that change frequently (CI-generated artifacts) — **Volatile Libraries**
- Switch between debug/release builds and want reliable full rebuilds — **Flag Heritage**
- Use template-based code generation — **PreForM Preprocessing**
- Want lightweight atomic unit tests living next to the code — **Doctests**
- Need to hand off a GNU Makefile to users without FoBiS.py — **GNU Makefile Export**
- Want a declarative way to pull in GitHub-hosted Fortran libraries — **Fetch Dependencies**
- Want to install a single GitHub-hosted FoBiS project in one step — **GitHub Install**
