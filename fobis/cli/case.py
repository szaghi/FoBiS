"""case.py — FoBiS.py ``case`` sub-app (list, run) and the ``provenance`` command (verification, phase V1)."""

from __future__ import annotations

from typing import Annotated

import typer

from ._app import _ns, app
from ._options import FciOpt, FobosOpt, JsonOpt, ModeOpt

case_app = typer.Typer(
    name="case",
    help="Run the cases declared in the fobos ([case:NAME]) and extract their quantities.",
    no_args_is_help=True,
)
app.add_typer(case_app)


def _case_ns(action: str, **fields):
    return _ns(
        which="case",
        case_action=action,
        lmodes=False,
        colors=False,
        log=False,
        quiet=False,
        verbose=False,
        **fields,
    )


@case_app.command("list")
def cmd_case_list(
    ctx: typer.Context,
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    json_output: JsonOpt = False,
):
    """List the cases declared in the fobos."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _case_ns(
        "list", fobos=fobos, fobos_case_insensitive=fobos_case_insensitive, mode=None, json_output=json_output
    )


@case_app.command("run")
def cmd_case_run(
    ctx: typer.Context,
    names: Annotated[list[str] | None, typer.Argument(help="Cases to run [default: all]")] = None,
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    json_output: JsonOpt = False,
):
    """Build and run cases; report their quantities, the status of each run and its provenance."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _case_ns(
        "run",
        case_names=names or [],
        case_mode=mode,
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=None,  # the case's own mode is used; --mode overrides it per run, not for loading the fobos
        json_output=json_output,
    )


@app.command("provenance")
def cmd_provenance(
    ctx: typer.Context,
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    json_output: JsonOpt = False,
):
    """Print what a result produced now would depend on: commit, dependency pins, compiler, flags, machine."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _ns(
        which="provenance",
        prov_mode=mode,
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=None,
        lmodes=False,
        colors=False,
        log=False,
        quiet=False,
        verbose=False,
        json_output=json_output,
    )
