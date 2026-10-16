# About FoBiS

**FoBiS** (the Fortran Building System, command `fobis`) builds modern Fortran projects without a makefile: it parses
the sources, finds which module every file defines and uses, and compiles them in the order that follows. Around that
core it has grown into a tool for the whole life of a Fortran code.

## What it does, by level

| Level | You get | Start with |
|---|---|---|
| Build | dependency-ordered, incremental, parallel builds of programs and libraries; modes in a fobos file; any of a dozen compilers | [First steps](/tutorial/first-steps/01-first-build) |
| Project | dependencies fetched from GitHub and locked, tests, doctests, coverage, external libraries, fpm and Makefile export | [Tutorials](/tutorial/) |
| Many projects | a dashboard of several repositories, commands across them in dependency order, checks downstream, a release train | [Ecosystem](/cookbook/ecosystem) |
| Code quality | a linter aware of the build's defines and of OpenMP, OpenACC and MPI; reviews of a change; queries on the code; verified modernisation | [Linting](/cookbook/analysis) |
| Verification | cases compared with references within tolerances, across compilers and checked builds; error and uncertainty assessment; differential runs; benchmarks; one gate verdict; clusters and profilers | [Verifying results](/cookbook/verification#accept-results-then-catch-a-change) |
| AI assistance | explanations of failures, cited answers, generated tests, merge proposals, on local models; an MCP server for agents | [Analysis and AI](/ai/) |

Each level uses the ones below it, and none is needed to use the others: a project that only wants `fobis build`
never meets a model.

## Design

- **The sources are the configuration.** Dependencies are read from the code on every run: renaming a file or adding a
  module changes nothing to write.
- **One vocabulary.** A fobos key is the command-line option with the same name; there is nothing else to learn.
- **Facts before opinions.** Every check is deterministic and reproducible (the same code gives the same result); what
  a language model adds is labelled as such, cites the facts it was given, and never fails a build on its own.
- **Real outputs.** Machine-readable output (`--json`) for scripts and agents; every output in these pages is the one
  the command printed.

## How these pages are organised

- **Get started**: this page, [Installation](/guide/installation), shell completion, the supported compilers.
- **[Tutorials](/tutorial/)**: one project, grown in tracks from a first build to AI-assisted development. Read them in
  order; the first track is all a new user needs.
- **[Cookbook](/cookbook/)**: everything FoBiS does, by task: how each part works, then one recipe per task, with real
  outputs and the limits worth knowing.
- **[Reference](/reference/)**: every command's options, the [fobos keys](/fobos/), the user configuration, the lint
  rules.
