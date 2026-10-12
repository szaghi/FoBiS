# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FoBiS.py is a Python CLI tool that automatically builds modern Fortran projects by parsing source files and resolving inter-module dependency hierarchies. It eliminates the need to manually track module dependencies in makefiles.

## Build and Development Commands

### Common tasks (via Makefile)
```bash
make dev    # pip install -e ".[dev]"
make test   # pytest
make lint   # ruff check + format check (no fixes)
make fmt    # ruff check --fix + ruff format
make clean  # remove dist/, *.egg-info/, .pytest_cache/, .ruff_cache/, __pycache__/
make standalone  # build dist/fobis.pyz — single-file offline zipapp (FoBiS + full typer closure) for air-gapped clusters
```

The `standalone` target vendors the full runtime dependency closure into one `dist/fobis.pyz` (stdlib `zipapp`) so it can be `scp`'d to clusters with no pip/PyPI and run as `python3 fobis.pyz build`. The tag-push CI (`python-package.yml`, `standalone` job) attaches the same archive to each GitHub Release. Requires `fobis/__main__.py` (the package + zipapp entry shim).

### Releasing a new version
```bash
# Requires: git-cliff installed (pipx install git-cliff)
./release.sh --patch    # X.Y.Z → X.Y.Z+1
./release.sh --minor    # X.Y.Z → X.Y+1.0
./release.sh --major    # X.Y.Z → X+1.0.0
./release.sh 3.7.0      # explicit version

# What release.sh does (trunk-based — must be on master):
# 1. Runs ruff lint + format checks (abort if failing)
# 2. Bumps __version__ in fobis/__init__.py
# 3. Regenerates docs/guide/changelog.md via git-cliff (CHANGELOG.md is a symlink to it)
# 4. Runs pytest
# 5. Commits version bump + tags vX.Y.Z
# 6. git push --follow-tags origin master
# 7. Tag push triggers CI: lint → test → build → publish (PyPI via OIDC)
```

### CI / release pipeline

The `python-package.yml` workflow has four jobs:

| Job | Trigger | What it does |
|-----|---------|--------------|
| `lint` | push/PR to master, tag `v*` | ruff check + format |
| `test` | push/PR to master, tag `v*` | pytest on ubuntu + gfortran |
| `build` | push/PR to master, tag `v*` | smoke-test entry points across 3 OS × 4 Python |
| `publish` | tag `v*` only | `python -m build` + PyPI OIDC publish |

PyPI publishing uses [OIDC Trusted Publisher](https://docs.pypi.org/trusted-publishers/) — no API token required. The PyPI project must have a Trusted Publisher configured:
- Repository: `szaghi/FoBiS`
- Workflow: `python-package.yml`
- Environment: `release`

### Building/Running the Project
```bash
# Run directly from source
python fobis/fobis.py build

# Install for development (editable install)
pip install -e ".[dev]"

# Build a distribution (sdist + wheel)
python -m build
```

### Testing
```bash
# Run the full test suite
pytest

# Run a single test file
pytest tests/test_build.py

# Run a specific parametrized case
pytest tests/test_build.py::test_build[1]

# Run with coverage
pytest --cov=fobis --cov-report=term-missing

# Tests require gfortran to be available in PATH
```

### Linting
```bash
# Check for lint issues
ruff check fobis/ tests/

# Check formatting
ruff format --check fobis/ tests/

# Auto-fix lint issues
ruff check --fix fobis/ tests/

# Apply formatting
ruff format fobis/ tests/
```

## Architecture

### Core Components (fobis/)

- **fobis.py**: Main entry point with `run_fobis()` orchestrating all commands (build, clean, install, doctests, rule, fetch, plus the newer commands below)

- **FoBiSConfig.py**: Configuration class that parses CLI arguments and fobos files, manages cflags heritage, and handles interdependent project builds. Contains app metadata (`__appname__`, `__author__`, etc.); `__version__` is imported from `fobis/__init__.py` (single source of truth for `pyproject.toml`). The `_load_fetched_deps()` method auto-loads `.fobis_deps/.deps_config.ini` during `build`: `dependon` entries are appended to `cliargs.dependon` (and their directories added to `cliargs.exclude_dirs` to prevent source-scan overlap); `src` entries are appended to `cliargs.src` when not already covered by an existing source path.

- **cli/** (package): **Typer-based** CLI (migrated from argparse, March 2026). The root Typer `app` lives in `cli/_app.py`; each subcommand is its own module that registers via `@app.command(...)` (or `app.add_typer(...)` for sub-apps). `cli/_options.py` holds shared `Annotated` option types (`FobosOpt`, `FciOpt`, ...), `cli/_completions.py` holds shell-completion callbacks, `cli/_constants.py` holds constants. Each command function assembles an `argparse.Namespace` and stores it in `ctx.obj['cliargs']`; all downstream core code reads `cliargs.*` unchanged. **Command set:** build, clean, rule, install, doctests, fetch, scaffold (sub-app: status/sync/init/list), **check, lint, review, merge-assist, kb (sub-app: list/search/show/notice/build/add/remove), ask, mcp, llm (sub-app: recommended/pull/list/rm/ask/doctor + runtime install/list/remove + serve start/stop/status), test, coverage, tree, introspect, run, cache (sub-app: list/clean/show), commit, ecosystem (sub-app: discover/add/remove/dashboard/graph/exec/fetch/check/scaffold/release)**.

- **cli_parser.py**: Legacy argparse module retained for the backward-compat shim. `_normalize_args()` converts legacy single-dash multi-char options (`-compiler`, `-mode`, `-ex`) to double-dash and normalizes `--build_dir` → `--build-dir` before Typer/Click sees them, preserving 100% CLI back-compat and the test `fake_args` interface. Also defines supported file extensions and compilers.

- **ParsedFile.py**: Parses Fortran source files using regex to extract:
  - Module definitions and submodule relationships
  - `use` statements (filters intrinsic modules like iso_fortran_env)
  - `include` statements
  - Program declarations
  - Creates dependency graphs (optional graphviz output)

- **Builder.py**: Orchestrates compilation with:
  - Parallel compilation via multiprocessing Pool
  - Dependency hierarchy ordering
  - Preprocessor integration (PreForM.py supported)
  - GNU Make file generation
  - Support for static/shared library creation

- **Compiler.py**: Compiler abstraction supporting: gnu, intel, intel_nextgen, g95, opencoarrays-gnu, pgi, ibm, nag, nvfortran, amd, lfortran, custom. Handles MPI, OpenMP, coarray, coverage, and profile flags.

- **Fobos.py**: Parses fobos configuration files (INI format). Supports:
  - Multiple modes (build configurations)
  - Templates for mode inheritance
  - Local variable substitution ($var syntax)
  - Custom rules execution
  - `[dependencies]` section parsed by `get_dependencies()` for the `fetch` command; `get_deps_dir(default='.fobis_deps')` reads an optional `deps_dir` key from this section
  - `[project]` section (optional) parsed by `get_project_info()` → returns `{'name': str, 'authors': [str], 'version': str}` (raw fobos values); authors are newline-separated (configparser continuation lines)
  - `get_version()` resolves the effective version: reads `[project] version` (literal or file path relative to git root), falls back to `git describe --tags --abbrev=0`, warns with fix suggestions when both sources disagree

- **Fetcher.py**: Handles fetching, building, and installing GitHub-hosted FoBiS dependencies:
  - `parse_dep_spec()` parses `"URL [:: branch=X] [:: tag=X] [:: rev=X] [:: mode=X] [:: use=sources|fobos]"` specs
  - `fetch()` clones repos on first run; with `--update` runs `git fetch` + checkout
  - `build_dep()` runs `FoBiS.py build` inside the cloned dependency directory; called only for `use=fobos` deps
  - `save_config()` writes `.fobis_deps/.deps_config.ini`: `use=fobos` deps → `dependon` key; `use=sources` deps → `src` key
  - `load_config()` returns `{'dependon': [...], 'src': [...]}` (keys absent when no entries of that type)
  - `_resolve_url()` converts `user/repo` GitHub shorthand to a full HTTPS URL
  - `install_from_github()` orchestrates clone → build (with `--track_build`) → artifact install (used by `install <repo>`)
  - `_build_dep_tracked()` runs `fobis build --track_build` inside the cloned dir
  - `_install_artifacts()` walks dep dir for `.track_build` files and copies executables/libraries/mod files to prefix

- **Dependency.py**: Simple class representing a single dependency (module or include)

- **Doctest.py**: Extracts and runs inline doctests from Fortran module comments

#### Modules backing the newer commands

- **TestRunner.py** (`TestResult`, `TestRunner`): first-class test runner behind `fobis test`; `--suite` tag filtering; passthrough args
- **Coverage.py** (`CoverageReporter`) + **Gcov.py**: coverage reporting behind `fobis coverage` (html/xml/text/all); gcov markdown reports embed mermaid pie charts
- **Cache.py**: build-artifact cache behind the `fobis cache` sub-app (`list`/`clean`/`show`)
- **Commit.py**: LLM-assisted Conventional-Commit message generation behind `fobis commit` (`--provider ollama|openai` (`--backend` alias), `--url`, `--model`, `--api-key-env`; iterative prompt refinement). Task logic only: `generate(provider, ...)` builds the prompts and calls `provider.chat()`; git failures raise `GitError`/`NothingStagedError` (`CommitError`), never `sys.exit`
- **llm/** (package): provider-agnostic LLM layer (plan: `PLAN-llm.md`, features: `PLAN-ai-features.md`). `Provider` protocol (`chat(messages, *, schema, temperature, seed, max_tokens, on_token) -> Completion`); `OllamaProvider` (native `/api/chat`, schema -> `format`) and `OpenAICompatProvider` (`/v1/chat/completions`, schema -> `response_format.json_schema`) over the stdlib streaming client `http.post_stream`; `FakeProvider` (scripted replies, records calls) for tests; `LLMConfig.from_user_config()` + `get_provider()`; errors under `LLMError` (`ConfigError`/`ApiKeyError`, `ProviderUnavailableError`, `ProviderResponseError`). API keys only via an explicitly named env var (`api_key_env`), never an implicit default. Stdlib only: the zipapp must keep working
- **ai/** (package, phase D of `PLAN-ai-features.md`): LLM features grounded on facts and packs. `grounding.py`: `ContextBundle` (sections + numbered `Source`s, deterministic `render()`, printed by `--show-context`), `claims_schema(labels)` (citations are an ENUM of the bundle's labels `S1..Sn`, so a grammar-constrained server cannot invent one), `check_claims` (keeps claims citing a known label, drops and counts the rest; non-JSON -> insufficient), `render_answer`/`to_json`, `load_prompt(name)` (templates `ai/prompts/*.md` via importlib.resources; package-data in pyproject). `ask.py` + `cli/ask.py` (`fobis ask QUESTION [-p DIR] [--pack] [-k] [--show-context] [--verbose] [--json]`): `route_packs` (a question naming omp/acc/mpi searches that standard's pack + fortran-std, hpc-practice, project), `project_pack(files)` (one pseudo-chunk per named unit: header, args, uses, calls, MPI calls, directives, location; ids relative to cwd), `build_bundle`, `ask` (temperature 0, seed 0). No model is started when retrieval finds nothing or with `--show-context`. `kb/search.py` now folds plurals (`_fold`) and expands query synonyms (`SYNONYMS`: index->iteration, hang->deadlock, gpu->device ...): retrieval remains lexical (documented limit in `docs/ai/ask.md`). `claims_schema(labels, kinds=)` adds a required `kind` enum per claim; `render_answer(groups={kind: heading})` groups by it (unknown kinds under the last heading)
- **build --explain** (phase D2): `utils.check_results` raises `BuildFailed(SystemExit)` (exit 1 as before) carrying the failed commands' outputs; `build_pfile`/`run_fobis_build` record `configuration.build_trace` (`pfiles`, `target`); `run_fobis` catches `BuildFailed` only with `--explain`/`--explain-context` and calls `_explain_build_failure` (not with `--json`). `ai/diagnostics.py`: `parse_diagnostics` (gfortran block + plain form, ifx `file(line): error #N: msg [SYM]`, nvfortran `NVFORTRAN-S-NNNN-msg (file: line)`, LFortran with ANSI stripped, GNU ld undefined/multiple definition with the `in function` context, lld; ICE lines -> severity `ice`), `demangle` (gfortran `__m_MOD_p`, ifx `m_mp_p_`, nvfortran `m_p_` split only against known modules, longest first). `ai/explain.py`: `BuildFacts.scan(sources, deps_dir, defines, ...)` (analysed project files + fetched deps walked separately; `raw_modules` from a regex over the raw text, so a module hidden by an inactive `#if` branch is found; `not_built_reason` from `src`/`exclude`/`exclude_dirs`; lookups memoised), `classify` -> deterministic `Diagnosis` (missing-module, undefined-reference, missing-library, wrong-runtime (runtime symbols of another compiler -> stale objects), multiple-definition, internal-compiler-error) + the errors left; later errors of a file whose module is missing, and all linker errors under a wrong runtime, are `consequences`. "Not linked" uses the target's `pfile_dep_all` + no-module files (FoBiS links what the program reaches through `use`). The first error left -> `build_bundle` (message, compiler/mode/flags, code span with `>` on the error line, enclosing unit's header/uses/declarations, interfaces of project procedures named on the line, <= 2 pack chunks with BM25 score >= 10, clipped to 1500 chars) -> `explain` (kinds cause/fix, prompt `prompts/explain.md`). Scan cost ~5 s on 850 files (only after a failure). Fixtures: GENUINE logs in `tests/build-explain/*.txt` (gfortran 16, ifx 2025.3, nvfortran 26.5, LFortran 0.63; scratch paths stripped) + the `.f90` sources that produced them. The model call is shared by build/run/test: `fobis._model_explanation(configuration, bundle, prompt, ask, header)` (handles `--explain-context`, provider, `LLMError`)
- **ecosystem impact** (phase F1, F10): `fobis/ai/impact.py` + `cmd_ecosystem_impact` in `cli/ecosystem.py` (Ecosystem.py stays self-contained). `module_api(FileUnits)` -> {module: {name: Entity(kind, signature)}}: public procedures (prefixes, args, arg decls, result), generics (`interface name` + specifics), derived types (definition + components from the module statements: types are not units), variables, parameters (+ value); access from `Unit.default_access`, the NEW `Unit.access` map (`public :: a, b` lists; kept out of `decls`, which rules treat as data) and decl attrs. `api_changes(old, new)` removed/changed/added (+ module removed); `project_changes(path, base)` (base = latest tag else HEAD, vs `WORKTREE` via `change.Revision`), then `reexports` (a facade module using a changed module and making the name public changes too, transitively, `via`). `usages_in(project, root, changes, files)`: a use counts when the code references a changed name (only lists + renames), or an only list imports a REMOVED name, or the module was removed; plain use without reference = not affected. `fortran_sources(path)` = `git ls-files -co --exclude-standard` (no fetched deps, no submodule contents: VTKFortran vendors PENF under src/third_party). Scan skipped when nothing is breaking. Text/markdown/json; `--deep` cited summary (kinds breaking/action, prompt `prompts/impact.md`); exit 1 when a dependent is affected
- **merge-assist** (phase E2, F4): `fobis/ai/merge.py` + `cli/merge_assist.py` + `run_fobis_merge_assist`/`_choose_hunks`; prompt `prompts/merge.md`. `operation()` from MERGE_HEAD/REBASE_HEAD/CHERRY_PICK_HEAD/REVERT_HEAD (rebase: stage 2 = upstream, stage 3 = your commit, named so); `conflicted_files` (`--diff-filter=U`); `load_conflict` re-merges stages :2:/:1:/:3: with `git merge-file -p --diff3` (independent of conflictStyle and of user edits) -> `ConflictFile` segments + `Hunk`s. `pre_pass`: ours==base / theirs==base / same / whitespace-only / `merge_uses` (three-way union of use-only lists) / `merge_adjacent` (one side appended or prepended, the other edited the base: medium-confidence DRAFT) / `merge_pins` (fobos [dependencies] tag= -> higher SemVer, only inside that section). Drafts and unresolved hunks go to the model (`build_bundle`: base/ours/theirs/context sources, `intent` = commit messages of each side since the merge base, procedures at the conflict, the draft; `merge_schema` strategy enum + citations enum; `check_proposal` builds ours/theirs/both text itself, rejects custom text with markers, uncited -> confidence low). `verify` compiles syntax-only in a tempdir (`syntax_command` per family; unresolved hunks stand in as ours, their errors ignored; missing module -> ok None "not built"); `resolve_file` retries failing model hunks with the errors (MAX_RETRIES 2). `apply_to_worktree` replaces only the worktree blocks still present, matching a block to a RUN of consecutive hunks (git coalesces neighbouring conflicts into one block); user edits elsewhere untouched; never `git add`. `--yes` accepts pre-pass high + model verified. `replay(clone)` + `scripts/merge_replay.py`: historical merges redone in a temporary worktree of a clone; stats separate high-confidence rules (agreement) from drafts
- **review** (phase E1, F5): `fobis/ai/review.py` + `cli/review.py` + `run_fobis_review`. `change.py` is revision-generic: `Revision(diff args, old, new, root)` (`STAGED` = `--cached`/HEAD/index; `review_revision`: staged, `--base` = merge-base..HEAD, default HEAD vs `WORKTREE`); git pathspecs use `:(top)` (git paths are repo-root relative; cwd may be a subdirectory); `FileChange.added` = new-side line numbers. `diff_scope` (changes + per-file `-U2` diffs), `effective_lines` (a changed directive statement adds its whole region), `in_scope(findings, scope, context, lines)`, `scoped_result`, `render_markdown` (PR comment), `risk_bundle` (diff first, changed windows, touched regions, `fact:dependents#<module>` = files using a module whose procedure header changed, rule docs) -> `risk_summary` (kinds risk/check, prompt `prompts/review.md`). The whole project is linted through `_lint_project` (shared with `run_fobis_lint`; changed files outside the sources added); lint and review share the CLI namespace via `cli.lint.lint_namespace(**fields)`. With `--staged`/`--base` the runner warns when a reviewed file's worktree differs from the reviewed side (line numbers). Exit 1 on error/warning findings in scope
- **commit scope from facts** (phase D4): `fobis/ai/change.py` (deterministic). `staged_changes` (name-status, renames), `hunks` (-U0 old/new line sets), Fortran files lexed on both sides (`git show HEAD:old` / `git show :path`) -> `FileChange.lines` (code / omp / acc / comment-or-blank, removed + added), `procedures` (code lines' units), `interfaces` (procedure header lines). `history_scopes` = path and directory (trailing `/`) -> Counter of conventional scopes of the last 300 non-merge commits, one vote per commit per path. `scope_candidates`: the file's history, or when it has < 3 commits the nearest directory with >= 3 (directories stop below the top level: `src/`, the package), the file's own commits adding 0.5 x share as tie-break; no history -> `path_scope` (dir under src/ or the package); floor 0.15 x best, max 4. Hints: only docs/test/ci/build; only directives -> `perf(omp|acc)` and that model becomes the first scope; only comments -> docs or style; header changed -> breaking?. `Commit.generate(facts=True)`: `ChangeFacts.render()` in the prompt (and refine prompt), `commit_schema(scopes)` restricts the scope to candidates + "", `render_message(data, scopes)` keeps a candidate verbatim (`prism/fnl`; other scopes are still cut to the last path component). CLI `fobis commit --show-facts` (no model), `--no-facts`. ALL git diff/log calls in Commit.py and change.py pass `--no-color` (the user's `color.ui=always` leaked ANSI codes into the stat/diff sent to the model). `tests/test_commit.py`'s `staged` fixture stubs `change_facts` (generate must not read the real cwd's index)
- **lint --deep / --ask** (phase D3): `fobis/ai/deep.py`. `LintResult` now keeps `units` (display path -> FileUnits), `project` (ProjectIndex) and `feedback` (attributed compiler messages) for the review. `group_findings` groups findings by innermost directive region (`regions()`), else enclosing procedure (+-15-line windows for procedures > 120 lines, overlapping windows merged); mechanical families `MECHANICAL_FAMILIES` (OBS, MDN, PRT, STY, LNT) are not sent; regions first. `build_bundle(group, files, project, kb, feedback, question)`: code with finding lines `>`, enclosing declarations, `rule:ID` docs (summary/rationale/bad/good), the rules' `refs` pack chunks (<= 3), `feedback:<path>` messages in range, interfaces of called procedures (`ProjectIndex.procedure`), <= 2 pack chunks searched with the directive text + rule names (BM25 >= 10). Findings labelled F1..Fn; `review_schema` (finding, verdict, source labels as enums; concerns with line). `check_review`: confirmed/dismissed without a valid citation -> `uncertain` (`uncited`), uncited concerns dropped, concern lines outside the group -> None, missing findings -> uncertain "not reviewed". Nothing hidden: the exit status ignores verdicts. `report.render_text(notes=, tail=)` / `render_json(reviews=, review=)` carry the annotations (text/json only; other formats warn). `--deep-max` (default 10; ADAM: 580 groups), `--deep-context`, `--ask QUESTION FILE:LINE` (paths may carry `:LINE`, stripped before discovery; answered with the `ask` prompt and claims schema). One provider for all groups, closed at the end; `LLMError` -> warning, plain report
- **run/test --explain** (phase D2b): `fobis/ai/crash.py`. `parse_crash(stderr, exit_code)` -> `Crash` (tool, kind bounds/pointer/allocation/fpe/segv/gpu/io/error-stop/killed/timeout/signal/exit, message, file/line from the runtime message (gfortran `At line N of file F`, nvfortran `0: msg (file: line)`; Intel from the innermost traceback row), frames (gfortran `#N ... in fn` + `at file:line`, Intel table rows; demangled), bounds `detail`). `optimisation(compiler, cflags)` -> (level, -g, checks): last `-O` wins; defaults gfortran/LFortran 0, nvfortran 1 (0 with -g), Intel 2 (0 with -g). `mode_infos(fobos)` reads every mode's compiler and cflags (templates already applied by Fobos; `$vars` substituted; `build_profile` flags prepended). `RunContext.debug_mode()` = another mode at -O0 with -g (same compiler family, checks, "debug" in the name preferred). `trusted_location`: the runtime message's own line (not Intel) at any optimisation, frames only in an -O0 + -g build: optimised-build backtraces lie (hpc-practice note). `classify_crash` -> notes (located crash with statement/declaration/dummy-caller/empty-pointer facts; `error stop` found by message text in the sources; optimised-build note naming the debug mode or `DEBUG_FLAGS`; known compiler bugs gfortran EFAULT at -O2+, nvfortran 719 + `ProjectIndex.device_variables` allocatable targets of acc `reduction`; gdb advice when nothing locates it) + ask_model. Bundle: failing line span + caller span (debug builds) + declarations + interfaces + <= 2 pack chunks; prompt `prompts/crash.md`. `run --explain` runs the binary through `_run_tee` (stderr echoed + recorded, stdout inherited) and passes `--explain` to its build; `test --explain` explains every failed test (build failures, exit -3, excluded), the model only for the first. Fixtures: GENUINE stderr in `tests/run-explain/` (5 programs x gfortran/ifx/nvfortran x debug/-O3; exit codes in the test's `EXIT` table)
- **llm managed runtime** (harness phase P3, `PLAN-llm.md`): `pins.py` (`PINNED_BUILD` = llama.cpp `b11308`; `ASSETS[(os, arch, variant)] = (Asset(name, sha256), cudart Asset | None)`, GENERATED from `gh api repos/ggml-org/llama.cpp/releases/tags/<build>` digests, never hand-typed; to move the pin regenerate the whole table and run the opt-in real test), `runtime.py` (`platform_key`, `detect_variant` (Metal on Apple silicon, cuda12/13 from `nvidia-smi` "CUDA Version", else cpu), `RuntimeManager(root)`: `install` (download, sha256 vs pin, extract with traversal/symlink checks + tar `filter="data"` when available, flatten the single top dir, CUDA runtime archive into the same dir, `--version` check, `runtime.json`), `installed`, `remove`, `resolve(runtime=pinned|PATH|path, variant)`; `runtime_env` prepends the binary dir to LD_LIBRARY_PATH), `server.py` (`LlamaServer`: loopback, free port, random per-process `--api-key`, `--parallel 1 --no-webui`, own process group, `/health` 503->200 wait, crash -> `ServerStartError` with log tail, bind race retried 3x, stop = SIGTERM to the group then SIGKILL; all live servers stopped at exit and on SIGTERM; `generation_speed()` parses the log's "tokens per second"), `managed.py` (`ManagedProvider`: resolves runtime + model before spawning (both missing -> one error naming both commands), one server per provider object reused across chats, `close()`), `get_provider(cfg, on_status)` builds it for `provider = managed`. **Default provider is `managed`**, default model per provider (`UserConfig.DEFAULT_MODELS`: managed `coder-7b`); a `[llm]` section setting `model`/`url` without `provider` keeps meaning Ollama (`UserConfig.LEGACY_PROVIDER`, protects pre-P3 configs). `UserConfig` default path is resolved at construction (`default_config_path()`), not at import. Commit v2: `Commit.generate(structured=True)` sends `COMMIT_SCHEMA` and renders the header with `render_message` (type enum, scope normalised to a lowercase component name, prefix/period stripped, co-author footers dropped); HTTP 400/422 or non-JSON answers fall back to the free-text pipeline. Callers that build a provider must `close()` it (`run_fobis_commit`, `llm ask/doctor` do). Persistent server (P4): `fobis llm serve start` spawns `LlamaServer(persistent=True)` (no atexit/SIGTERM teardown) and writes `<root>/server.json` (mode 0600: pid, url, api_key, model, model_path, log); `running_state` = record + live pid + `/health` 200 (stale record deleted; `_pid_alive` reaps own zombies); `ManagedProvider.attach()` uses it only when its `model_path` equals the resolved model, and `close()` never stops an attached server; `stop_persistent` kills the process group. Store and runtime are RELOCATABLE: manifest part paths and `runtime.json` `binary` are stored relative (read with `os.path.join`, so old absolute entries still work) — the documented offline-cluster copy depends on it
- **llm/models.py** + `cli/llm.py`: the model store behind `fobis llm` (harness phase P2, `PLAN-llm.md`). Spec `hf:<org>/<repo>[@<rev>]/<file>.gguf`, a local path, or an alias of `RECOMMENDED` (pinned to full commits, Apache-2.0 only; sizes and files verified against the Hub API when added). `HubClient` (stdlib): `resolve_revision` (`/api/models/<repo>/revision/<rev>` -> commit), `file_info` (tree API of the file's folder, sha256 = `lfs.oid`), `download` (`resolve/<commit>/<file>` answers 302 to a CDN on another host; resume via `.part` + `Range`, restart when the server answers 200; an early end of stream is NOT an error in urllib (read returns b"") so `done < size` -> `DownloadError` keeping `.part`; sha256/size mismatch -> `ChecksumMismatchError`, `.part` deleted). `HF_TOKEN` is added with `add_unredirected_header`, so urllib never forwards it to the CDN; `HF_ENDPOINT` for mirrors. `ModelStore(root=$FOBIS_LLM_DIR or ~/.fobis/llm)`: `<root>/models/<org>/<repo>/<commit>/<file>` + `manifest.json` (resolved spec -> repo, revision, file, parts[{path, sha256, size}], pulled_at), atomic writes; `pull` (idempotent, split GGUFs, disk-space check), `locate` (never downloads: `ModelMissingError` with the pull command), `remove` (prunes empty dirs), `entries`. Nothing downloads implicitly. `fobis.main()` dispatches `fobis llm` directly (progress must stream). Errors: `ModelMissingError`, `DownloadError`, `ChecksumMismatchError(DownloadError)`
- **analysis/** (package): statement-level Fortran analysis, NOT a parser (fparser2 cannot parse F2008+ OOP codes; tree-sitter would break the zipapp). `preprocessor.py` resolves `#if/#ifdef/#elif/#define` with the mode's `-D` flags (`parse_defines(_merged_preproc_flags(cliargs))`), unevaluable conditions assumed true + warning; `lexer.py` -> `SourceFile` of logical `Statement`s (continuations joined, comments dropped, `;` split, labels detached, `masked` = lower-case with string contents blanked; `!$omp`/`!$acc` directives as statements with `sentinel`; fixed form truncated at col 72; inline `! fobis: ignore[ID] reason` suppressions); `units.py` -> `FileUnits` tree (module/submodule/program/subroutine/function/module procedure/block data/interface + bodies/fragment) with per-unit facts: args, result, prefixes, implicit none (type/external), decls (`Decl`: type_spec, attrs, dims, init, pointer_init), uses, default access. Tolerant by design: unknown syntax is skipped statement by statement; derived-type and enum bodies are not unit specifications; macro-typed declarations (`VARTYPE(KKP), intent(in) :: q`) are recognised; `regions.py`: OpenMP/OpenACC directive parsing (`parse_directive` -> construct + `{clause: [vars]}`), `regions()` (block constructs to the matching `end`, loop constructs to the following DO nest via `loop_end`, `atomic` to the next statement), helpers `assignment`/`call_name`/`strip_if`; `project.py`: `ProjectIndex` built over ALL linted files before any rule runs (procedures by name + `procedure(name)` when unique, `!$acc routine`/`declare target` device routines, `!$acc declare create` module variables, callees of parallel regions, `mpi_init` vs `mpi_init_thread`, integer kind constants + `real_precision(kind)` (selected_real_kind/real64/kind(1.d0)/chains; PENF `R4P/R8P/R16P` fallback for kind modules outside the linted tree), module arrays, type -> final procedures, `enter data` variables, `mpi_comm_rank` rank variables)
- **lint/** (package): rule engine behind `fobis lint`. `rule.py`: `Rule` registry filled by the `@rule(...)` decorator (id `FAMnnn`, kebab name, severity, summary/rationale/bad/good docs, `equivalent` Fortitude code, `default`), `select_rules(select, ignore)` (prefixes, `ALL`; explicit selection enables opt-in rules); `rules/correctness.py` (COR, G1 + G4), `rules/obsolescent.py` (OBS, G2 + OBS014), `rules/modernisation.py` (MDN/PRT, G3; MDN011/MDN021 carry `Edit` fixes), `rules/style.py` (STY, G4: structure only, never formatting), `rules/fortran.py` (FOR, NUM001), `rules/parallel.py` (OMP/ACC/MPI001), `rules/mpi.py` (MPI002-006: source-order data flow within one unit, whole-array buffers only, rank branches from `ProjectIndex.rank_variables`); `rules/_common.py` helpers (`replacements` builds column-exact `Edit`s on physical lines, comments/strings untouched; `do_loops`/`innermost_loop`, `lookup`/`is_array`). Medium-confidence rules ship opt-in (`default=False`); every default-on rule was checked against the 19-repo corpus noise budget (see PLAN-ai-features.md "A3 as built"); rules get `ctx.project` (cross-file facts); `engine.py`: `analyse`/`check_units`/`lint_text` (one-file project)/`lint_files` (two passes: analyse all, `build_index`, then check)/`discover_files` (always skips `.fobis_deps`, VCS dirs; `.h` files with C markers are skipped into `LintResult.skipped`), `apply_fixes` (`--diff`/`--fix` in `run_fobis_lint._lint_fixes`), suppressions + meta rules LNT001-004, baseline (`fingerprint` = rule|path|normalised statement text, line-independent; count-matched); `report.py`: text/json/sarif 2.1.0/github. Generic rules reimplement the Fortitude catalogue natively (user decision; no dependency). Run with the fobos mode (sources, exclusions, defines); fobos `[lint]` (`Fobos.get_lint_config`: select/ignore/baseline); default baseline `.fobis-lint-baseline.json` when present
- **kb/** (package): knowledge packs behind `fobis kb` (`cli/kb.py` sub-app; never sets `cliargs`). `pack.py`: a pack = `pack.ini` + `NOTICE` + `index.json` (chunks `{id: "pack:doc#slug", doc, heading, text, symbols}`); scopes project `.fobis/kb` > user `$XDG_CONFIG_HOME/fobis/kb` > shipped; shipped packs are read through `importlib.resources` (`shipped_root()`), never `os.listdir`, so they load from the zipapp (regression test with `zipfile.Path`); `PackPath`/`Traversable` is type-only (`importlib.resources.abc` is 3.11+). `build.py`: markdown/skill dir -> pack (drops front matter, "How to Use This Skill", assistant-directed lines; heading chunks capped ~1800 chars; symbols from code spans + constraint ids; `rewrites` regex list). `search.py`: BM25 (heading words x2) + exact-symbol bonus, `neighbours()`. Shipped packs (`fobis/kb/packs/`: fortran-std, openmp, openacc, mpi, hpc-practice; CC-BY-4.0, attribution in pack.ini/NOTICE) are GENERATED by `python scripts/sync_kb.py ~/dotfiles` from the maintainer's skills (records the dotfiles rev; `REWRITES` redirect the skills' references to CLAUDE-*.md / memory notes to the hpc-practice pack). Rule -> pack section links live in `fobis/lint/references.py` (`Rule.refs`, shown by `--explain` and on rule pages); `tests/test_kb.py` fails on a stale reference or on assistant-directed leftovers, and holds the retrieval eval (expected chunk in top 5). After rebuilding packs: re-run the tests, fix references, regenerate `docs/lint-rules`
- **lint/feedback.py** + **lint/rules/feedback.py**: compiler feedback (`fobis lint --compiler-feedback LOG`). `parse_log` reads nvfortran `-Minfo` (`procedure:` headers + `LINE, msg` + indented continuations; no file names) and gfortran `-fopt-info` (`file:line:col: kind: msg`); `attribute` maps nvfortran messages to files through `ProjectIndex.procedures` (line must fall inside the procedure; duplicate names disambiguated by the log's `Compiling <files>` lines) and counts the rest as unattributed. Rules ACC001 implicit data movement, ACC012 sequential device loop, OMP008 implicit target map, PRF001 loop not vectorized (opt-in) read `LintContext.feedback` only. FoBiS never runs the feedback build itself: with a fobos mode the mode's `build_dir` overrides `--build-dir`, so it would overwrite the user's build tree; a missing log prints the exact `fobis build --cflags ... | tee` command. `tests/compiler-feedback/` holds GENUINE logs (nvfortran 26.5, gfortran) captured with `fobis build`
- **mcp_server.py** + `cli/mcp.py`: `fobis mcp`, an MCP server (newline-delimited JSON-RPC 2.0 over stdio; protocol 2025-06-18/2025-03-26/2024-11-05). Tools: lint, list_rules, explain_rule, kb_search, kb_show, introspect, check, build, test. fobos-reading tools run `fobis` as a subprocess (`fobis_command()`: `python -m fobis`, or `python fobis.pyz` from the zipapp) so nothing can print into the protocol stream; rules/kb answered in process; `Server(run=...)` injectable for tests. `fobis.main()` dispatches `fobis mcp` directly (like `ecosystem`): the CliRunner would replace stdin and buffer stdout
- **Cleaner.py**: cleaning-phase controller
- **Externals.py** (`ExternalFlags`): resolved compiler/linker flags for one or more external libraries
- **PkgConfig.py** (`PkgConfigSpec`): generates `.pc` pkg-config files
- **SemVer.py** (`Version`): parsed `major.minor.patch` triple
- **Ecosystem.py** (`Ecosystem`, `Project`, `ProjectStatus`, `Pin`): behind the `fobis ecosystem` sub-app (`cli/ecosystem.py`). Manages a set of interconnected Fortran projects registered in the user config (`[ecosystem] root/projects`, read by `UserConfig.ecosystem_root`/`ecosystem_projects`): dependency graph from each fobos `[dependencies]` (topological levels, cycle report), per-repo status collected concurrently (git with `git -C`, never `chdir`; latest tag + Conventional-Commits bump; CI via `gh`; scaffold drift via `Scaffolder.drift()`; pins = `<deps_dir>/fobos.lock` commit vs the dependency's remote default-branch head), terminal/JSON/HTML (Mermaid) renderers. Self-contained on purpose: it uses the rest of FoBiS only through public interfaces, so it can later be extracted into a separate tool. Like `cache`, the sub-app never sets `ctx.obj['cliargs']`, so no fobos is loaded from the cwd; and `fobis.main()` dispatches `fobis ecosystem ...` to the Typer app directly, bypassing `FoBiSConfig`'s `CliRunner` (which buffers stdout until the end and replaces stdin, so prompts abort) — `run_fobis(fake_args)` still goes through the runner. Release rule: a commit is releasable when it touches a path outside `DEFAULT_RELEASE_EXCLUDE` (`docs/* .github/* *.md scripts/*`, overridable per project with fobos `[ecosystem] release_exclude`); the bump comes from the Conventional-Commits types of the releasable commits only. HTML dashboard: palettes in `Ecosystem.THEMES` (light+dark variant each), `--theme/--mode` or config `[ecosystem] theme/mode`; the page template uses `@@NAME@@` placeholders (not `str.format`) and computes all colours in JS (hue-preserving 4.5:1 contrast fix-up), so pytest cannot see JS bugs — exercise the page script under Node with a stub DOM when changing it. Phase 2 (acting): `run_step` (bash -c, streamed output, signal -> `crashed`), `FobisShim` (PATH launchers so `fobis`/`FoBiS.py` in commands and fobos rules run this FoBiS via `sys.executable -m fobis`), `exec_all`/`fetch_all` in release order, `check_dependents` (stages each transitive dependent in a tempdir from `git ls-files -co --exclude-standard`, with the changed project's working copy in its deps_dir; commands from fobos `[ecosystem] check`, else `rule --ex makecoverage`, else `build`), `scaffold_for` (honours fobos `[scaffold] skip`, also honoured by `fobis scaffold` itself via `Fobos.get_scaffold_config()['skip']`). Phase 3 (release train): `plan_release` (releasable projects in release order, version computed and passed explicitly to each repo's `scripts/release.sh`, pre-flight blockers for the whole train), `run_release_train` (release.sh with inherited stdin so its own prompt reaches the user; verifies tag locally + on remote because release.sh exits 0 when declined -> `aborted`; waits for the GitHub release via `gh release view`; `fetch_all` on direct dependents; stops at first failure, CLI prints a `--from` resume hint). `Scaffolder._confirm`: a prompt that cannot be answered (EOF/no tty) now means NO — never write without consent. Registry editing: `ecosystem add/remove` write through `UserConfig.set_ecosystem_projects()`, a line-based edit of the `projects` key only (configparser.write would drop every comment of the user's config), atomic replace
- **Profiles.py**, **UserConfig.py**, **Colors.py**, **Coverage.py**: supporting infrastructure (build profiles, user config, terminal coloring)

### Data Flow
1. `FoBiSConfig` parses CLI + fobos file -> `cliargs` namespace
2. `parse_files()` creates list of `ParsedFile` objects by scanning source directories
3. `dependency_hierarchy()` (in utils.py) resolves module dependencies between files
4. `Builder.build()` compiles in dependency order, then links

### Key Design Patterns
- Uses `fake_args` parameter in `run_fobis()` to enable programmatic invocation (used heavily in tests)
- Fobos file serves as project-specific makefile replacement (INI format with modes, templates, rules)
- Timestamps used to skip up-to-date objects; volatile libraries trigger rebuilds via MD5 hashing
- `fetch` command stores fetched deps in `.fobis_deps/` and writes `.fobis_deps/.deps_config.ini`; `build` auto-reads this file via `_load_fetched_deps()` before the normal `dependon` machinery runs
- Two per-dependency integration modes (`use=sources` default, `use=fobos`): source mode compiles the dep inline with the project; fobos mode builds the dep as a library and links against it via the `dependon` mechanism

### fetch command

The `fetch` subcommand clones GitHub-hosted FoBiS projects and saves a config file that `build` picks up automatically.

**Fobos `[dependencies]` section:**
```ini
[dependencies]
deps_dir = .fobis_deps                          # optional; overrides --deps-dir default
penf     = https://github.com/szaghi/PENF :: tag=v1.5.0
stdlib   = https://github.com/fortran-lang/stdlib :: tag=v0.5.0 :: use=fobos :: mode=gnu
jsonfort = https://github.com/jacobwilliams/json-fortran :: branch=main :: use=fobos
utils    = https://github.com/certik/fortran-utils :: rev=a1b2c3d
simple   = https://github.com/user/repo
```
Each entry: `name = URL [:: branch=X | tag=X | rev=X] [:: mode=X] [:: use=sources|fobos]`

**Per-dependency `use` option (mutually exclusive, default `sources`):**

| `use=` | `fobis fetch` | `fobis build` | Typical use |
|--------|--------------|---------------|-------------|
| `sources` (default) | clone only | dep dir added to source scan if not already covered; no library build | small/header-like deps compiled inline with the project |
| `fobos` | clone + `FoBiS.py build` | dep fobos added to `dependon`; dep dir added to `exclude_dirs` to prevent double-compile | deps that must be built as a separate library |

**Workflow:**
```bash
FoBiS.py fetch             # clone deps; pre-build use=fobos deps only
FoBiS.py fetch --update    # re-fetch (git pull/checkout) and re-build use=fobos deps
FoBiS.py fetch --no-build  # clone only (skips build even for use=fobos deps)
FoBiS.py build             # auto-reads .fobis_deps/.deps_config.ini:
                           #   src entries  -> appended to cliargs.src
                           #   dependon entries -> appended to cliargs.dependon
                           #                      + dep dir added to exclude_dirs
```

**Storage:** deps are cloned into `deps_dir/<name>/` (default `.fobis_deps/`); `deps_dir` can be set in fobos `[dependencies]` section or via `--deps-dir` CLI flag (CLI takes precedence). The generated `.deps_config.ini` has a `src` key for source-mode deps and a `dependon` key for fobos-mode deps.

### install command (GitHub mode)

When `install` receives a positional `repo` argument it behaves like a package manager: clone → build (with `--track_build`) → install artifacts to a prefix. The existing `install` behaviour (installing previously built local files) is fully preserved when no `repo` is given.

**Usage:**
```bash
fobis install szaghi/FLAP                        # install latest default branch to ./
fobis install szaghi/FLAP --tag v2.0.0 -p ~/.local  # pin to tag, install to ~/.local
fobis install szaghi/FLAP --branch develop --mode gnu
fobis install https://github.com/user/repo --rev a1b2c3d
fobis install szaghi/FLAP --no-build            # clone only
fobis install szaghi/FLAP --update              # re-pull before building
```

**Options added to `install`:** `repo` (positional, optional), `--branch`, `--tag`, `--rev`, `--update`, `--no-build`, `--deps-dir` (default: `~/.fobis/`).

**How it works:** `Fetcher.install_from_github()` calls `fetch()` to clone/update, then `_build_dep_tracked()` to build with `fobis build --track_build`, then `_install_artifacts()` scans for `.track_build` files and copies executables → `prefix/bin/`, libraries → `prefix/lib/`, mod files → `prefix/include/`.

## Documentation infrastructure

- `docs/.vitepress/theme/index.ts` + a markdown fence hook in `docs/.vitepress/config.mts` render ```` ```mermaid ```` blocks client-side with the `mermaid` devDependency (re-rendered on dark-mode toggle). `vitepress-plugin-mermaid` (used by StringiFor/PENF) does NOT support VitePress 2: do not add it. `vite.build.target = 'es2022'` is required by mermaid 11.16+.
- `docs/demo/ecosystem-demo/setup.sh DIR` builds a private 3-project ecosystem (core <- mathx <- app, local bare remotes, fetched deps, tags, scaffolded, a releasable `feat`); `source DIR/env.sh` selects its registry and rewrites `https://github.com/demo/*` to the local remotes via git `url.<base>.insteadOf`, so `fetch`/`release` work offline.
- Lint rule reference: `docs/lint-rules/*.md` + `sidebar.json` are GENERATED from the rule registry by `python docs/scripts/gen_lint_rules.py` and committed (a docs CI job builds with Node only); `tests/test_lint_docs.py` fails when they are stale, so regenerate after any rule change. The fobos *rules* (custom commands) live in `docs/fobos/rules.md`: different concept, hence the `/lint-rules/` path.
- GIFs: `docs/make_gifs.sh` + VHS tapes in `docs/public/gifs/tapes/`; tapes named `*_ecosystem_*` get a fresh demo ecosystem; tapes named `*_llm_*` (`12_llm_commit`) need an LLM directory with the runtime and coder-7b already installed (`FOBIS_LLM_DIR` or `~/.fobis/llm`): `make_gifs.sh` gives them a throwaway managed config and a short symlinked `FOBIS_LLM_DIR`. Look at extracted frames (`ffmpeg -ss N -i x.gif -frames:v 1 f.png`) before keeping a GIF. Record unreleased features with the dev FoBiS first on PATH: `PATH="$(realpath ../.venv/bin):$PATH" bash make_gifs.sh 09 10 11` (absolute: a relative PATH entry breaks once a tape `cd`s into its demo dir). HTML-dashboard screenshots in `docs/public/images/` were taken with the headless Chromium VHS ships (`~/.cache/rod/browser/chromium-*/chrome --headless=new --screenshot`): `--window-size` includes the browser chrome, so the viewport is shorter than asked and a tight height clips the page — capture tall (`--window-size=1200,1000`), then crop (`ffmpeg -vf crop=1200:630:0:0`), and look at the result.

## Test Structure

Tests use **pytest** and live in `tests/`:

| File | Description |
|------|-------------|
| `tests/helpers.py` | Shared helpers: `run_build`, `run_clean`, `make_makefile`, `run_install`, `run_doctest`, `run_rule`, `TESTS_DIR`, `OPENCOARRAYS`, `PREFORM` |
| `tests/conftest.py` | pytest configuration/fixtures |
| `tests/unit/` | Unit tests for individual modules |
| `tests/test_build.py` | 32 parametrized build scenarios |
| `tests/test_clean.py` | 1 clean scenario |
| `tests/test_makefile.py` | 2 Makefile generation scenarios |
| `tests/test_install.py` | 4 install scenarios |
| `tests/test_doctest.py` | 3 doctest scenarios |
| `tests/test_rules.py` | 1 custom rule scenario |
| `tests/test_template.py` | Circular template detection |
| `tests/test_fetch.py` | Fetcher unit tests + 4 integration scenarios |
| `tests/test_scaffold.py` | `scaffold` subcommand (GH #164) |
| `tests/test_tree.py` | `tree` inter-project dependency rendering (GH #167) |
| `tests/test_externals.py` | `Externals` — automatic external library detection (GH #169) |
| `tests/test_semver.py` | `SemVer` — version constraint resolution (GH #171) |
| `tests/test_cache.py` | `Cache` — build artifact cache (GH #172) |
| `tests/test_testrunner.py` | `TestRunner` — first-class test runner (GH #173) |
| `tests/test_run.py` | `run` — build and execute a target (GH #174) |
| `tests/test_multitarget.py` | multi-target builds / `Fobos.get_targets()` (GH #175) |
| `tests/test_profiles.py` | `Profiles` — named build profiles (GH #176) |
| `tests/test_auto_discover.py` | convention-based source-dir auto-discovery (GH #177) |
| `tests/test_pkgconfig.py` | `PkgConfig` — automatic pkg-config file generation (GH #179) |
| `tests/test_coverage.py` | `Coverage` — coverage report generation (GH #180) |
| `tests/test_gcov.py` | `Gcov` — gcov file analysis and reporting |
| `tests/test_features.py` | feature flags — conditional compilation (GH #168) |
| `tests/test_includes.py` | `[include]` directive in fobos files |
| `tests/test_variables.py` | `$variable` substitution + `[varset:NAME]` mechanism |
| `tests/test_compiler_lfortran.py` | first-class LFortran compiler support |
| `tests/test_commit.py` | `Commit` — LLM-assisted commit-message generation |
| `tests/test_analysis.py` | `fobis.analysis` — cpp conditional evaluation, free/fixed-form lexing, directives, suppressions, unit tree and declaration facts |
| `tests/test_lint.py` | `fobis.lint` — positive and negative case per rule (`CASES`; a test fails if a rule has no positive case), suppressions, selection, baseline, the four report formats, CLI via `run_fobis` |
| `tests/test_feedback.py` | compiler feedback — parsing the genuine logs in `tests/compiler-feedback/`, attribution (duplicate names, unattributable), ACC001/ACC012/OMP008/PRF001, CLI |
| `tests/test_mcp.py` | `fobis mcp` — handshake/version negotiation, notifications, errors, tool command lines (fake runner), in-process rule/kb tools, stream serving, one real subprocess lint |
| `tests/test_kb.py` | `fobis.kb` — cleaning/chunking/build guards, scope precedence, BM25 + symbols, shipped-pack quality gates (licence, NOTICE, no assistant-directed text, rule references resolve), retrieval eval, zip loading, `fobis kb` CLI |
| `tests/test_lint_docs.py` | the committed `docs/lint-rules/` pages match the rule registry |
| `tests/test_ai.py` | `fobis.ai`: bundle rendering, claims schema, citation check (kept/dropped/unknown labels/non-JSON), rendering, prompt shipping, plural folding + synonyms, pack routing, project facts on the compiler-feedback fixture, `ask` request shape, `fobis ask` CLI (FakeProvider; `--show-context` and no-match run no model) |
| `tests/test_build_explain.py` | `fobis build --explain`: parsing every genuine log of `tests/build-explain/`, demangling, each deterministic diagnosis (incl. preprocessor-disabled module, fetched dependency, wrong runtime), bundle contents, `explain` request, real gfortran builds through `run_fobis` (excluded module, module never used -> not linked, model path and `--explain-context` on FakeProvider, no `--explain` unchanged) |
| `tests/test_impact.py` | `ecosystem impact`: public API (access lists, generics, types, constants), API changes, a temporary 3-project ecosystem (direct and transitive dependent through a facade module): project changes + re-exports, usages (references, renames, removed name in an only list), reports, CLI incl. `--deep` on FakeProvider |
| `tests/test_merge_assist.py` | `merge-assist` on real temporary git repos (merge, rebase): parse/render, `apply_to_worktree` (user edits kept, coalesced blocks, partial runs), every pre-pass rule (use union three-way, adjacent drafts, pins only in [dependencies]), operation and side names, intent, bundle/schema, `check_proposal`, real gfortran verification (placeholders, missing module), retries on FakeProvider, CLI (report, `--context`, `--apply --yes`, interactive a/t/e with a scripted `$EDITOR`, no tty, no conflict), the index stays unmerged, `replay` stats |
| `tests/test_review.py` | `fobis review` on real temporary git repos: revisions (worktree, staged, base, errors), only changed lines (legacy quiet), changed directive -> whole region, `--context`, markdown, risk bundle (diff, region, dependents), CLI (exit status, staged, base, uncommitted warning, formats, `--deep` on FakeProvider, `--deep-context`) |
| `tests/test_commit_facts.py` | commit scope from facts on real temporary git repos (`color.ui=always`): file kinds, path scope, history scopes (one vote per commit), candidate voting (file, widened directory, tie-break, top-level stop, floor), directive-only -> perf(acc), comment-only, code + interface changes, add/delete/rename, docs-only, schema enum + verbatim hierarchical scope, generate prompt without ANSI codes, `--show-facts` |
| `tests/test_lint_deep.py` | `lint --deep`/`--ask`: grouping (regions first, mechanical families skipped, long-procedure windows), bundle (code marks, declarations, rule docs, pack refs, genuine compiler feedback, called interfaces), schema enums, `check_review` (uncited verdict downgraded, duplicates/unknown labels ignored, concerns), annotations/json, CLI (exit status unchanged, json, context, max, no model, other formats, ask) on FakeProvider |
| `tests/test_run_explain.py` | `run/test --explain`: parsing every genuine runtime capture of `tests/run-explain/`, `optimisation` defaults, `mode_infos`, debug-mode choice, each note (bounds, pointer, error stop for all three runtimes, optimised build, located runtime message at -O3, no location, gfortran EFAULT, nvfortran 719 on a real declare-create reduction), bundle with caller, real gfortran `run`/`test` through `run_fobis` |
| `tests/test_llm_runtime.py` | managed runtime: pins, variant detection, install from synthetic archives (flatten, CUDA runtime, checksum, path traversal, symlink escape, zip, non-pinned build), resolve; `LlamaServer` against a Python stub of llama-server (health wait, 401 without key, crash log tail, timeout kill, port-race retry, SIGTERM -> no orphan); `ManagedProvider`; `fobis llm runtime/ask/doctor`. `@pytest.mark.llm` real test (pinned CPU build + coder-0.5b, schema answer) runs only with `FOBIS_TEST_LLM=1` (`FOBIS_TEST_LLM_DIR` reuses a store) |
| `tests/test_llm_models.py` | model store against a real local fake Hub + CDN (two loopback HTTP servers): revision pinning, subfolders, split GGUFs, resume with `Range` (and restart when ignored), interrupted stream keeps `.part`, checksum mismatch, token never reaches the CDN, gated/404/non-LFS errors, disk space, `fobis llm` CLI |
| `tests/test_llm.py` | `fobis.llm` — streaming client, providers' payloads, `FakeProvider`, `LLMConfig`/`get_provider`, API-key resolution |
| `tests/test_userconfig.py` | `UserConfig` — user-level LLM configuration |
| `tests/test_ecosystem.py` | `Ecosystem` — `fobis ecosystem` (graph, status, pins, CI via mocked `gh`, renderers, CLI) on temporary git repos |
| `tests/test_release_script.py` | the scaffolded `scripts/release.sh` run for real (local bare origin, git-cliff stub, failures injected via `gpg.program=false` or a bad push URL): each failure stage prints a recovery hint that, followed, really recovers |

Fixture directories in `tests/`:
- `build-test{1-32}/`: Build scenarios with fobos files
- `clean-test1/`: Clean functionality
- `makefile-test{1-2}/`: Makefile generation
- `install-test{1-4}/`: Install functionality
- `doctest-test{1-3}/`: Doctest functionality
- `rule-test1/`: Custom rule execution
- `fetch-dep-test{1-4}/`: Fetch dependency integration
- `template-circular-test1/`: Circular template detection

Each fixture directory contains a `fobos` file and Fortran sources.
