"""merge_assist.py — FoBiS.py ``merge-assist`` subcommand: proposals for resolving merge conflicts."""

from __future__ import annotations

from typing import Annotated

import typer

from ._app import _ns, app
from ._options import FciOpt, FobosOpt, ModeOpt


@app.command("merge-assist")
def cmd_merge_assist(
    ctx: typer.Context,
    paths: Annotated[
        list[str] | None, typer.Argument(help="Conflicted files to work on [default: every conflicted file]")
    ] = None,
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    apply: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="Ask hunk by hunk (accept/ours/theirs/both/edit/skip) and write the accepted resolutions to the "
            "working tree. Nothing is ever staged.",
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="With --apply, no questions: accept the high-confidence deterministic resolutions and the model "
            "proposals that compile; leave the others in conflict.",
        ),
    ] = False,
    no_model: Annotated[bool, typer.Option("--no-model", help="Deterministic resolutions only; no model.")] = False,
    context: Annotated[
        bool, typer.Option("--context", help="Print what the model would receive for each hunk, run no model.")
    ] = False,
    output_format: Annotated[
        str, typer.Option("--format", help="Output format: text, or json (the report on stdout; asks nothing).")
    ] = "text",
):
    """Propose resolutions for merge, rebase or cherry-pick conflicts, checked by the compiler; never stages."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _ns(
        which="merge_assist",
        merge_paths=paths or [],
        merge_apply=apply or yes,
        merge_yes=yes,
        merge_no_model=no_model,
        merge_context=context,
        merge_format=output_format,
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        lmodes=False,
        colors=False,
        log=False,
        quiet=False,
        verbose=False,
    )
