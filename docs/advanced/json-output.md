# JSON Output

The `--json` flag makes FoBiS commands emit a single JSON object to **stdout** instead of human-readable progress
messages. This is useful for scripting, CI pipelines, and AI agent workflows that need to parse the result
programmatically; the [MCP server](/ai/mcp) returns the same documents to agents.

| Command | Machine-readable output |
|---|---|
| `fobis build --json` | status, objects compiled, errors; on failure the parsed `diagnostics` and FoBiS's `diagnoses` (below) |
| `fobis clean --json`, `fobis fetch --json` | below |
| `fobis check --json` | the dependency graph check (below) |
| `fobis tree --json` | the dependency tree (below) |
| `fobis test --json` | every test's result, with the facts of each failure (below) |
| `fobis introspect` | JSON by default (see [introspect](/reference/introspect)) |
| `fobis lint --format json` / `sarif`, `fobis review --format json` | findings ([lint](/ai/lint), [review](/ai/review)) |
| `fobis merge-assist --format json` | each conflict's versions and resolution (below) |
| `fobis commit --show-facts --json` | the facts of the staged change (below) |
| `fobis ask --show-context --json` | the retrieved, citable sections of a question (below) |
| `fobis case list --json`, `fobis case run --json`, `fobis provenance --json` | cases, runs with their quantities, provenance (below) |
| `fobis verify --json` | each case compared with its reference (below) |
| `fobis testgen --format json`, `fobis ecosystem impact --format json`, `fobis ecosystem dashboard --json` | see [testgen](/reference/testgen), [ecosystem](/reference/ecosystem) |

With machine output on, FoBiS's own messages and warnings go to **stderr**: stdout holds the JSON document only.

## Usage

```bash
fobis build --json
fobis clean --json
fobis fetch --json
```

`--json` can be combined with any other option:

```bash
fobis build --fobos project.fobos --mode release --json
fobis clean --fobos project.fobos --json
fobis fetch --update --json
```

## Schemas

### `fobis build --json`

```json
{
  "status": "ok",
  "target": "all",
  "objects_compiled": 3,
  "errors": []
}
```

| Field | Type | Description |
|---|---|---|
| `status` | `"ok"` \| `"error"` | Whether the build succeeded |
| `target` | `string` | The `--target` value, or `"all"` when building all programs |
| `objects_compiled` | `integer` | Number of `.o` files newly written in this run |
| `errors` | `string[]` | Compiler error lines and any warning messages emitted during the build |

### `fobis clean --json`

```json
{
  "status": "ok",
  "removed": [
    "build/obj/main.o",
    "build/mod/mymodule.mod"
  ],
  "errors": []
}
```

| Field | Type | Description |
|---|---|---|
| `status` | `"ok"` \| `"error"` | Whether the clean succeeded |
| `removed` | `string[]` | Paths of `.o`, `.mod`, and `.smod` files that were deleted |
| `errors` | `string[]` | Any warning messages emitted during the clean |

### `fobis fetch --json`

```json
{
  "status": "ok",
  "deps_dir": ".fobis_deps",
  "dependencies": [
    { "name": "penf",    "path": ".fobis_deps/penf",    "use": "sources" },
    { "name": "jsonfort","path": ".fobis_deps/jsonfort", "use": "fobos"   }
  ],
  "errors": []
}
```

| Field | Type | Description |
|---|---|---|
| `status` | `"ok"` \| `"error"` | Whether all dependencies were fetched successfully |
| `deps_dir` | `string` | The directory where dependencies were cloned |
| `dependencies` | `object[]` | One entry per dependency (see below) |
| `errors` | `string[]` | Git error messages or build failures |

Each entry in `dependencies`:

| Field | Type | Description |
|---|---|---|
| `name` | `string` | Dependency name (matches the fobos key) |
| `path` | `string` | Absolute path to the cloned directory |
| `use` | `"sources"` \| `"fobos"` | Integration mode |

### Diagnosed build failures

When `fobis build --json` fails, the object also holds:

```json
{
  "status": "error",
  "diagnostics": [
    {"tool": "gnu", "severity": "fatal", "file": "src/p.f90", "line": 2, "column": 5,
     "message": "Cannot open module file 'missing_mod.mod' for reading at (1): No such file or directory"}
  ],
  "diagnoses": [
    {"kind": "missing-module", "summary": "module missing_mod is not available when src/p.f90 is compiled",
     "facts": ["no project source defines module missing_mod, and it is not a known library module."],
     "advice": ["declare the project that provides it in fobos `[dependencies]` and run `fobis fetch`, ..."],
     "diagnostic": {"...": "the message explained"}, "consequences": 0}
  ]
}
```

`diagnostics` are the compiler's and linker's messages parsed (gfortran, ifx, nvfortran, LFortran, GNU ld, lld);
`diagnoses` are what [`build --explain`](/ai/explain) establishes from facts: `missing-module`,
`undefined-reference`, `missing-library`, `wrong-runtime`, `multiple-definition`, `internal-compiler-error`.

### `fobis check --json`

```json
{"status": "error", "files": 3,
 "unresolved": [{"file": "./test/t_bad.f90", "dependency": "nothere", "type": "module"}],
 "warnings": ["warning: the file './test/t_bad.f90' depends on 'nothere' that is unreachable"]}
```

Exit code 1 when a dependency is unresolved.

### `fobis tree --json`

```json
{"name": "StringiFor", "version": "v1.8.0", "deps_dir": "src/third_party",
 "dependencies": [
   {"name": "BeFoR64", "spec": "https://github.com/szaghi/BeFoR64", "version": "v1.2.4",
    "fetched": true, "has_fobos": true, "duplicate": false,
    "dependencies": [{"name": "PENF", "version": "v2.0.1", "...": "..."}]}
 ]}
```

### `fobis test --json`

A real run (one passing test, one out-of-bounds write built with `-fcheck=all`, one test using a missing module),
shortened:

```json
{"status": "error", "test_dir": "test", "passed": 1, "failed": 2,
 "results": [
   {"name": "t_bounds", "status": "failed", "exit_code": 2, "duration": 0.055,
    "crash": {"tool": "gnu", "kind": "bounds",
              "message": "Index '4' of dimension 1 of array 'a' above upper bound of 3",
              "file": "./test/t_bounds.f90", "line": 5,
              "frames": [{"function": "t_bounds", "file": "./test/t_bounds.f90", "line": 5},
                         {"function": "main", "file": "./test/t_bounds.f90", "line": 2}]},
    "notes": [{"kind": "bounds", "summary": "index 4 of array a is above its upper bound 3 at ./test/t_bounds.f90:5"}]},
   {"name": "t_broken", "status": "build-failed", "exit_code": -3,
    "diagnoses": [{"kind": "missing-module", "summary": "module nothere is not available when ./test/t_broken.f90 is compiled"}]},
   {"name": "t_ok", "status": "passed", "exit_code": 0, "duration": 0.001}
 ]}
```

`status` per test: `passed`, `failed` (with the parsed `crash` and FoBiS's `notes`, the facts of
[`test --explain`](/ai/explain#runtime-failures)), `build-failed` (with the build's `diagnostics` and
`diagnoses`), `timeout`, `error`. With `--list`: `{"status": "listed", "tests": [...]}`. Exit code 1 when a
test does not pass.

### `fobis merge-assist --format json`

`operation` (kind, ours, theirs and their names: during a rebase ours is the upstream), then per file its `hunks`
(`base`, `ours`, `theirs` lines and the `resolution`: source, strategy, lines, rationale, confidence, risks,
citations, verified, note), `compiles` (true, false, or null when not checked, with `not_checked_because`) and
the compile errors outside the conflicts; `both_sides_touched`. It asks nothing: `--apply` needs `--yes`.

### `fobis commit --show-facts --json`

`staged`, `scopes` (name, score, reasons), `hints` (type, reason) and per file its status, kind, changed `lines`
by kind (`code`, `omp`, `acc`, `comment`), `procedures` and `interfaces`. Exit code 1 when nothing is staged.

### `fobis ask --show-context --json`

`question` and `sources`: each with its `label` (S1...), `id`, `title` and `text`. No model is run.

### `fobis case run --json`

`results`, one per run: `case`, `variant`, `status` (`ok`, `probe-error`, `failed`, `timeout`, `build-failed`,
`error`), `exit_code`, `elapsed`, `command`, `rundir`, `quantities` (name -> `values`, and `shape` when declared or
known; NaN and infinities as the strings `"nan"`, `"inf"`, `"-inf"`), `probe_errors` (name -> reason), the tails of
`stdout` and `stderr`, `provenance`, and `build` (the `build --json` document) when the build failed. `fobis case
list --json` gives the declared `cases`; `fobis provenance --json` the provenance alone (see
[Cases](/advanced/cases#provenance)).

### `fobis verify --json`

`cases`, each with `case`, `status` (`pass`, `fail`, `no-reference`, `nondeterministic`, `run-failed`, `updated`),
`reference` (path), `quantities` (per quantity: `name`, `status` (`pass`, `fail`, `missing`, `new`, `shape`),
`tolerance`, `count`, `out_of_tolerance`, `max_abs`, `max_rel`, `l2`, `linf`, `worst` {`index`, `value`,
`reference`}, `nonfinite`, `note`), `provenance_changes` (`key: old -> new`), `run` (status, exit code, elapsed,
run directory, probe errors, stderr tail, build document when it failed), `repeat` (quantities that differed
between repeated runs). See [Verifying results](/advanced/verify).

### `fobis query --json`

`kind`, `argument`, `files` (analysed), `notes`, and `items`. Calls (`callers`, `callees`): `caller`, `path`,
`line`, `name` (as written), `kind` (`call`, `function`, `binding`), `resolved` (qualified procedures), `how`
(`contained`, `unique`, `generic`, `binding`, `ambiguous`, `unresolved`), `candidate` (one of several), `text`.
Accesses (`writers`, `readers`): `unit`, `path`, `line`, `is` (local, dummy with intent, host, module variable,
use with rename), `module`, `how` (assignment, read statement, allocate, actual argument with intent). `defines`:
`name`, `kind`, `qualified`, `path`, `line`, `detail`. `uses`: `unit`, `path`, `line`, `only`. `region`/`device`:
`unit`, `path`, `line`, `end_line`, `sentinel`, `construct`, `clauses`, `implicit`. `mpi`: `routine`, `kind`, `unit`,
`path`, `line`. `interface`: `qualified`, `signature`; `generic` + `specifics`; `binding` + `types`. See
[Querying the code](/advanced/query).

### `fobis agents-md --json`

`facts` and `block` (the rendered Markdown, markers included); `files` unless `--print`: per file `path`, `status`
(`created`, `updated`, `appended`, `unchanged`; with `--check`: `current`, `stale`, `no-block`, `missing`) and
`diff` (`--check`, stale). `facts`: `name`, `summary`, `default_mode`, `analysed_mode`, `modes` (per mode `name`,
`compiler`, `builds`, `build_dir`, `optimisation`, `debug`, `checks`, `parallel`, `defines`), `sources`, `files`
(per extension), `modules`, `programs`, `no_implicit_none`, `kinds` (per type `counts`, `origins`, `digits`),
`openmp_files`, `openacc_files`, `device_variables`, `mpi` (binding -> files), `mpi_calls`, `test_dir`, `tests`,
`doctest_modules`, `cases` (`name`, `description`, `runs`, `mode`, `ranks`, `threads`, `quantities`, `tolerance`,
`reference`, `assess`, `budgets`), `references_dir`, `setup`, `lint`, `deps_dir`, `dependencies`, `rules`. See
[Instructions for agents](/advanced/agents-md).

### `fobis diff-run --json`

`ref`, `commit`, `status` (`equivalent` or `differs`), `changed` (per file: `path`, `status` (git letter, `?` for
untracked), the `procedures` whose code changed), `notes`, and `cases`: per case the `verify --json` fields
(`quantities` compared with the revision's run: status, tolerance, errors, `worst` with its index, `nonfinite`),
`status` (`equivalent`, `within-uncertainty`, `differs`, `new-failed`, `old-failed`), `old_run` when the revision's
run failed, `spread` with `--assess` (per quantity `digits` shared by the working tree's variants, `max_rel`, and
for a differing one `within`), `provenance_changes` other than git. `scratch` with `--keep`. See
[Differential execution](/advanced/diff-run).

### `fobis bench --json`

`status` (`ok`, or `fail`: a case failed or is measurably slower), `compare` (the revision, `""`), `commit`, and
`cases`: per case `case`, `mode`, `time` (`wall` or the quantity), `status` (`ok`, `error` with `error`), `stats`
per side (`new`; `old` with `--compare`): `n`, `median`, `mad`, `low`, `high` (95% interval of the median, null
below 6 runs), `halfwidth` (relative), `min`, `max`, `cpu_ratio`, `load_max`, `throughput`, `unit`; `comparison`
(`speedup`, `interval`, `verdict`: `faster`, `slower`, `indistinguishable`, `unknown`; `against`: the revision or
`recorded COMMIT (DATE)`), `notes`, `feedback` (per change `procedure`, `category`, `detail`, `old`, `new`,
`regression`, `scope`: `both`, `added`, `removed`, `lines`), `recorded` (history path with `--record`). `scratch`
with `--keep`. See [Benchmarks](/advanced/bench).

### `fobis profile --json`

`case`, `mode`, `tool` (`gprof`, `callgrind`), `unit` (`s` or `Ir`), `total`, `project_share` (percent of the
total in the analysed sources; null when gprof measured no time), `routines` (`symbol`, `procedure`, `location`,
`self`, `percent`, `calls`; for a callgrind routine outside the sources, `callers`: the project procedures calling it
directly with `calls`, `inclusive` and `percent`), `procedures` and `lines` (callgrind: per project procedure and per source line:
`location`, `procedure`, `self`, `percent`, `text`), `processes` and `imbalance` (gprof, several processes), `notes`,
`run` (`status`, `elapsed`, `rundir`). See [Profiling](/advanced/profile).

### `fobis gate --json`

`status` (`pass`, `fail`), `base` (the base and its merge base, `""` for the working tree against HEAD),
`elapsed`, and `stages`, in order: `stage`, `status` (`pass`, `fail`, `error`: the command gave no JSON,
`skipped`), `advisory`, `fact` (the first failing fact, or why the stage was skipped), `details` (up to 4 more),
`commands` (the nested `fobis` commands), `elapsed`. See [The gate](/advanced/gate).

### `fobis assess --json`

`case`, `mode`, `status` (`ok`, `fail`: a budget failed, `error`: the base run failed, with `error`), `builds`,
`runs`, `families` (per family: `family`, `members`, `failed` members with status and detail, `notes`, and
`quantities`, per quantity: ensembles `digits`, `digits_low` (95%), `digits_median`/`worst` for arrays, `mean`,
`std`, `min`, `max`, `outlier`; precision `against`, `digits`, `base`, `reference`; parallel `nondeterministic`
(configuration, runs, max_rel) and `bitwise_identical`; inputs `elasticity` or `mean`/`std`/`correlation`, and
`ranking`; refinement `levels` (h, value), `orders`, `order`, `convergence`, `extrapolated`, `error`, `gci`,
`asymptotic`), `budgets` (`budget`, `actual`, `ok`, `note`), the `base` quantities and its `provenance`. Infinite
digits (every member equal) are the string `"inf"`. See [Assessing numerical error](/advanced/assess).

### `fobis matrix --json`

`status` (`ok` or `fail`), `counts` (cells per status) and `cells`, one per mode x shadow: `mode`, `shadow`,
`compiler`, `version` (first line of the compiler's `--version` in the cell's environment), `status` (`ok`,
`fail`, `skipped`: compiler missing or setup failed, `unsupported`: no such shadow for the compiler), `reason`,
`setup`, `build` (`status`, the first `problem`), `tests` (`passed`, `failed`, `failures`: name, status,
problem), `cases` (`case`, `status`, `problem`, `verify` {`status`, `failed` quantities}), `recheck` (the
failures run again under the `checks` shadow: `test` or `case`, `status`, `problem`, `crash`). Then
`disagreements`: `case`, `quantity`, `cell`, `baseline` (the first cell that produced it), `status`, `tolerance`,
`max_abs`, `max_rel`, `worst`, `nonfinite`, `note`. Progress lines go to stderr. See
[Shadow modes and the matrix](/advanced/matrix).

## Exit codes

`--json` does not change the exit code behaviour:

- `0` on success — `"status": "ok"`
- `1` on failure — `"status": "error"`, `errors` contains the diagnostics

## Scripting example

Parse the JSON output with `jq`:

```bash
# Build and check status
result=$(fobis build --json)
status=$(echo "$result" | jq -r '.status')
if [ "$status" != "ok" ]; then
  echo "Build failed:"
  echo "$result" | jq -r '.errors[]'
  exit 1
fi
echo "Built $(echo "$result" | jq '.objects_compiled') object(s)"
```

Python example:

```python
import json
import subprocess

result = subprocess.run(
    ["fobis", "build", "--fobos", "fobos", "--json"],
    capture_output=True,
    text=True,
)
data = json.loads(result.stdout)
if data["status"] != "ok":
    raise RuntimeError("Build failed: " + "\n".join(data["errors"]))
print(f"Compiled {data['objects_compiled']} object(s)")
```

## Notes

- All human-readable output is suppressed (or sent to stderr) when `--json` is active.
- Compiler diagnostics written to stderr are captured and included in the `errors` array.
- On build failure the JSON is still printed before FoBiS.py exits with code 1, so the calling process can always parse the output regardless of the exit code.
