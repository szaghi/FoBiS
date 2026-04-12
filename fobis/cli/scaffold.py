"""scaffold.py — FoBiS.py ``scaffold`` subcommand."""

from typing import Annotated

import typer

from ._app import _ns, app

scaffold_app = typer.Typer(
    name="scaffold",
    help="Manage project boilerplate via bundled scaffold templates.",
    no_args_is_help=True,
)
app.add_typer(scaffold_app)

_FobosOpt = Annotated[str | None, typer.Option("--fobos", "-f", help="Path to fobos configuration file")]
_DryRunOpt = Annotated[bool, typer.Option("--dry-run", help="Show what would change without writing any files")]
_YesOpt = Annotated[bool, typer.Option("--yes", "-y", help="Apply all changes without interactive prompts")]
_FilesOpt = Annotated[str | None, typer.Option("--files", help="Limit scope to files matching this glob pattern")]
_StrictOpt = Annotated[bool, typer.Option("--strict", help="Exit non-zero if any drift is detected (for CI use)")]


def _scaffold_ns(action, fobos=None, dry_run=False, yes=False, files=None, strict=False):
    return _ns(
        which="scaffold",
        action=action,
        fobos=fobos,
        fobos_case_insensitive=False,
        mode=None,
        lmodes=False,
        dry_run=dry_run,
        yes=yes,
        files=files,
        strict=strict,
        colors=False,
        log=False,
        quiet=False,
        verbose=False,
    )


@scaffold_app.command("status")
def cmd_scaffold_status(
    ctx: typer.Context,
    fobos: _FobosOpt = None,
    files: _FilesOpt = None,
    strict: _StrictOpt = False,
):
    """Show drift report: which managed files are up-to-date, outdated, or missing."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _scaffold_ns("status", fobos=fobos, files=files, strict=strict)


@scaffold_app.command("sync")
def cmd_scaffold_sync(
    ctx: typer.Context,
    fobos: _FobosOpt = None,
    dry_run: _DryRunOpt = False,
    yes: _YesOpt = False,
    files: _FilesOpt = None,
):
    """Update divergent managed files (shows diff + asks confirmation, or --yes to skip prompts)."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _scaffold_ns("sync", fobos=fobos, dry_run=dry_run, yes=yes, files=files)


@scaffold_app.command("init")
def cmd_scaffold_init(
    ctx: typer.Context,
    fobos: _FobosOpt = None,
    yes: _YesOpt = False,
):
    """Create all missing boilerplate in a new or existing repo."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _scaffold_ns("init", fobos=fobos, yes=yes)


@scaffold_app.command("list")
def cmd_scaffold_list(
    ctx: typer.Context,
    fobos: _FobosOpt = None,
):
    """List all managed template files and their categories."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _scaffold_ns("list", fobos=fobos)
