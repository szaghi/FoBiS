"""query.py — FoBiS.py ``query`` subcommand: deterministic questions about the project's code."""

from __future__ import annotations

from typing import Annotated

import typer

from ._app import app
from ._options import FciOpt, FobosOpt, JsonOpt, ModeOpt, SrcOpt
from .lint import lint_namespace


@app.command("query")
def cmd_query(
    ctx: typer.Context,
    kind: Annotated[
        str,
        typer.Argument(
            help="callers, callees, uses, writers, readers, defines, region, device, mpi, interface",
        ),
    ],
    argument: Annotated[
        str | None,
        typer.Argument(help="NAME, module::NAME, MODULE, FILE:LINE (region) or ROUTINE|KIND (mpi, optional)"),
    ] = None,
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    src: SrcOpt = None,
    json_output: JsonOpt = False,
):
    """Answer a question about the code from the analysis: who calls what, who writes a variable, where a name is
    defined, which directive regions hold a line, where a variable lives on the device, which MPI calls are made."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = lint_namespace(
        which="query",
        query_kind=kind,
        query_argument=argument or "",
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        src=src or ["./"],
        varset="",
        json_output=json_output,
    )
