"""run.py — FoBiS.py ``run`` subcommand.

Implements issue #174: build and execute a target in one step.
"""

from __future__ import annotations

from typing import Annotated

import typer

from ._app import _ns, app
from ._options import FobosOpt, FciOpt, ModeOpt


@app.command("run", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def cmd_run(
    ctx: typer.Context,
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    target_name: Annotated[
        str | None,
        typer.Argument(help="Name or path of the executable to run (defaults to the mode's output)"),
    ] = None,
    no_build: Annotated[
        bool,
        typer.Option("--no-build", help="Skip build step; just run the existing binary"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print build and run commands without executing"),
    ] = False,
    example: Annotated[
        str | None,
        typer.Option("--example", help="Build and run a named [[example.*]] target"),
    ] = None,
):
    """Build a target (if needed) and execute it."""
    ctx.ensure_object(dict)
    # Extra args after -- are forwarded to the binary
    extra_args = list(ctx.args)
    ctx.obj["cliargs"] = _ns(
        which="run",
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        lmodes=False,
        run_target=target_name,
        run_no_build=no_build,
        run_dry_run=dry_run,
        run_extra_args=extra_args,
        run_example=example,
    )
