"""bindings.py — FoBiS.py ``bindings`` command: C and Python bindings of the project's modules."""

from __future__ import annotations

from typing import Annotated

import typer

from ._app import app
from ._options import FciOpt, FobosOpt, JsonOpt, ModeOpt
from .lint import lint_namespace


@app.command("bindings")
def cmd_bindings(
    ctx: typer.Context,
    modules: Annotated[list[str] | None, typer.Argument(help="Modules to bind [default: every module]")] = None,
    name: Annotated[str | None, typer.Option("--name", help="Base name of the files [default: the project's].")] = None,
    output_dir: Annotated[str, typer.Option("--output-dir", "-o", help="Where the files are written.")] = "bindings",
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing files.")] = False,
    print_only: Annotated[bool, typer.Option("--print", help="Report what would be bound; write nothing.")] = False,
    json_output: JsonOpt = False,
):
    """Generate bind(c) shims (NAME_c.f90), a C header (NAME.h) and a Python ctypes wrapper (NAME.py) for the
    public procedures of the modules whose arguments allow it; report why the others are not bound."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = lint_namespace(
        which="bindings",
        bindings_modules=[m.lower() for m in modules or []],
        bindings_name=name,
        bindings_output_dir=output_dir,
        bindings_force=force,
        bindings_print=print_only,
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        src=["./"],
        varset="",
        json_output=json_output,
    )
