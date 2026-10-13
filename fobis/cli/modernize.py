"""modernize.py — FoBiS.py ``modernize`` command: mechanical lint fixes, verified by build, tests and cases."""

from __future__ import annotations

from typing import Annotated

import typer

from ._app import app
from ._options import FciOpt, FobosOpt, JsonOpt, ModeOpt
from .lint import lint_namespace


@app.command("modernize")
def cmd_modernize(
    ctx: typer.Context,
    select: Annotated[
        list[str] | None,
        typer.Option("--select", help="Fixable rules to apply (repeatable or comma-separated) [default: all fixable]."),
    ] = None,
    apply: Annotated[bool, typer.Option("--apply", help="Write the verified fixes into the working tree.")] = False,
    unverified: Annotated[
        bool,
        typer.Option("--unverified", help="With --apply: accept a build as the only check (no tests, no cases)."),
    ] = False,
    keep: Annotated[bool, typer.Option("--keep", help="Keep the scratch copies (path printed).")] = False,
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    json_output: JsonOpt = False,
):
    """Apply the automatic lint fixes (array constructors, relational operators, generic intrinsics, character
    length, labelled DO loops) to a scratch copy and keep them only when it builds, the tests still pass and the
    declared cases give equivalent results; each rule is checked alone when the whole set fails."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = lint_namespace(
        which="modernize",
        modernize_select=[s for item in select or [] for s in item.replace(",", " ").split()],
        modernize_apply=apply,
        modernize_unverified=unverified,
        modernize_keep=keep,
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        src=["./"],
        varset="",
        json_output=json_output,
    )
