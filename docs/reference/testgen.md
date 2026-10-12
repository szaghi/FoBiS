# `testgen` command

Generate a test program for the public procedures of a module: a compile-checked skeleton from facts, completed by
the LLM, built and run in a scratch copy of the project, and kept only when it builds, runs and checks something.

```bash
fobis testgen MODULE [options]
```

Guide: [Generating tests](/ai/testgen).

## Options

| Option | Description |
|--------|-------------|
| `-p/--procedure NAME` | Test only this public procedure, generic or type-bound procedure (`binding` or `type%binding`); repeatable |
| `--max N` | Test at most N procedures (default: 8 with the model, all with `--skeleton`) |
| `--skeleton` | No model: print (or with `--apply` write) the compile-checked skeleton: declarations and calls, no checks |
| `--context` | Print what the model would receive, run no model |
| `--apply` | Write the accepted program to the test directory (fobos `[test] test_dir`, default `test/`) as `test_<module>.f90`; an existing file is never overwritten |
| `-o/--output PATH` | Write to this path instead (implies `--apply`) |
| `--retries N` | Attempts after the first one, each with the errors of the previous (default 3) |
| `--timeout SECONDS` | How long a test program may run (default 60) |
| `--format text\|json` | Output format; with `json` the progress goes to stderr |
| `--mode`, `-f/--fobos`, `--fci`, `--src` | The fobos mode (sources, compiler, flags) used to find the module and to build |

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | A program was accepted (or the skeleton built) |
| 1 | No program accepted, the project or the skeleton does not build, no model available, or the output file exists |
| 2 | Module not found, no public procedure to test, or an unknown format |
