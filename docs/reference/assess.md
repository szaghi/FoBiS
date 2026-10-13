# `assess` command

Run ensembles of variants of a case and report what their spread says about the accuracy of its quantities. Guide:
[Assessing numerical error and uncertainty](/advanced/assess).

```bash
fobis assess CASE [options]
```

| Option | Description |
|--------|-------------|
| `--families F1,F2` | `precision`, `rounding`, `compiler`, `parallel`, `inputs`, `refinement` [default: the case's `[assess:CASE] families`, else `rounding`] |
| `--samples N` | Monte Carlo samples of the `inputs` family (default: `samples` of the section, else 16) |
| `--jobs N`, `-j N` | Runs at a time (builds are sequential) [default: 1] |
| `--mode M` | Build with this mode instead of the case's own |
| `--runner local\|slurm` | Run the programs locally (default) or as Slurm jobs (see [Running on a cluster](/advanced/scheduler)) |
| `--json` | One JSON object on stdout (see [JSON output](/advanced/json-output#fobis-assess-json)); progress on stderr |
| `-f/--fobos`, `--fci` | The fobos file |

| Exit code | Meaning |
|-----------|---------|
| 0 | The assessment ran and every budget holds (or none is declared) |
| 1 | A budget fails, or the base run of the case is not ok |
| 2 | An unknown case or family, a bad `[assess:CASE]` declaration, a family without what it needs |
