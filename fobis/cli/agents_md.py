"""agents_md.py — FoBiS.py ``agents-md`` subcommand: the project's instructions for coding agents, from facts."""

from __future__ import annotations

from typing import Annotated

import typer

from ._app import app
from ._options import FciOpt, FobosOpt, JsonOpt, ModeOpt
from .lint import lint_namespace


@app.command("agents-md")
def cmd_agents_md(
    ctx: typer.Context,
    output: Annotated[
        list[str] | None,
        typer.Option("--output", "-o", help="File to update (repeatable, e.g. CLAUDE.md) [default: AGENTS.md]."),
    ] = None,
    check: Annotated[
        bool, typer.Option("--check", help="Write nothing; exit 1 when a file's generated block is stale or missing.")
    ] = False,
    print_block: Annotated[bool, typer.Option("--print", help="Print the generated block; write nothing.")] = False,
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    json_output: JsonOpt = False,
):
    """Generate the build, test and verification instructions for coding agents (AGENTS.md) from the fobos and the
    sources, between fobis:begin/end markers: the rest of the file is kept."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = lint_namespace(
        which="agents_md",
        agents_outputs=output or ["AGENTS.md"],
        agents_check=check,
        agents_print=print_block,
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        src=["./"],
        varset="",
        json_output=json_output,
    )
