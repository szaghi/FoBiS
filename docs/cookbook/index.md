---
title: Cookbook
---

# Cookbook

Short answers to "how do I ...?". Each recipe gives the fobos lines and the commands, and links to the tutorial
chapter that shows it running and to the guide that covers every option. Every `fobis` command and every fobos mode
key on these pages is checked against FoBiS by the CI (`docs/scripts/check_doc_commands.py`).

| Area | Recipes |
|---|---|
| [Building](./build) | modes for debug and release, one program of many, libraries, compiler flags per compiler, parallel compilation, out-of-tree builds, preprocessing, a Makefile |
| [Dependencies](./dependencies) | a GitHub dependency pinned, building a dependency as a library, a local project, system libraries, reproducible fetches, an air-gapped cluster |
| [Testing](./testing) | test programs, suites, doctests, coverage, catching hidden defects, explained failures |
| [Verifying results](./verification) | the numbers a program prints, references and tolerances, non-determinism, comparing with a revision, accuracy, speed |
| [Code analysis](./analysis) | linting in CI, legacy code, suppressions, who calls what, automatic modernisation, Python bindings |
| [AI assistance](./ai) | a local model, explained errors, questions, tests, reviews, commit messages, merges, an agent |
| [Continuous integration](./ci) | a GitHub Actions workflow, machine-readable output, the gate |
| [HPC and clusters](./hpc) | MPI, OpenMP, GPUs, several compilers, Slurm, profiling |
