"""testgen.py — FoBiS.py ``testgen`` subcommand: a test program for a module's public API, kept only if it runs."""

from __future__ import annotations

from typing import Annotated

import typer

from ._app import app
from ._options import FciOpt, FobosOpt, ModeOpt, SrcOpt
from .lint import lint_namespace


@app.command("testgen")
def cmd_testgen(
    ctx: typer.Context,
    module: Annotated[str, typer.Argument(help="Name of the module to test.")],
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    src: SrcOpt = None,
    procedure: Annotated[
        list[str] | None,
        typer.Option("--procedure", "-p", help="Test only this public procedure or generic (repeatable)."),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option(
            "--max", help="Test at most this many procedures [default: 8 with the model, all with --skeleton]."
        ),
    ] = None,
    skeleton: Annotated[
        bool,
        typer.Option(
            "--skeleton", help="No model: the compile-checked skeleton (declarations and calls, no checks) only."
        ),
    ] = False,
    context: Annotated[
        bool, typer.Option("--context", help="Print what the model would receive, run no model.")
    ] = False,
    apply: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="Write the accepted program to the test directory (fobos [test] test_dir, default test/) as "
            "test_<module>.f90; an existing file is never overwritten.",
        ),
    ] = False,
    output: Annotated[
        str | None, typer.Option("--output", "-o", help="With --apply, write to this path instead.")
    ] = None,
    retries: Annotated[
        int, typer.Option("--retries", help="Attempts after the first one, each with the errors of the previous.")
    ] = 3,
    timeout: Annotated[float, typer.Option("--timeout", help="Seconds a test program may run.")] = 60.0,
    output_format: Annotated[str, typer.Option("--format", help="Output format: text or json.")] = "text",
):
    """Generate a test program for a module's public procedures; kept only when it builds, runs and checks."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = lint_namespace(
        which="testgen",
        testgen_module=module,
        testgen_procedures=procedure or [],
        testgen_max=limit,
        testgen_skeleton=skeleton,
        testgen_context=context,
        testgen_apply=apply or output is not None,
        testgen_output=output,
        testgen_retries=max(0, retries),
        testgen_timeout=timeout,
        testgen_format=output_format,
        testgen_src_cli=list(src or []),
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        src=src or ["./"],
        varset="",
    )
