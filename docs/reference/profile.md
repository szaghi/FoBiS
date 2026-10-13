# `profile` command

Profile a declared case and map the profile to the project's procedures and source lines. Guide:
[Profiling](/advanced/profile).

```bash
fobis profile CASE [options]
```

| Option | Description |
|--------|-------------|
| `--tool gprof\|callgrind\|nsys` | `gprof` (default): sampled time and call counts, `-pg` build; `callgrind`: instructions per function and source line (valgrind); `nsys`: GPU kernel time per directive and host-device transfers (Nsight Systems) |
| `--top N` | Routines, procedures and lines shown [default: 15] |
| `--mode M` | Build the case in this mode; its sources and defines are analysed for the mapping |
| `--runner local\|slurm` | Run the case as a Slurm job ([Running on a cluster](/advanced/scheduler)) |
| `--json` | One JSON object (see [JSON output](/advanced/json-output#fobis-profile-json)) |
| `-f/--fobos`, `--fci` | The fobos file |

Exit code 0; 1 when the build or the run fails, or the profiler wrote nothing; 2 for an unknown case or tool, a
tool not installed, gprof on a case that runs a command, an unknown runner.
