# `bench` command

Measure the run time of declared cases, with a confidence interval, against their history or a revision. Guide:
[Benchmarks](/advanced/bench).

```bash
fobis bench [CASE...] [options]
```

| Option | Description |
|--------|-------------|
| `CASE...` | Cases to measure [default: those with a `[bench:NAME]` section, else all] |
| `--compare REF` | Also measure a git revision (scratch copies, runs interleaved) and compare |
| `--feedback` | With `--compare`: diff the compiler's vectorisation and data-movement reports per procedure |
| `--record` | Append the measurement to `<bench_dir>/<case>.jsonl` (not with `--compare`) |
| `--runs N` | Maximum runs per side (overrides `max_runs`) |
| `--mode M` | Build the cases in this mode instead of their own |
| `--keep` | Keep the scratch copies of `--compare` (path printed) |
| `--runner local\|slurm` | Run the programs locally (default) or as Slurm jobs (see [Running on a cluster](/advanced/scheduler)) |
| `--json` | One JSON object (see [JSON output](/advanced/json-output#fobis-bench-json)) |
| `-f/--fobos`, `--fci` | The fobos file |

`[bench:NAME]` keys: `warmup` (1), `min_runs` (10), `max_runs` (50), `target` (0.02: relative half-width of the
median's 95% interval), `max_time` (600 s per side), `time` (`wall` or a quantity name), `work` (`NUMBER [unit]`).
`[verification] bench_dir` (default `verification/bench`).

Exit code 0; 1 when a case fails or is measurably slower than its comparison; 2 for a declaration error, an
unknown case or revision, `--feedback` without `--compare`, `--record` with `--compare`.
