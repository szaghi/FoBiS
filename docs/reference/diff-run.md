# `diff-run` command

Run the declared cases on a git revision and on the working tree, both in scratch copies, and compare their
quantities. Guide: [Differential execution](/advanced/diff-run).

```bash
fobis diff-run [REF] [CASE...] [options]
```

| Option | Description |
|--------|-------------|
| `REF` | The revision to compare with: a commit, tag or branch [default: `HEAD`] |
| `CASE...` | The cases to compare [default: all the cases declared in the working tree's fobos] |
| `--mode M` | Build with this mode instead of each case's own |
| `--assess` | For a case that differs, assess the working tree's own spread (the `[assess:CASE]` families, except `inputs` and `refinement`; `rounding` by default) and judge each difference against it |
| `--keep` | Keep the scratch copies (`revision/` and `worktree/`) and print where they are |
| `--runner local\|slurm` | Run the programs locally (default) or as Slurm jobs (see [Running on a cluster](/advanced/scheduler)) |
| `--json` | One JSON object on stdout (see [JSON output](/advanced/json-output#fobis-diff-run-json)); progress on stderr |
| `-f/--fobos`, `--fci` | The fobos file |

| Exit code | Meaning |
|-----------|---------|
| 0 | Every case is equivalent (or, with `--assess`, differs only within the working tree's own spread) |
| 1 | A case differs, or fails to build or run on either side |
| 2 | An unknown revision or case, a bad declaration |
