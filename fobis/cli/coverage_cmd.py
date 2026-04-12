"""coverage_cmd.py — FoBiS.py ``coverage`` subcommand.

Implements issue #180: generate HTML/XML coverage reports after test runs.
"""

from __future__ import annotations

from typing import Annotated

import typer

from ._app import _ns, app
from ._options import FciOpt, FobosOpt, ModeOpt


@app.command("coverage")
def cmd_coverage(
    ctx: typer.Context,
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    fmt: Annotated[
        list[str] | None,
        typer.Option("--format", help="Output formats: html (default), xml, text, all"),
    ] = None,
    output_dir: Annotated[
        str,
        typer.Option("--output-dir", help="Directory for coverage reports [default: coverage/]"),
    ] = "coverage",
    source_dir: Annotated[
        str,
        typer.Option("--source-dir", help="Root for source filtering [default: .]"),
    ] = ".",
    exclude: Annotated[
        list[str] | None,
        typer.Option("--exclude", help="Glob patterns to exclude from coverage (repeatable)"),
    ] = None,
    fail_under: Annotated[
        float | None,
        typer.Option("--fail-under", help="Exit 1 if line coverage is below N%"),
    ] = None,
    tool: Annotated[
        str | None,
        typer.Option("--tool", help="Force a specific backend: gcovr or lcov"),
    ] = None,
):
    """Generate HTML/XML coverage reports from instrumented test runs."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _ns(
        which="coverage",
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        lmodes=False,
        coverage_formats=fmt or ["html"],
        coverage_output_dir=output_dir,
        coverage_source_dir=source_dir,
        coverage_exclude=exclude or [],
        coverage_fail_under=fail_under,
        coverage_tool=tool,
        # Minimal build-like attrs
        build_dir="./",
        obj_dir="./obj/",
    )
