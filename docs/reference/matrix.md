# `matrix` command

Build, test and (with `--verify`) run the cases of every fobos mode rebuilt as each shadow, in the environment of
its `[verification] setup` line. Guide: [Shadow modes and the matrix](/advanced/matrix).

```bash
fobis matrix [options]
```

| Option | Description |
|--------|-------------|
| `--modes M1,M2` | The modes (rows) [default: every mode of `[modes]`] |
| `--shadows S1,S2` | The shadows (columns): `none` (the mode's own flags), `checks`, `sanitize`, `strict` [default: `none,checks`] |
| `--compilers C1,C2` | Keep the modes whose compiler (`gnu`, `intel_nextgen`, ...) or family (`gnu`, `intel`, `nvfortran`) is listed |
| `--verify` | Also run the declared cases: each against its reference, and every quantity across cells |
| `--recheck` | Run the failed tests and cases of a cell again under the `checks` shadow |
| `--no-tests` | Do not run the test programs (`fobis test`) |
| `--json` | One JSON object on stdout (see [JSON output](/advanced/json-output#fobis-matrix-json)); progress on stderr |
| `-f/--fobos`, `--fci` | The fobos file |

Every cell builds from scratch (`--force-compile`) in `.fobis/shadow/<mode>-<shadow>/`: the modes' own build
directories are never written.

## fobos

```ini
[verification]
setup =
    nvfortran: source /usr/share/lmod/lmod/init/bash; module load nvhpc/26
    intel_nextgen: source /opt/intel/oneapi/compiler/2025.3/env/vars.sh
    gnu15-release: source /usr/share/lmod/lmod/init/bash; module load gcc/15.2.0
```

One line per mode name, compiler name or compiler family (looked up in that order): bash commands run before the
mode's cells; the environment they leave is the cells' environment. A failing setup skips the mode, with the
commands' last output lines as the reason.

| Exit code | Meaning |
|-----------|---------|
| 0 | Every cell that ran is ok and no quantity disagrees between cells |
| 1 | A cell failed (build, test, case or reference) or a quantity disagrees |
| 2 | An unknown mode or shadow, a bad declaration, `--verify` without cases, no fobos |
