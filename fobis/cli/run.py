"""run.py — FoBiS.py ``run`` subcommand.

Implements issue #174: build and execute a target in one step.
"""

from __future__ import annotations

from typing import Annotated

import typer

from ._app import _ns, app
from ._options import FciOpt, FobosOpt, ModeOpt, ShadowOpt


# no ignore_unknown_options: an unknown option is an error (it became the TARGET_NAME); program options go after --
@app.command("run", context_settings={"allow_extra_args": True})
def cmd_run(
    ctx: typer.Context,
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    shadow: ShadowOpt = None,
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
    explain: Annotated[
        bool,
        typer.Option(
            "--explain",
            help="When the program fails, explain why: from facts (location, declarations, debug mode to use, "
            "known compiler bugs), then with the LLM (cited cause and fix) when the location can be trusted.",
        ),
    ] = False,
    explain_context: Annotated[
        bool,
        typer.Option("--explain-context", help="Like --explain, but print what the model would receive instead."),
    ] = False,
    program_args: Annotated[
        list[str] | None,
        typer.Option("--program-arg", hidden=True, help="An argument for the program (what follows --)."),
    ] = None,
):
    """Build a target (if needed) and execute it."""
    ctx.ensure_object(dict)
    # the words after -- are forwarded to the program (_normalize_args turns them into --program-arg options)
    extra_args = [*(program_args or []), *ctx.args]
    ctx.obj["cliargs"] = _ns(
        which="run",
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        shadow=shadow,
        lmodes=False,
        run_target=target_name,
        run_no_build=no_build,
        run_dry_run=dry_run,
        run_extra_args=extra_args,
        run_example=example,
        explain=explain or explain_context,
        explain_context=explain_context,
    )
