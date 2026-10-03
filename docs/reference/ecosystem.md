# `ecosystem` command

Manage a set of interconnected FoBiS projects: know their state, act across them in dependency
order, release them as a train.

```bash
fobis ecosystem <subcommand> [options]
```

This page is the reference: every subcommand, option, exit code and JSON field. For the concepts,
a guided tour and recipes, read the [Ecosystem guide](/advanced/ecosystem).

## Subcommands

| Group | Subcommand | Purpose | Writes |
|-------|------------|---------|--------|
| Registry | [`discover`](#discover) | list unregistered FoBiS repositories under the root | — |
| | [`add`](#add) | register projects | user config |
| | [`remove`](#remove) | unregister projects | user config |
| Know | [`graph`](#graph) | release order and dependency tree | — |
| | [`dashboard`](#dashboard) | state of every project (terminal, HTML, JSON) | HTML file (`--format html`) |
| Act | [`exec`](#exec) | run a command in every project | whatever the command writes |
| | [`fetch`](#fetch) | `fobis fetch --update` in every project | fetched dependencies, locks |
| | [`check`](#check) | build and test the dependents against a local working copy | temporary copies only |
| | [`scaffold status`](#scaffold-status) | scaffold drift across the projects | — |
| | [`scaffold sync`](#scaffold-sync) | show or apply the scaffold changes | managed files (`--apply`) |
| Release | [`release`](#release) | the release train | commits, tags, pushes (via `release.sh`) |

Every subcommand accepts `--config`/`-c PATH` to use another user configuration file than
`~/.config/fobis/config.ini` (`$XDG_CONFIG_HOME/fobis/config.ini`). The acting commands walk the
projects in **release order** (dependencies first) and stream each command's output live. Colours
are used only on a terminal and honour [`NO_COLOR`](https://no-color.org/).

## Registry

The projects are listed in the `[ecosystem]` section of the user configuration:

```ini
[ecosystem]
root     = ~/fortran
projects = PENF FACE BeFoR64 StringiFor FLAP
theme    = github
mode     = auto
```

| Key | Default | Description |
|-----|---------|-------------|
| `root` | — | Directory the projects live in; `~` is expanded |
| `projects` | — | Directory names under `root`, or `~`/absolute paths; whitespace or newline separated |
| `theme` | `github` | Palette of the HTML dashboard (see [Themes](#themes)) |
| `mode` | `auto` | `auto` (follow the system), `light` or `dark` |

A project is a git repository with a `fobos` file; its name is its directory name. A dependency in
a project's fobos `[dependencies]` is an ecosystem dependency when its key, or the repository name
of its URL, matches a registered project (case-insensitively); any other is reported as external.

### `discover`

```bash
fobis ecosystem discover [--root DIR]
```

List the git repositories with a `fobos` file directly under the root (no recursion) that are not
registered, and print the `fobis ecosystem add ...` command that would register them. Read-only:
pick the candidates you want, not necessarily all.

| Option | Default | Description |
|--------|---------|-------------|
| `-r`, `--root DIR` | the configured `root` | Directory to scan |

Exit codes: `0`; `1` when no root is configured or given, or it is not a directory.

### `add`

```bash
fobis ecosystem add PROJECT...
```

Register projects, given as names under the root or as paths. Each must be a git repository with a
`fobos` file, and its directory name must not be taken by a registered project (the name identifies
the project). An already registered project is reported and skipped. A project directly under
`root` is written as its bare name, any other as a `~/...` (or absolute) path.

Exit codes: `0`; `1` when an argument is invalid — and then **nothing** is written.

### `remove`

```bash
fobis ecosystem remove PROJECT...
```

Unregister projects, given as names (case-insensitive) or paths. The repositories are not touched.
The registered projects that still depend on a removed one are noted: it becomes an external
dependency for them.

Exit codes: `0`; `1` when an argument is not registered — and then **nothing** is written.

::: tip The configuration keeps its comments
`add` and `remove` rewrite only the `projects` key (creating the section, or the file, when
missing); the rest of the file, comments included, is left as it is. The file is replaced
atomically. Long lists wrap onto indented continuation lines.
:::

## Know

### `graph`

```bash
fobis ecosystem graph [--json]
```

Print the release order (dependencies first, grouped in levels) and the dependency tree. A project
sits one level above its deepest dependency. A dependency cycle is reported, and its projects are
left out of the order; repeated subtrees are marked `(*)`.

| Option | Description |
|--------|-------------|
| `--json` | Print the graph as JSON ([schema](#graph-json)) |

Exit codes: `0`; `1` when no project is registered.

### `dashboard`

```bash
fobis ecosystem dashboard [--format terminal|html] [--no-fetch] [--no-ci] [--json]
```

One row per project: git state, release state, CI, scaffold drift, dependency pins.

| Option | Default | Description |
|--------|---------|-------------|
| `--format` | `terminal` | `terminal`: coloured table. `html`: self-contained page written to a file and opened in the browser |
| `-o`, `--output FILE` | `~/.cache/fobis/ecosystem.html` | HTML file to write (`$XDG_CACHE_HOME` honoured) |
| `--no-open` | off | Write the HTML page without opening the browser |
| `--theme NAME` | config `theme`, else `github` | HTML palette ([Themes](#themes)) |
| `--mode MODE` | config `mode`, else `auto` | HTML mode: `auto`, `light` or `dark` |
| `--no-fetch` | off | Skip `git fetch` in every project: faster and offline, but upstream, CI and pins reflect the last fetch |
| `--no-ci` | off | Do not query GitHub Actions (CI shows `unknown`) |
| `-j`, `--jobs N` | `8` | Projects examined concurrently |
| `--json` | off | Print the full status as JSON ([schema](#dashboard-json)) |

Exit codes: `0`; `1` when no project is registered; `2` for an unknown format, theme or mode (theme
and mode are validated only when an HTML page is written).

#### Columns

| Column | Values |
|--------|--------|
| Branch | checked-out branch |
| Tree | `clean`, or `N changed` (changed and untracked files) |
| Upstream | `in sync`, `+ahead/-behind`, `no upstream` |
| Version / tag | the `VERSION` file (else the literal fobos `[project] version`) / the latest reachable tag; highlighted when they differ |
| Unreleased | `0`; `N (bump -> next)` when every commit is releasable; `N, R to release (bump -> next)`; `N, none to release` |
| CI | `passing`, `failing`, `running`, `none` (no run for HEAD), `not pushed` (HEAD not on the remote), `unknown` (no `gh`, not authenticated, not on GitHub) |
| Drift | scaffold-managed files not in sync, project-owned (`[scaffold] skip`) ones excluded; `?` when it cannot be computed |
| Pins | `-` (no ecosystem dependency), `current`, or the dependencies not at their head, with their state |

**CI** is the latest run of every workflow for the HEAD commit (a re-run supersedes the previous
one): `failing` when any concluded otherwise than success, skipped or neutral; `running` when any
is not completed.

**Pins** compare the commit of each ecosystem dependency in the project's `<deps_dir>/fobos.lock`
with that dependency's remote default-branch head: `current`, `stale` (lock behind the head),
`ahead` (lock newer than the known head), `diverged`, `unlocked` (no lock entry), `unknown` (no
remote head).

**Release rule.** A commit since the latest tag is *releasable* when it changes at least one file
outside the release-excluded globs — default `docs/* .github/* *.md scripts/*`, fnmatch patterns on
repository-relative paths where `*` also matches `/`; a project replaces them with fobos
`[ecosystem] release_exclude`. The bump comes from the releasable commits only: a `!` or a
`BREAKING CHANGE` footer → major, `feat` → minor, anything else → patch.

**Project state** (the colour of the HTML diagram nodes), most severe first: `error` (unreadable
project) → `ci-failing` → `stale` (a pin `stale`, `diverged` or `unlocked`) → `unreleased`
(releasable commits) → `ok`.

#### Themes

| `theme` | Light variant | Dark variant |
|---------|---------------|--------------|
| `github` | GitHub Light | GitHub Dark |
| `solarized` | Solarized Light | Solarized Dark |
| `dracula` | Alucard | Dracula |
| `nord` | Snow Storm | Nord |
| `tokyo-night` | Tokyo Night Day | Tokyo Night |
| `catppuccin` | Latte | Mocha |
| `gruvbox` | Gruvbox Light | Gruvbox Dark |
| `one` | One Light | One Dark |
| `rose-pine` | Rosé Pine Dawn | Rosé Pine |

The page's *Theme* and *Mode* selectors switch live; the choice is stored by the browser for that
page and takes precedence over the generated default. Secondary, link and status text is darkened
or lightened, keeping its hue, to a 4.5:1 contrast with the background. Without JavaScript the page
falls back to the GitHub palette, following the system mode. The diagram is drawn by Mermaid,
loaded from a CDN: without network the page still shows the table and the diagram source.

## Act

Shared options:

| Option | Commands | Description |
|--------|----------|-------------|
| `--only A,B` | `exec`, `fetch`, `release`, `scaffold` | Comma-separated projects to act on (still in release order) |
| `--from NAME` | `exec`, `fetch`, `release` | Start from this project in release order: resume after a failure |
| `--fail-fast` | `exec`, `fetch`, `check` | Stop at the first failure; the rest are reported as `not run` |

Every acting command ends with a summary table and exits `1` when a project failed; unknown project
names exit `2`.

```
Project  Result        Time  Detail
PENF     passed        0.0s
FLAP     failed        0.0s  exit 1

1 passed, 1 failed: FLAP
```

| Result | Meaning |
|--------|---------|
| `passed` | the command succeeded |
| `failed` | non-zero exit |
| `crashed` | killed by a signal (the detail names it, e.g. `SIGSEGV`) |
| `aborted` | a release declined at its prompt (`release`) |
| `skipped` | not run: unreadable project, nothing to do, missing dependency |
| `not run` | after a failure (`--fail-fast`, or any failure in `release`) |

### `exec`

```bash
fobis ecosystem exec [--only A,B] [--from NAME] [--fail-fast] -- <command>
```

Run a command in every project's directory through `bash -c`, its output streaming live under a
`==> PROJECT: command` header. A single argument is a shell command line
(`-- 'fobis clean && fobis build'`); several arguments form one command (`-- git status -s`).
`fobis` and `FoBiS.py` in the command, and in the fobos rules it runs, resolve to the FoBiS running
`exec`. Unreadable projects are skipped.

Exit codes: `0`; `1` when a project failed or crashed; `2` without a command or for an unknown project.

### `fetch`

```bash
fobis ecosystem fetch [--only A,B] [--from NAME] [--fail-fast]
```

Run `fobis fetch --update` in every project with a `[dependencies]` section, dependencies first, so
that each lock ends at the current heads. Projects without dependencies are reported as `skipped`.

Exit codes: `0`; `1` when a fetch failed.

### `check`

```bash
fobis ecosystem check PROJECT [--keep] [--fail-fast]
```

Pre-release impact check: build and test every project that depends on `PROJECT`, directly or
transitively, in release order, against `PROJECT`'s **local working copy**. For each dependent:

1. its working copy — tracked and untracked files, uncommitted changes included; ignored files
   (build products, fetched dependencies, `node_modules`) excluded — is copied to a temporary
   directory;
2. its fetched dependencies are copied into the copy's `deps_dir` as they are, together with
   `.deps_config.ini` and `fobos.lock` — except `PROJECT`, copied from its local working copy;
3. its check commands run there, from scratch.

The repositories are never touched. Check commands, in order of precedence:

| Source | Commands |
|--------|----------|
| the dependent's fobos `[ecosystem] check` | one command per line, chained with `&&` |
| a `[rule-makecoverage]` in its fobos | `fobis rule --ex makecoverage` |
| otherwise | `fobis build` |

| Option | Description |
|--------|-------------|
| `--keep` | Keep the staging directory even when every check passes |
| `--fail-fast` | Stop at the first failing dependent |

The staging directory is removed after a full pass and kept, its path printed, otherwise. A
dependent whose dependencies were never fetched is reported as `skipped`.

Exit codes: `0` when every dependent passed (or there is none); `1` otherwise, `skipped` dependents
included; `2` for an unknown project.

### `scaffold status`

```bash
fobis ecosystem scaffold status [--only A,B] [--files GLOB]
```

List, project by project, the [scaffold](/reference/scaffold)-managed files not in sync, and the
project-owned ones (`[scaffold] skip`) as `SKIPPED`.

| Option | Description |
|--------|-------------|
| `--only A,B` | Projects to inspect |
| `--files GLOB` | Limit to managed files matching this glob |

Exit codes: `0` when every project is in sync; `1` when any drifts.

### `scaffold sync`

```bash
fobis ecosystem scaffold sync [--only A,B] [--files GLOB] [--apply [--yes]]
```

Show the scaffold changes project by project; with `--apply`, write them. Files listed in a
project's `[scaffold] skip` are never written.

| Option | Description |
|--------|-------------|
| `--only A,B` | Projects to sync |
| `--files GLOB` | Limit to managed files matching this glob |
| `--apply` | Write the changes (default: only show them) |
| `-y`, `--yes` | With `--apply`: do not ask for each project |

With `--apply` each project's changes are confirmed (default *no*); when no answer is possible (no
terminal) nothing is written and the command exits `1`.

## Release

### `release`

```bash
fobis ecosystem release [--dry-run] [--bump NAME=LEVEL|VERSION]... [--only A,B] [--from NAME]
                        [--yes] [--no-wait] [--timeout SEC] [--no-fetch]
```

The release train.

| Option | Default | Description |
|--------|---------|-------------|
| `--dry-run` | off | Show the plan and stop |
| `--bump NAME=VALUE` | — | Override a bump: `major`, `minor`, `patch`, or an explicit `vX.Y.Z` (repeatable); also adds a project with nothing releasable |
| `--only A,B` | all | Projects to consider |
| `--from NAME` | — | Start from this project in release order |
| `-y`, `--yes` | off | Approve the plan and answer every `release.sh` prompt |
| `--no-wait` | off | Do not wait for the GitHub releases |
| `--timeout SEC` | `900` | Seconds to wait for each GitHub release |
| `--no-fetch` | off | Plan without `git fetch` (not recommended) |

1. **Plan**: the projects with releasable commits (see the release rule above), in release order,
   each with the version it will get — computed from the latest tag and passed explicitly to
   `release.sh`.
2. **Pre-flight** for every planned project; any *blocker* refuses the whole train:

   | Blockers | Warnings |
   |----------|----------|
   | no executable `scripts/release.sh` | unpushed commits |
   | `git-cliff` not found | CI `running`, `none` or `unknown` |
   | not on the trunk branch (the remote default branch) | not fetched |
   | uncommitted changes | not on GitHub |
   | behind the upstream; no upstream | |
   | CI failing at HEAD | |
   | no previous tag and no explicit version | |
   | version not above the current tag; tag already exists | |

3. **Confirmation** of the plan (default *no*; no answer possible means no).
4. **For each project**: `scripts/release.sh vX.Y.Z` with the terminal's stdin, so that its own
   prompt reaches you (`--yes` answers it); the tag must then exist locally **and** on the remote —
   a declined prompt is reported as `aborted`; the GitHub release is awaited with
   `gh release view`; `fobis fetch --update` runs in the project's direct dependents.
5. **Stop at the first failure**, printing the resume command
   `fobis ecosystem release --from NAME [--bump ...]`. Projects already released have nothing left
   to release, so they drop out of the plan.

Exit codes: `0` when every planned project is released, nothing needs a release, the plan is
declined, or `--dry-run` finds no blocker; `1` when a project is blocked, the confirmation cannot be
answered, or a release fails, aborts or is not published in time; `2` for an invalid `--bump` or an
unknown project.

## Per-project configuration

Keys a project can set in its own `fobos`:

```ini
[ecosystem]
check           = fobis build --mode tests-gnu      ; `check` commands, one per line
                  ./scripts/run_tests.sh
release_exclude = docs/* .github/* *.md scripts/*   ; changes that call for no release

[scaffold]
skip = scripts/release.sh                           ; customised files never written by scaffold
```

| Section | Key | Used by | Default |
|---------|-----|---------|---------|
| `[ecosystem]` | `check` | `check` | `fobis rule --ex makecoverage` if defined, else `fobis build` |
| `[ecosystem]` | `release_exclude` | `dashboard`, `release` | `docs/* .github/* *.md scripts/*` |
| `[scaffold]` | `skip` | `ecosystem scaffold`, the dashboard Drift column, plain `fobis scaffold` | none |

## JSON output

### Dashboard JSON

`fobis ecosystem dashboard --json`:

```json
{
  "generated": "2026-10-03T13:39:00",
  "projects": [{ "name": "PENF", "state": "unreleased", "...": "fields below" }],
  "levels": [["PENF", "FACE"], ["BeFoR64", "FLAP"], ["StringiFor"]],
  "release_order": ["PENF", "FACE", "BeFoR64", "FLAP", "StringiFor"],
  "cycle": [],
  "warnings": []
}
```

| Project field | Type | Description |
|---------------|------|-------------|
| `name`, `path`, `slug` | string | project name, absolute path, GitHub `owner/repo` (`""` off GitHub) |
| `branch`, `head` | string | checked-out branch, HEAD commit |
| `dirty` | int | changed and untracked files |
| `ahead`, `behind` | int \| null | commits against the upstream (`null` without one) |
| `fetched` | bool | `git fetch` succeeded in this run |
| `version`, `tag` | string | `VERSION` file, latest reachable tag |
| `unreleased`, `releasable` | int | commits since the tag; those calling for a release |
| `bump` | string \| null | suggested bump (`null` when nothing to release) |
| `next_version` | string | the version the bump leads to (`""` when nothing to release) |
| `pushed` | bool | HEAD is on a remote branch |
| `ci` | string | `passing`, `failing`, `running`, `none`, `not pushed`, `unknown` |
| `drift` | int \| null | scaffold files not in sync (`null` when unknown) |
| `pins` | list | `{dep, locked, head, state}` per ecosystem dependency |
| `errors` | list of string | problems met while reading the project, fetch failures included |
| `state` | string | `error`, `ci-failing`, `stale`, `unreleased`, `ok` |

### Graph JSON

`fobis ecosystem graph --json` prints `{projects, levels, release_order, cycle, warnings}`; every
project carries `name`, `path`, `slug`, `depends_on`, `dependents`, `external` and `error`.
