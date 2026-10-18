---
title: Many projects
---

# Many projects

A portability layer used by a string library, used by a parser, used by your application: each in its own
repository, with its own tags, CI and boilerplate, and every change at the bottom rippling upwards. `fobis ecosystem`
manages such a family of FoBiS projects as a whole: it shows the state of every repository, runs commands across them
in dependency order, builds the dependents against an unreleased change, and releases them as a train. `fobis
scaffold` keeps their CI workflows, scripts and documentation configuration identical. The outputs below come from a
private three-project demo you can build in a minute: see [Try it offline](#try-it-offline).

How it works:

1. **The registry.** The ecosystem is an explicit list of local repositories in your user configuration,
   `[ecosystem] root` and `projects`. A project is a git repository with a `fobos` file; its name is its directory name.
   Nothing is managed until you register it.
2. **The graph.** The edges come from each project's own fobos `[dependencies]`, the section `fobis fetch` reads:
   a dependency is an ecosystem dependency when its key or the repository name of its URL matches a registered
   project (case-insensitively), or when it is a `path=` dependency whose directory is one. Any other dependency is
   external: listed, not managed.
3. **The release order.** Projects are grouped in levels, each one level above its deepest dependency. Every acting
   command walks the projects in this order, dependencies first.
4. **The release rule.** A project needs a release when a commit since its latest tag changes a file outside
   `docs/* .github/* *.md scripts/*`; the Conventional Commits types of those commits give the bump.
5. **Nothing written without consent.** `discover`, `graph`, `dashboard` and `impact` only read (the dashboard runs
   `git fetch`, which updates remote-tracking refs only); `check` builds copies. Only `release` commits and pushes,
   after you approve the plan, and a confirmation that cannot be answered (no terminal) counts as no.

Tutorial: [the ecosystem track](/tutorial/ecosystem/01-register). Reference: [`ecosystem`](/reference/ecosystem),
[`scaffold`](/reference/scaffold).

![fobis ecosystem graph and dashboard](/gifs/09_ecosystem_dashboard.gif)

## Register the projects

The registry lives in `~/.config/fobis/config.ini` (`$XDG_CONFIG_HOME/fobis/config.ini` when set; `--config FILE` on
any subcommand reads another):

```ini
[ecosystem]
; the directory the projects live in
root     = ~/fortran
; names under root, or paths; whitespace or newline separated
projects = PENF FACE BeFoR64 StringiFor
           FLAP
```

`discover` lists the git repositories with a fobos file directly under the root (no recursion) that are not
registered yet, and prints the command that would register them. Pick the ones you want, not necessarily all:

<<< @/examples/output/3-ecosystem/01/discover.txt{console}

<<< @/examples/output/3-ecosystem/01/add.txt{console}

```bash
fobis ecosystem discover --root ~/work      # scan another directory
fobis ecosystem add FiNeR ~/work/MyLib      # names under root, or any path
fobis ecosystem remove FiNeR                # the repository itself is not touched
```

- **The name identifies the project.** `add` accepts only git repositories with a fobos file whose directory name no
  registered project has; an already registered one is reported and skipped. A project directly under `root` is
  written as its bare name, any other as a `~/...` or absolute path.
- **All or nothing.** One invalid argument and the configuration is not touched (exit 1). `remove` notes the projects
  that still depend on the one removed: it becomes an external dependency for them.
- **Your comments survive.** `add` and `remove` rewrite only the `projects` key (creating the section or the file when
  missing), atomically; long lists wrap onto continuation lines.
- **No inline comments** in the configuration: `FLAP ; the parser` registers `;`, `the` and `parser` as projects.
- **Two registered directories with the same name:** the second is ignored, with a warning.

## The graph and the release order

<<< @/examples/output/3-ecosystem/01/graph.txt{console}

Level 0 holds the projects with no ecosystem dependency; releasing level by level never releases a project before one
of its dependencies. A subtree shown already is marked `(*)`, and the external dependencies are listed last.

```bash
fobis ecosystem graph --json      # projects (depends_on, dependents, external), levels, release_order, cycle
```

- **A dependency cycle** is printed as `dependency cycle, not ordered: A, B` and its projects are left out of the
  release order; the acting commands still visit them, after all the others. `graph` exits 0 all the same.
- **Exit 1** when no project is registered, for every subcommand that reads the registry.

## The dashboard

One row per project: git state, release state, CI, boilerplate drift, dependency pins.

<<< @/examples/output/3-ecosystem/02/dashboard.txt{console}

| Column | Shows | Look at it when |
|---|---|---|
| Tree | `clean`, or the number of changed and untracked files | not `clean` |
| Upstream | `in sync`, `+ahead/-behind`, or `no upstream` | not in sync |
| Version / tag | the `VERSION` file (else a literal fobos `[project] version`) against the latest reachable tag | they differ (highlighted) |
| Unreleased | commits since the tag, how many are releasable, the bump and the next version | something to release |
| CI | GitHub Actions at HEAD: `passing`, `failing`, `running`, `none` (no run), `not pushed`, `unknown` | `failing` |
| Drift | scaffold-managed files not in sync, project-owned ones excluded (`?` when it cannot be computed) | not 0 |
| Pins | the ecosystem dependencies not at their head, with their state | `stale`, `unlocked`, `diverged` |

The Unreleased cell reads `0`; `N (minor -> v1.1.0)` when every commit is releasable; `N, R to release (...)`; or
`N, none to release` when only docs or CI changed. CI is the latest run of every workflow for the HEAD commit (a
re-run supersedes the previous one): `failing` when any concluded otherwise than success, skipped or neutral,
`running` while any is not completed.

A **pin** compares the commit each project locked in `<deps_dir>/fobos.lock` (written by `fobis fetch`) with the
dependency's remote default-branch head. Ecosystem projects usually follow the default branch of their dependencies,
so a fix at the bottom reaches the dependents without a cascade of version bumps; the pin says whether they are built
against it:

| Pin | Meaning | Fix |
|---|---|---|
| `current` | built against the dependency's head | |
| `stale` | the head has moved on since the last fetch | `fobis ecosystem fetch` |
| `ahead` | the lock is newer than the head FoBiS knows | `git fetch` the dependency (drop `--no-fetch`) |
| `diverged` | lock and head on unrelated histories | inspect the dependency |
| `unlocked` | the dependency was never fetched | `fobis fetch` in the project |
| `unknown` | the dependency has no remote head | push the dependency |
| `NAME at DIR` | a `path=` dependency, used as it is in its directory | |

```bash
fobis ecosystem dashboard                # git fetch in every project first, then the table
fobis ecosystem dashboard --no-fetch     # offline: upstream, CI and pins as of the last fetch
fobis ecosystem dashboard --no-ci        # do not ask GitHub (CI reads unknown)
fobis ecosystem dashboard -j 16          # projects examined at once (default 8)
```

- **The fetch is what makes it right:** ahead/behind, CI at HEAD and the dependency heads are only current after it.
- **CI reads `unknown` everywhere** when [`gh`](https://cli.github.com/) is missing or not authenticated
  (`gh auth status`), or `origin` is not on GitHub. Nothing fails.
- **A pin stays `stale` after a fetch** when the commits are not pushed: pins compare with the dependency's remote head.
- **An unreadable project** (no directory, not a git repository, no fobos, a broken fobos) shows its error across the
  row; the other projects are not affected. Problems met while reading a project (a failed fetch) are noted below
  the table.
- **Each project's state**, most severe first, colours the HTML diagram: `error`, `ci-failing`, `stale` (a pin
  `stale`, `diverged` or `unlocked`), `unreleased` (releasable commits), `ok`.

## The dashboard as JSON and as a web page

For scripts and agents, every field of every project, plus the levels, the release order and any cycle:

<<< @/examples/output/3-ecosystem/02/json.txt{console}

`ahead`/`behind` are `null` without an upstream, `drift` is `null` when unknown, `bump` is `null` and `next_version`
empty when nothing is to release; each pin is `{dep, locked, head, state, path}`; `errors` holds the problems met
while reading the project, failed fetches included. After the projects come `levels`, `release_order`, `cycle` and
`warnings`.

```bash
# the projects with something to release
fobis ecosystem dashboard --no-ci --json | jq -r '.projects[] | select(.releasable > 0) | .name'
```

A self-contained HTML page: the same table with links to each repository, its Actions and its releases, the release
order, and the dependency diagram with every node coloured by its project's state.

<<< @/examples/output/3-ecosystem/02/html.txt{console}

![HTML dashboard, Catppuccin Mocha](/images/ecosystem-dashboard-dark.png)

![HTML dashboard, GitHub Light](/images/ecosystem-dashboard-light.png)

```bash
fobis ecosystem dashboard --format html                       # ~/.cache/fobis/ecosystem.html, opened in the browser
fobis ecosystem dashboard --format html --theme nord --mode dark
```

The page has *Theme* and *Mode* selectors that switch live and are remembered by the browser. Nine palettes, each with
a light and a dark variant: `github` (the default), `solarized`, `dracula` (Alucard / Dracula), `nord` (Snow Storm /
Nord), `tokyo-night`, `catppuccin` (Latte / Mocha), `gruvbox`, `one`, `rose-pine` (Dawn / Rosé Pine). The mode is
`auto` (follow the system, live), `light` or `dark`. Set your defaults in the user configuration:

```ini
[ecosystem]
theme = catppuccin
mode  = auto
```

- **Contrast is enforced:** secondary, link and status text is darkened or lightened, keeping its hue, to a 4.5:1
  contrast with the background.
- **Offline:** the diagram is drawn by Mermaid from a CDN; without network the page shows the table and the diagram
  source. Without JavaScript it falls back to the GitHub palette.
- **`XDG_CACHE_HOME`** moves the default page; `-o FILE` writes elsewhere, `--no-open` does not start a browser.
- **An unknown theme or mode** exits 2 (checked only when a page is written).
- **On WSL** a Windows browser cannot open a `file:///home/...` path: write the page, then open it from Windows.

```bash
fobis ecosystem dashboard --format html --no-open
explorer.exe "$(wslpath -w ~/.cache/fobis/ecosystem.html)"
```

## Run a command in every project

`exec` runs a command in each project's directory through `bash -c`, in release order, its output streaming live
under a `==> PROJECT: command` header, then sums up:

<<< @/examples/output/3-ecosystem/03/exec.txt{console}

<<< @/examples/output/3-ecosystem/03/build.txt{console}

```bash
fobis ecosystem exec -- git status -s                          # several words form one command
fobis ecosystem exec -- 'fobis clean && fobis build'           # one argument is a shell command line
fobis ecosystem exec --only core,mathx --fail-fast -- fobis test
fobis ecosystem exec --from mathx -- fobis test                # resume after a failure
```

| Result | Meaning |
|---|---|
| `passed` | the command succeeded |
| `failed` | non-zero exit |
| `crashed` | killed by a signal (the detail names it, e.g. `SIGSEGV`) |
| `aborted` | a release declined at its prompt (`release` only) |
| `skipped` | not run: unreadable project, nothing to do, a dependency not fetched |
| `not run` | after a failure, with `--fail-fast` (and always in `release`) |

- **`fobis` means this FoBiS.** `fobis` and `FoBiS.py` in the command, and in the fobos rules it runs, resolve to the
  FoBiS running `exec`, not to whichever one the PATH finds first.
- **Exit codes:** 1 when a project failed or crashed; 2 without a command or for an unknown project name.
  `--only` keeps the release order whatever order you list the names in.
- **Clean builds everywhere.** FoBiS skips up-to-date objects, so an object built with other flags can survive a flag
  change: `fobis ecosystem exec -- 'fobis clean && fobis build'` rules that out.

## Bring every dependency to its head

`fetch` runs `fobis fetch --update` in every project with dependencies, dependencies first, so each lock ends at the
current heads and the Pins column turns `current`:

<<< @/examples/output/3-ecosystem/03/fetch.txt{console}

It takes `--only`, `--from` and `--fail-fast` like `exec`; a project with no dependency is `skipped`. More on
`[dependencies]` and the lock file in [Dependencies](./dependencies).

## Check the dependents before releasing

The question before releasing a library is not whether it passes its own tests (its CI answers that) but whether it
breaks the projects that use it. `check` answers it with your **local working copy**, uncommitted changes included,
without touching any repository:

<<< @/examples/output/3-ecosystem/04/check.txt{console}

![fobis ecosystem check](/gifs/10_ecosystem_check.gif)

For every project depending on the checked one, directly or transitively, in release order:

1. its working copy (tracked and untracked files; ignored files such as build products and fetched dependencies
   excluded) is copied to a temporary directory;
2. its fetched dependencies are copied into the copy's `deps_dir` as it fetched them, with `.deps_config.ini` and
   `fobos.lock`, except the checked project, taken from its working copy; a `path=` dependency is copied to the same
   relative place;
3. its check commands run there, chained with `&&`, from scratch: no stale object leaks into the result.

The commands come from the dependent's fobos: `[ecosystem] check`, one command per line; else
`fobis rule --ex makecoverage` when the fobos has a `[rule-makecoverage]` (what the CI runs); else `fobis build`.

```ini
[ecosystem]
check = fobis build --mode tests-gnu
        ./scripts/run_tests.sh
```

A change that breaks a dependent, `twice` renamed `double` in `core` and not committed:

<<< @/examples/output/3-ecosystem/04/broken.txt{console}

```bash
fobis ecosystem check core --keep         # keep the staged copies even when everything passes
fobis ecosystem check core --fail-fast    # stop at the first failing dependent
```

- **The staged copies** are removed after a full pass and kept, their path printed, when a check does not pass.
- **`skipped: dependency X not fetched`:** the dependent never ran `fobis fetch`; run `fobis ecosystem fetch`.
- **Exit 1** unless every dependent passed, `skipped` ones included; 2 for an unknown project. A project nothing
  depends on has nothing to check (exit 0).

## What an API change breaks

`check` builds the dependents; `impact` reads them. It compares the public interface of the project's Fortran modules
between its latest tag (else `HEAD`) and its working tree, then finds every place in the dependents that uses what
changed, without building anything:

<<< @/examples/output/3-ecosystem/04/diff.txt{console}

<<< @/examples/output/3-ecosystem/04/impact.txt{console}

```bash
fobis ecosystem impact core                       # since the latest tag
fobis ecosystem impact core --base v1.0.0         # since another revision
fobis ecosystem impact core --format markdown     # for a release note or an issue
fobis ecosystem impact core --format json
```

- **The public interface** of a module: its public procedures with their signature (prefixes, dummy arguments and
  their declarations, function result), generic interfaces and their specifics, derived types and their components,
  variables, and named constants with their value (a kind constant that changes is an interface change). Default
  access and access lists (`public :: str, strz`) are honoured.
- **Breaking** is a removed or changed entity, or a removed module; an added one is listed, not breaking. When nothing
  breaks, the dependents are not scanned.
- **Re-exports:** a facade module that `use`s a changed module and makes the changed name public changes too,
  transitively (PENF's `penf` re-exports `penf_global_parameters_variables`, and dependents only `use penf`).
- **A dependent is affected** when its code references a changed name (`only` lists and renames resolved), when an
  `only` list imports a removed name, or when it uses a removed module. A plain `use` that never references what
  changed is not affected.
- **Only the dependent's own files** are read (`git ls-files`, tracked and untracked): fetched dependencies and the
  contents of git submodules (vendored copies) are not its code.
- **Exit 1** when a dependent is affected; 2 for an unknown project or format.
- **`--deep`** adds a model summary for the release train (what breaks, what to do), cited on these facts;
  `--deep-context` prints its input and runs no model. See [AI assistance](./ai).

## Shared boilerplate in one project

`fobis scaffold` keeps the boilerplate of a project identical to the templates bundled in FoBiS, with the project's
name and URLs filled in: no template repository, no extra tool.

<<< @/examples/output/3-ecosystem/05/project.txt{console}

```bash
fobis scaffold status                     # every managed file and its state
fobis scaffold status --files "scripts/*" # a glob of managed paths (* also matches /)
fobis scaffold status --strict            # exit 1 on any drift: a CI check
fobis scaffold sync                       # each difference as a diff, then [Y/n] per file
fobis scaffold sync --dry-run             # the diffs, nothing written
fobis scaffold sync --files cliff.toml --yes
fobis scaffold init                       # create every missing managed file
fobis scaffold list                       # the managed files by category
```

<<< @/examples/output/3-ecosystem/05/sync.txt{console}

| State | Meaning |
|---|---|
| `OK` | identical to the template (an init-only file: present) |
| `OUTDATED` | differs from the (rendered) template: `sync` overwrites it |
| `MISSING` | absent: `sync` (or `init`) creates it |
| `SKIPPED` | project-owned through `[scaffold] skip`: never written, not drift |
| `SYMLINK` | `CONTRIBUTING.md` is not a link to its target: `sync` makes it one |
| `PATCH` | a required configuration fragment is missing: `sync` inserts it |
| `MANUAL` | the fragment cannot be inserted unambiguously: `sync` prints it for you to add |
| `UNRENDERED` | a project-owned file still holds `{{VAR}}` placeholders: fill them, or delete it and run `init` |

- **No consent, no write.** `sync` asks per file (Enter means yes); when no answer is possible (no terminal, stdin at
  end of file, CI, a pipe) the answer is no. Unattended runs need `--yes`.
- **`init`** creates `src/`, `docs/`, `.github/workflows/`, `.github/actions/` and `scripts/`, then every missing
  managed file; an existing file is left alone (`exists`). It asks for the project variables it cannot resolve;
  `--yes` asks nothing and leaves them empty.
- **Plain `status` exits 0** whatever drifts; only `--strict` turns drift into exit 1. Pin the FoBiS version in that CI
  job: a FoBiS upgrade with new templates is drift.
- **Stateless:** drift is the SHA-256 of the file against the SHA-256 of the rendered template, nothing recorded.
  Files outside the manifest are never touched.
- **A file it cannot write** (permissions) is reported, the others are still written, and the command exits 1.
- **Then commit by hand:** `git add -A && git commit -m "chore: sync scaffold boilerplate"`.

New project from scratch: `fobis new` (in [Building](./build)) writes a fobos and sources, and `fobis new --scaffold`
adds this boilerplate.

## What scaffold manages

| Category | Files | `sync` |
|---|---|---|
| verbatim | `.github/workflows/ci.yml`, `docs.yml`, `install.yml`, `.github/actions/run-coverage-analysis/action.yml`, `scripts/release.sh`, `scripts/run_tests.sh`, `scripts/install.sh`, `scripts/compute-coverage.sh`, `docs/package.json`, `cliff.toml`, `LICENSE.gpl3.md` | overwrites |
| templated | `.github/workflows/release.yml` (`{{NAME}}`), `.github/actions/setup-build-env/action.yml` (`{{SCAFFOLD_APT_PACKAGES}}`) | overwrites with the rendered text |
| init-only | `fobos`, `fpm.toml`, `docs/ford.md` (rendered when created), `docs/guide/contributing.md` | never: yours after `init` |
| patched | `docs/.vitepress/config.mts` (rendered when created) | only inserts the `build: { target: 'es2022' }` block into `vite: {` |
| symlink | `CONTRIBUTING.md` -> `docs/guide/contributing.md` | creates or repairs the link, never writes through it |

What the files do: `ci.yml` builds and tests; `docs.yml` deploys the VitePress site and the coverage badge;
`release.yml` publishes the release notes when a tag is pushed; `install.yml` smoke-tests the install methods the
project has (make, CMake, FoBiS, fpm) after a release. `scripts/release.sh vX.Y.Z` (or `--patch`/`--minor`/`--major`)
regenerates `CHANGELOG.md` with git-cliff, updates `VERSION` (and the `fpm.toml` version), commits, tags and pushes.
`scripts/run_tests.sh` runs the tests serially, `--np N` under MPI, `--vmem KB` capping each test's memory; a test with
a `<name>.result` file (the doctests) must print that result.

The variables come from the fobos `[project]` section, then from git:

| Variable | fobos `[project]` key | Fallback |
|---|---|---|
| `{{NAME}}` | `name` | the repository name |
| `{{SUMMARY}}` | `summary` | empty |
| `{{REPOSITORY}}` | `repository` | `git remote get-url origin` (SSH turned into HTTPS) |
| `{{REPOSITORY_NAME}}` | (derived) | the last path segment of `{{REPOSITORY}}` |
| `{{WEBSITE}}` | `website` | empty |
| `{{AUTHORS}}` | `authors`, one per line, joined with `, ` | `git config user.name` |
| `{{EMAIL}}` | `email` | `git config user.email` |
| `{{YEAR}}` | `year` (pin the founding year) | the current year |
| `{{DEPENDENCIES}}` | `[dependencies]`, written as fpm dependencies | the git submodules |

```ini
[project]
name       = PENF
summary    = Portability Environment for Fortran
version    = VERSION
repository = https://github.com/szaghi/PENF
website    = https://szaghi.github.io/PENF
email      = stefano.zaghi@cnr.it
year       = 2015
authors    = Stefano Zaghi
             Jane Doe
```

The `[scaffold]` section holds the project's own knobs; without it every file renders to the defaults:

```ini
[scaffold]
; extra system packages for the CI build environment, appended to its apt install line
apt_packages = libopenmpi-dev openmpi-bin zlib1g-dev
; managed files this project owns (globs): reported SKIPPED, never written by sync or init
skip         = scripts/release.sh
```

- **`skip` is for a deliberate customisation** (a `release.sh` that also bumps a CMake version): the file stays out
  of `status --strict`, `sync`, `init`, the dashboard's Drift column and `fobis ecosystem scaffold`.
- **MPI in CI:** the packages go in `apt_packages`; running the tests under `mpirun` is `scripts/run_tests.sh --np N`.
- **Old layouts are replaced:** a `run-coverage` action, an `install.sh` or a `cliff.toml` hardcoding the repository,
  a `release.yml` that also deployed the docs are all `OUTDATED`, and `sync` writes the current files.

## Shared boilerplate across the projects

The same states for every registered project, honouring each one's `skip`:

<<< @/examples/output/3-ecosystem/05/status.txt{console}

<<< @/examples/output/3-ecosystem/05/drift.txt{console}

```bash
fobis ecosystem scaffold status                        # exit 1 when any project drifts
fobis ecosystem scaffold status --only PENF,FACE --files ".github/*"
fobis ecosystem scaffold sync                          # the diffs, project by project: writes nothing
fobis ecosystem scaffold sync --apply                  # confirm each project (default no), then write
fobis ecosystem scaffold sync --files "scripts/*" --apply --yes
```

- **`--apply` without a terminal** writes nothing and exits 1: add `--yes` for an unattended run.
- **After upgrading FoBiS** the new templates show as drift: `pip install -U FoBiS.py`, then `scaffold status`,
  `scaffold sync` to review, `scaffold sync --apply`, and `fobis ecosystem exec -- git status -s` before committing
  in each repository.

## The release train

Releasing a family by hand means: release the bottom library, wait for it, update its dependents' locks, release them,
and so on up the graph. `release` plans the whole train first:

<<< @/examples/output/3-ecosystem/06/plan.txt{console}

![fobis ecosystem release](/gifs/11_ecosystem_release.gif)

1. **The plan.** After a `git fetch` and a CI query, every project with releasable commits, in release order, with the
   version its commits call for, computed from its latest tag. `--bump NAME=major|minor|patch` or
   `--bump NAME=vX.Y.Z` overrides one (repeatable) and brings into the plan a project with nothing releasable.
2. **Pre-flight, for every project before anything runs.** One blocker refuses the whole train, so no ecosystem is
   left half released:

   | Blocks the train | Only warns |
   |---|---|
   | no executable `scripts/release.sh` | unpushed commits (CI has not seen them) |
   | `git-cliff` not on the PATH | CI `running`, `none` or `unknown` |
   | not on the trunk (the remote default branch) | not fetched (`--no-fetch`) |
   | uncommitted changes | not on GitHub (the release cannot be awaited) |
   | behind the upstream, or no upstream | |
   | CI failing at HEAD | |
   | no previous tag and no explicit version | |
   | version not above the current tag, or already tagged | |
   | an unreadable project | |

3. **Confirmation** of the plan as a whole (default no).
4. **For each project:** `scripts/release.sh vX.Y.Z` with the planned version, so the version you approved is the one
   tagged; it runs with your terminal's stdin and asks its own confirmation. Then the tag must exist locally **and**
   on the remote; the GitHub release is awaited (`gh release view`, `--timeout`, default 900 s); and
   `fobis fetch --update` runs in its direct dependents, so the next projects release against the new version.
5. **Stop at the first failure**, the rest `not run`, printing the command that resumes the train:
   `Stopped at FLAP. Fix it, then resume with:` followed by `fobis ecosystem release --from FLAP`, with your
   `--bump` overrides repeated.

<<< @/examples/output/3-ecosystem/06/release.txt{console}

<<< @/examples/output/3-ecosystem/06/after.txt{console}

```bash
fobis ecosystem release --dry-run                     # the plan and its blockers, nothing else
fobis ecosystem release                               # the train
fobis ecosystem release --only core,mathx --bump core=v2.0.0
fobis ecosystem release --no-wait                     # do not wait for the GitHub releases
```

- **A declined prompt is no release.** `release.sh` exits 0 when you answer no; the missing tag reports it `aborted`.
  Nothing was pushed: re-run the train.
- **Resuming never releases twice:** a released project's new tag leaves it nothing to release, so it drops out.
- **`--yes` approves the plan and answers every `release.sh` prompt.** Use it only for an unattended run of a plan
  reviewed with `--dry-run`.
- **The release is awaited only on GitHub with `gh` on the PATH**; otherwise the result says why: `vX.Y.Z pushed
  (GitHub release not awaited: gh is not installed)`, or `not a GitHub project`. Unawaited, the next projects fetch
  the tag while its release may still be building. A release not published within the timeout, or a failed fetch
  in a dependent, fails the project.
- **Your own `release.sh`** works if it takes the version as its only argument, tags and pushes; `git-cliff` is
  required anyway (`pipx install git-cliff`), as the scaffolded script needs it.
- **Exit codes:** 0 when every planned project is released, nothing needs a release, the plan is declined, or a
  `--dry-run` finds no blocker; 1 when a project is blocked, the confirmation cannot be answered, or a release fails,
  aborts or is not published in time; 2 for an invalid `--bump` or an unknown project.

## What calls for a release

Whether a project needs a release is decided by the **files** its commits change; how big a release by their
[Conventional Commits](https://www.conventionalcommits.org/) **type**:

1. A commit since the latest tag is releasable when it changes at least one file outside the excluded globs, by
   default `docs/* .github/* *.md scripts/*` (fnmatch on repository-relative paths, `*` also matching `/`). A docs-only
   or CI-only commit is unreleased but calls for no release, whatever its type; a commit changing no file (a merge,
   an empty commit) does not count.
2. The bump comes from the releasable commits only: a `!` after the type or scope, or a `BREAKING CHANGE` footer, means
   **major**; `feat` means **minor**; anything else, a non-conventional message included, means **patch**.

| Commit | Files changed | Releasable | Bump |
|---|---|:---:|:---:|
| `fix(docs): target es2022` | `docs/package.json`, `scripts/release.sh` | no | |
| `build(fpm): track default branches` | `fpm.toml` | yes | patch |
| `feat(core): add halve()` | `src/core_m.f90` | yes | minor |
| `refactor(api)!: rename twice` | `src/core_m.f90` | yes | major |

Commit types are written by hand and are sometimes wrong; the files a commit touches are not. A project replaces the
globs in its own fobos (the dashboard and `release` both read them):

```ini
[ecosystem]
release_exclude = docs/* .github/* *.md scripts/* examples/*
```

## A change at the bottom of the stack

```bash
# edit PENF, do not commit yet
fobis ecosystem impact PENF                 # which dependents use what changed, file by file
fobis ecosystem check PENF                  # do they still build and pass against the working copy?
git -C ~/fortran/PENF commit -am "feat(io): ..." && git -C ~/fortran/PENF push
fobis ecosystem release --dry-run           # PENF, and anything else that needs a release
fobis ecosystem release
```

A morning look at the family is `fobis ecosystem dashboard` (what changed, what is red, what is stale), then
`fobis ecosystem fetch` to bring every pin to the current heads.

## In CI or a cron job

```bash
fobis ecosystem dashboard --json > ecosystem.json
fobis ecosystem scaffold status             # exit 1 on drift
fobis ecosystem release --dry-run           # exit 1 when a planned release is blocked
```

More in [CI and machine output](./ci).

## Try it offline

The documentation ships a script that builds a small private ecosystem: three Fortran projects (`core` <- `mathx` <-
`app`, and `app` also uses `core`), each a clone of a local bare remote, with history, a `v1.0.0` tag, fetched
dependencies in `third_party/`, the scaffold boilerplate, a minimal `scripts/release.sh`, and commits after the tag
(`core` a releasable `feat`, `mathx` a docs commit, `app` nothing). Nothing leaves the directory you give it, so you
can release, break and repair at will:

```bash
bash docs/demo/ecosystem-demo/setup.sh ~/eco    # the script is in the FoBiS repository
source ~/eco/env.sh                             # the demo registry; its github.com/demo URLs resolve locally
cd ~/eco
fobis ecosystem graph
fobis ecosystem dashboard --no-ci
fobis ecosystem check core
fobis ecosystem release --dry-run
```

<<< @/examples/output/3-ecosystem/01/ls.txt{console}

<<< @/examples/output/3-ecosystem/01/deps.txt{console}

`env.sh` sets `XDG_CONFIG_HOME` to the demo's own configuration, so your registry is never touched, and rewrites
`https://github.com/demo/` to the local remotes with git's `url.<base>.insteadOf`, so `fetch` and `release` work
without network. It needs `git` and `gfortran`, and `git-cliff` for the release pre-flight. Every output on this page
and every GIF was recorded on it. Delete the directory to remove it.

## Configuration at a glance

In the user configuration (`~/.config/fobis/config.ini`):

```ini
[ecosystem]
root     = ~/fortran
projects = PENF FACE BeFoR64 StringiFor
           FLAP
theme    = github
mode     = auto
```

In each project's fobos:

```ini
[ecosystem]
; the commands of fobis ecosystem check, one per line
check           = fobis build --mode tests-gnu
                  ./scripts/run_tests.sh
; changes that call for no release
release_exclude = docs/* .github/* *.md scripts/*

[scaffold]
apt_packages = libopenmpi-dev
skip         = scripts/release.sh
```

The `[project]` keys feed the templates (above) and `version`, the dashboard's Version column; the
`[dependencies]` section is the graph ([Dependencies](./dependencies)).
