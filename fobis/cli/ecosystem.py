"""ecosystem.py — FoBiS.py ``ecosystem`` subcommand group.

Manage a set of interconnected FoBiS projects listed in the user configuration
(``[ecosystem]`` section of ``~/.config/fobis/config.ini``).

Like the ``cache`` sub-app, the commands do their work inside the Typer callbacks and never set
``ctx.obj['cliargs']``: no fobos is loaded from the current directory and the process exits with
the command's exit code.
"""

from __future__ import annotations

import json
import os
import sys
import webbrowser
from typing import Annotated

import typer

ecosystem_app = typer.Typer(
    name="ecosystem",
    help="Manage a set of interconnected FoBiS projects (registry: [ecosystem] in the user config).",
    no_args_is_help=True,
)

ConfigOpt = Annotated[
    str | None,
    typer.Option("--config", "-c", help="User config file [default: ~/.config/fobis/config.ini]"),
]
JsonOpt = Annotated[bool, typer.Option("--json", help="Print machine-readable JSON instead of text")]


def _use_color() -> bool:
    """Colour the output only on a real terminal (FoBiS runs commands inside a CliRunner, whose stdout is not a tty)."""
    stream = sys.__stdout__
    return stream is not None and stream.isatty() and "NO_COLOR" not in os.environ


def _load(config: str | None):
    """Return the user config and the ecosystem it registers; exit 1 when no project is registered."""
    from ..Ecosystem import Ecosystem
    from ..UserConfig import UserConfig

    cfg = UserConfig(path=config)
    paths = cfg.ecosystem_projects
    if not paths:
        typer.echo(
            f"No ecosystem projects registered in {cfg.path}.\n"
            "Add an [ecosystem] section, e.g.\n\n"
            "  [ecosystem]\n  root     = ~/fortran\n  projects = PENF FACE\n\n"
            "or run 'fobis ecosystem discover --root <dir>' to list candidates.",
            err=True,
        )
        raise typer.Exit(1)
    return cfg, Ecosystem(paths)


@ecosystem_app.command("discover")
def cmd_ecosystem_discover(
    root: Annotated[
        str | None,
        typer.Option("--root", "-r", help="Directory to scan [default: the configured ecosystem root]"),
    ] = None,
    config: ConfigOpt = None,
) -> None:
    """List git repositories with a fobos file under the root that are not registered yet.

    Read-only: register the ones you want with 'fobis ecosystem add'.
    """
    from ..Ecosystem import discover
    from ..UserConfig import UserConfig

    cfg = UserConfig(path=config)
    scan_root = os.path.abspath(os.path.expanduser(root)) if root else cfg.ecosystem_root
    if not scan_root:
        typer.echo("No root given: pass --root or set 'root' in the [ecosystem] section of " + cfg.path, err=True)
        raise typer.Exit(1)
    if not os.path.isdir(scan_root):
        typer.echo(f"Not a directory: {scan_root}", err=True)
        raise typer.Exit(1)
    found = discover(scan_root, cfg.ecosystem_projects)
    if not found:
        typer.echo(f"No unregistered FoBiS project under {scan_root}.")
        return
    typer.echo(f"Unregistered FoBiS projects under {scan_root}:")
    for path in found:
        typer.echo(f"  {os.path.basename(path)}")
    entries = " ".join(cfg.ecosystem_entry(p) for p in found)
    typer.echo(f"\nRegister the ones you want to manage (not necessarily all):\n  fobis ecosystem add {entries}")


def _resolve_target(cfg, target: str) -> str:
    """Return the absolute path of an ``add`` argument: a path, else a name under the configured root."""
    path = os.path.expanduser(target)
    if os.path.exists(path):
        return os.path.abspath(path)
    if cfg.ecosystem_root and os.path.exists(os.path.join(cfg.ecosystem_root, target)):
        return os.path.join(cfg.ecosystem_root, target)
    return os.path.abspath(path)


@ecosystem_app.command("add")
def cmd_ecosystem_add(
    projects: Annotated[list[str], typer.Argument(help="Project names under the root, or paths")],
    config: ConfigOpt = None,
) -> None:
    """Register projects in the ecosystem (the [ecosystem] projects list of the user config).

    Each must be a git repository with a fobos file, not registered yet, and with a directory name
    no registered project has (the name identifies the project). Nothing is written unless every
    argument is valid; the rest of the config file, comments included, is left untouched.
    """
    from ..UserConfig import UserConfig

    cfg = UserConfig(path=config)
    registered = {os.path.realpath(p): p for p in cfg.ecosystem_projects}
    names = {os.path.basename(p).lower(): p for p in cfg.ecosystem_projects}
    new_entries, errors = [], []
    for target in projects:
        path = _resolve_target(cfg, target)
        name = os.path.basename(path)
        if not os.path.isdir(path):
            errors.append(f"{target}: no such directory ({path})")
        elif not os.path.exists(os.path.join(path, ".git")):
            errors.append(f"{target}: not a git repository")
        elif not os.path.isfile(os.path.join(path, "fobos")):
            errors.append(f"{target}: no fobos file")
        elif os.path.realpath(path) in registered:
            typer.echo(f"{name}: already registered")
        elif name.lower() in names:
            errors.append(f"{target}: the name {name} is already taken by {names[name.lower()]}")
        else:
            names[name.lower()] = path
            registered[os.path.realpath(path)] = path
            new_entries.append(cfg.ecosystem_entry(path))
    if errors:
        for error in errors:
            typer.echo(error, err=True)
        typer.echo(f"Nothing registered: {cfg.path} is unchanged.", err=True)
        raise typer.Exit(1)
    if not new_entries:
        return
    cfg.set_ecosystem_projects(cfg.ecosystem_entries + new_entries)
    typer.echo(f"Registered {', '.join(new_entries)} in {cfg.path}")
    typer.echo("See where they sit: fobis ecosystem graph")


@ecosystem_app.command("remove")
def cmd_ecosystem_remove(
    projects: Annotated[list[str], typer.Argument(help="Registered project names, or paths")],
    config: ConfigOpt = None,
) -> None:
    """Unregister projects (the repositories themselves are not touched).

    Nothing is written unless every argument names a registered project.
    """
    from ..Ecosystem import Ecosystem
    from ..UserConfig import UserConfig

    cfg = UserConfig(path=config)
    entries = cfg.ecosystem_entries
    paths = [cfg.ecosystem_path(e) for e in entries]
    drop: set[int] = set()
    for target in projects:
        target_path = os.path.realpath(os.path.expanduser(target))
        match = [
            i
            for i, p in enumerate(paths)
            if os.path.basename(p).lower() == target.lower() or os.path.realpath(p) == target_path
        ]
        if not match:
            typer.echo(f"{target}: not registered. Nothing removed: {cfg.path} is unchanged.", err=True)
            raise typer.Exit(1)
        drop.update(match)
    removed = [os.path.basename(paths[i]) for i in sorted(drop)]
    eco = Ecosystem(paths)
    for name in removed:
        users = [d for d in eco.dependents(name) if d not in removed]
        if users:
            verb = "depends" if len(users) == 1 else "depend"
            typer.echo(f"note: {', '.join(users)} still {verb} on {name}; it becomes an external dependency")
    cfg.set_ecosystem_projects([e for i, e in enumerate(entries) if i not in drop])
    typer.echo(f"Unregistered {', '.join(removed)} from {cfg.path}")


@ecosystem_app.command("dashboard")
def cmd_ecosystem_dashboard(
    format: Annotated[
        str,
        typer.Option("--format", help="Output format: terminal or html", case_sensitive=False),
    ] = "terminal",
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="HTML file to write [default: ~/.cache/fobis/ecosystem.html]"),
    ] = None,
    no_open: Annotated[bool, typer.Option("--no-open", help="Write the HTML page without opening the browser")] = False,
    no_fetch: Annotated[
        bool,
        typer.Option("--no-fetch", help="Skip 'git fetch': faster and offline, but upstream, CI and pins may be old"),
    ] = False,
    no_ci: Annotated[bool, typer.Option("--no-ci", help="Do not query GitHub Actions (CI shows 'unknown')")] = False,
    theme: Annotated[
        str | None,
        typer.Option(
            "--theme", help="HTML palette (see the [ecosystem] theme key) [default: from config, else github]"
        ),
    ] = None,
    mode: Annotated[
        str | None,
        typer.Option("--mode", help="HTML mode: auto, light or dark [default: from config, else auto]"),
    ] = None,
    jobs: Annotated[int, typer.Option("--jobs", "-j", min=1, help="Projects examined concurrently")] = 8,
    json_output: JsonOpt = False,
    config: ConfigOpt = None,
) -> None:
    """Show the state of every project: git, release, CI, scaffold drift, dependency pins."""
    from ..Ecosystem import MODES, THEMES, dashboard_dict, render_html, render_table

    fmt = format.lower()
    if fmt not in ("terminal", "html"):
        typer.echo(f"Unknown format {format!r}: use terminal or html", err=True)
        raise typer.Exit(2)
    cfg, eco = _load(config)
    theme = (theme or cfg.ecosystem_theme).lower()
    mode = (mode or cfg.ecosystem_mode).lower()
    if fmt == "html" and not json_output:  # validated before the (slow) collection, only where it is used
        if theme not in THEMES:
            typer.echo(f"Unknown theme {theme!r}: choose one of {', '.join(THEMES)}", err=True)
            raise typer.Exit(2)
        if mode not in MODES:
            typer.echo(f"Unknown mode {mode!r}: choose one of {', '.join(MODES)}", err=True)
            raise typer.Exit(2)
    statuses = eco.collect(fetch=not no_fetch, ci=not no_ci, jobs=jobs)
    if json_output:
        typer.echo(json.dumps(dashboard_dict(eco, statuses), indent=2))
        return
    if fmt == "terminal":
        typer.echo(render_table(statuses, color=_use_color()))
        return
    cache_home = os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
    path = (
        os.path.abspath(os.path.expanduser(output)) if output else os.path.join(cache_home, "fobis", "ecosystem.html")
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_html(eco, statuses, theme=theme, mode=mode))
    typer.echo(f"Dashboard written to {path}")
    if not no_open and not webbrowser.open("file://" + path):
        typer.echo("Could not open a browser: open the file above by hand.")


@ecosystem_app.command("graph")
def cmd_ecosystem_graph(
    json_output: JsonOpt = False,
    config: ConfigOpt = None,
) -> None:
    """Print the dependency tree and the release order of the projects."""
    from ..Ecosystem import render_graph

    _, eco = _load(config)
    if json_output:
        typer.echo(json.dumps(eco.graph_dict(), indent=2))
        return
    typer.echo(render_graph(eco, color=_use_color()))


# ---------------------------------------------------------------------------
# Acting across projects
# ---------------------------------------------------------------------------

OnlyOpt = Annotated[
    str | None,
    typer.Option("--only", help="Comma-separated projects to act on [default: all]"),
]
FromOpt = Annotated[
    str | None,
    typer.Option("--from", help="Start from this project in release order (resume after a failure)"),
]
FailFastOpt = Annotated[bool, typer.Option("--fail-fast", help="Stop at the first failure")]


def _selected(eco, only: str | None, start: str | None) -> list[str]:
    """Return the selected projects in release order; exit 2 on an unknown name."""
    from ..Ecosystem import select

    try:
        return select(eco, [n for n in only.split(",") if n.strip()] if only else None, start)
    except ValueError as err:
        typer.echo(str(err), err=True)
        raise typer.Exit(2) from None


def _finish(results) -> None:
    """Print the summary table and exit 1 when a project failed."""
    from ..Ecosystem import render_results

    typer.echo("\n" + render_results(results, color=_use_color()))
    if any(r.failed for r in results):
        raise typer.Exit(1)


@ecosystem_app.command("exec", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def cmd_ecosystem_exec(
    ctx: typer.Context,
    only: OnlyOpt = None,
    start: FromOpt = None,
    fail_fast: FailFastOpt = False,
    config: ConfigOpt = None,
) -> None:
    """Run a command in every project, dependencies first: fobis ecosystem exec -- <command>.

    The command runs through bash in each project's directory, its output streaming live;
    fobis/FoBiS.py in it resolve to this FoBiS. A non-zero exit is a failure, a signal a crash.
    A single argument is taken as a shell command line ('make && ./run'), several as one command.
    """
    import shlex

    from ..Ecosystem import exec_all

    if not ctx.args:
        typer.echo("No command given: fobis ecosystem exec -- <command>", err=True)
        raise typer.Exit(2)
    command = ctx.args[0] if len(ctx.args) == 1 else shlex.join(ctx.args)
    _, eco = _load(config)
    _finish(exec_all(eco, command, _selected(eco, only, start), fail_fast, echo=typer.echo))


@ecosystem_app.command("fetch")
def cmd_ecosystem_fetch(
    only: OnlyOpt = None,
    start: FromOpt = None,
    fail_fast: FailFastOpt = False,
    config: ConfigOpt = None,
) -> None:
    """Run 'fobis fetch --update' in every project with dependencies, dependencies first."""
    from ..Ecosystem import fetch_all

    _, eco = _load(config)
    _finish(fetch_all(eco, _selected(eco, only, start), fail_fast, echo=typer.echo))


@ecosystem_app.command("check")
def cmd_ecosystem_check(
    project: Annotated[str, typer.Argument(help="Project whose local working copy is checked")],
    keep: Annotated[bool, typer.Option("--keep", help="Keep the staged copies even when every check passes")] = False,
    fail_fast: FailFastOpt = False,
    config: ConfigOpt = None,
) -> None:
    """Pre-release impact check: build and test every dependent against PROJECT's local working copy.

    Each dependent (direct or transitive) is copied to a temporary directory with PROJECT's working
    copy, uncommitted changes included, in place of its fetched copy, and built from scratch there;
    the repositories are not touched. Commands: the dependent's fobos [ecosystem] check (one per line),
    else 'fobis rule --ex makecoverage' when defined, else 'fobis build'.
    """
    from ..Ecosystem import check_dependents, transitive_dependents

    _, eco = _load(config)
    (name,) = _selected(eco, project, None)
    dependents = transitive_dependents(eco, name)
    if not dependents:
        typer.echo(f"No project depends on {name}: nothing to check.")
        return
    typer.echo(f"Checking {', '.join(dependents)} against the local working copy of {name}")
    results, kept = check_dependents(eco, name, keep=keep, fail_fast=fail_fast, echo=typer.echo)
    if kept:
        typer.echo(f"\nStaged copies kept in {kept}")
    _finish(results)
    if any(r.status != "passed" for r in results):  # a dependent that could not be checked is no pass
        raise typer.Exit(1)


scaffold_app = typer.Typer(
    name="scaffold",
    help="Scaffold drift across the projects (honours each fobos [scaffold] skip).",
    no_args_is_help=True,
)
ecosystem_app.add_typer(scaffold_app)

FilesOpt = Annotated[str | None, typer.Option("--files", help="Limit to managed files matching this glob")]


@scaffold_app.command("status")
def cmd_ecosystem_scaffold_status(
    only: OnlyOpt = None,
    files: FilesOpt = None,
    config: ConfigOpt = None,
) -> None:
    """List the managed files not in sync, project by project (exit 1 when any drifts)."""
    from ..Ecosystem import scaffold_for

    _, eco = _load(config)
    drifting = 0
    for name in _selected(eco, only, None):
        project = eco.projects[name]
        if project.error:
            typer.echo(f"{name}: {project.error}")
            continue
        states = scaffold_for(project.path).drift(files_glob=files)
        bad = [(d, s) for d, s in states if s not in ("ok", "skipped")]
        skipped = [d for d, s in states if s == "skipped"]
        drifting += bool(bad)
        typer.echo(f"{name}: {'in sync' if not bad else f'{len(bad)} not in sync'}")
        for dest, state in bad:
            typer.echo(f"  {state.upper():<9}{dest}")
        for dest in skipped:
            typer.echo(f"  {'SKIPPED':<9}{dest} (project-owned)")
    if drifting:
        raise typer.Exit(1)


@scaffold_app.command("sync")
def cmd_ecosystem_scaffold_sync(
    only: OnlyOpt = None,
    files: FilesOpt = None,
    apply: Annotated[bool, typer.Option("--apply", help="Write the changes (default: only show them)")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="With --apply: do not ask for each project")] = False,
    config: ConfigOpt = None,
) -> None:
    """Show (default) or apply the scaffold changes, project by project.

    Files listed in a project's fobos [scaffold] skip are never written. With --apply each project's
    changes are shown and confirmed (default: no) before being written; --yes skips the question.
    """
    from ..Ecosystem import scaffold_for

    _, eco = _load(config)
    applied = []
    for name in _selected(eco, only, None):
        project = eco.projects[name]
        if project.error:
            typer.echo(f"{name}: {project.error}")
            continue
        drift = [d for d, s in scaffold_for(project.path).drift(files_glob=files) if s not in ("ok", "skipped")]
        if not drift:
            typer.echo(f"{name}: in sync")
            continue
        typer.echo(f"\n=== {name}: {len(drift)} file(s) not in sync ===")
        scaffold_for(project.path).sync(dry_run=True, files_glob=files)
        if not apply:
            continue
        if not yes:
            try:
                go = typer.confirm(f"Apply these changes to {name}?", default=False)
            except (typer.Abort, EOFError):  # no terminal to ask: never write without consent
                typer.echo("No answer possible: nothing written (use --yes to apply unattended).")
                raise typer.Exit(1) from None
            if not go:
                continue
        scaffold_for(project.path).sync(yes=True, files_glob=files)
        applied.append(name)
    if not apply:
        typer.echo("\nDry run: nothing written. Re-run with --apply to write the changes.")
    elif applied:
        typer.echo(f"\nUpdated: {', '.join(applied)} (review and commit in each repository).")


# ---------------------------------------------------------------------------
# Release train
# ---------------------------------------------------------------------------


@ecosystem_app.command("release")
def cmd_ecosystem_release(
    only: OnlyOpt = None,
    start: FromOpt = None,
    bump: Annotated[
        list[str] | None,
        typer.Option("--bump", help="Override a bump: NAME=major|minor|patch|vX.Y.Z (repeatable)"),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the plan and stop")] = False,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Do not ask: approve the plan and answer each release.sh prompt")
    ] = False,
    no_fetch: Annotated[bool, typer.Option("--no-fetch", help="Plan without 'git fetch' (not recommended)")] = False,
    no_wait: Annotated[bool, typer.Option("--no-wait", help="Do not wait for the GitHub releases")] = False,
    timeout: Annotated[int, typer.Option("--timeout", min=1, help="Seconds to wait for each GitHub release")] = 900,
    config: ConfigOpt = None,
) -> None:
    """Release train: release every project with releasable commits, dependencies first.

    Plans the versions (Conventional Commits of the releasable commits, overridable with --bump),
    refuses to start while any project is blocked (dirty tree, behind, CI failing, ...), asks for
    confirmation, then for each project runs scripts/release.sh <version> (which asks its own
    confirmation), checks the tag reached the remote, waits for the GitHub release and runs
    'fobis fetch --update' in its dependents. Stops at the first failure with a resume hint.
    """
    from ..Ecosystem import parse_bump_overrides, plan_release, render_plan, run_release_train

    _, eco = _load(config)
    names = _selected(eco, only, start)
    try:
        overrides = parse_bump_overrides(bump or [], eco)
    except ValueError as err:
        typer.echo(str(err), err=True)
        raise typer.Exit(2) from None
    statuses = eco.collect(fetch=not no_fetch, ci=True)
    plan = plan_release(eco, statuses, names, overrides)
    typer.echo(render_plan(plan, color=_use_color()))
    if not plan:
        return
    if any(item.blockers for item in plan):
        typer.echo(
            "\nBlocked: fix the problems above (or leave those projects out with --only), then re-run.", err=True
        )
        raise typer.Exit(1)
    if dry_run:
        typer.echo("\nDry run: nothing released.")
        return
    if not yes:
        try:
            go = typer.confirm(f"\nRelease {len(plan)} project(s) in this order?", default=False)
        except (typer.Abort, EOFError):
            typer.echo("No answer possible: nothing released (use --yes to release unattended).", err=True)
            raise typer.Exit(1) from None
        if not go:
            typer.echo("Nothing released.")
            return
    results = run_release_train(eco, plan, yes=yes, wait=not no_wait, timeout=timeout, echo=typer.echo)
    stopped = next((r.name for r in results if r.status != "passed"), None)
    if stopped:
        extra = "".join(f" --bump {name}={value}" for name, value in overrides.items())
        typer.echo(f"\nStopped at {stopped}. Fix it, then resume with: fobis ecosystem release --from {stopped}{extra}")
    _finish(results)
