"""review.py — FoBiS.py ``review`` subcommand: lint findings on the changed lines only, plus a cited risk summary."""

from __future__ import annotations

from typing import Annotated

import typer

from ._app import app
from ._completions import _complete_fobos_varset
from ._options import FciOpt, FobosOpt, ModeOpt, SrcOpt
from .lint import lint_namespace

REVIEW_FORMATS = ("text", "markdown", "json", "sarif", "github")


@app.command("review")
def cmd_review(
    ctx: typer.Context,
    paths: Annotated[
        list[str] | None,
        typer.Argument(help="Sources to lint [default: the sources of the fobos mode, else ./]"),
    ] = None,
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    src: SrcOpt = None,
    base: Annotated[
        str | None,
        typer.Option(
            "--base", help="Review the commits since the merge base with this reference (e.g. origin/master)."
        ),
    ] = None,
    staged: Annotated[bool, typer.Option("--staged", help="Review the staged change (pre-commit hook).")] = False,
    context: Annotated[
        int, typer.Option("--context", help="Also report findings this many lines away from a changed line.")
    ] = 0,
    select: Annotated[
        list[str] | None,
        typer.Option("--select", help="Rule ids or prefixes to run (repeatable, comma-separated; 'ALL')."),
    ] = None,
    ignore: Annotated[
        list[str] | None, typer.Option("--ignore", help="Rule ids or prefixes to skip (repeatable, comma-separated).")
    ] = None,
    output_format: Annotated[
        str, typer.Option("--format", help="Output format: text, markdown (pull-request comment), json, sarif, github.")
    ] = "text",
    compiler_feedback: Annotated[
        str | None,
        typer.Option("--compiler-feedback", help="Build log with compiler optimisation reports (see fobis lint)."),
    ] = None,
    deep: Annotated[
        bool,
        typer.Option("--deep", help="Add an LLM risk summary of the change, with citations (text, markdown, json)."),
    ] = False,
    deep_context: Annotated[
        bool, typer.Option("--deep-context", help="Print what the model would receive for --deep, run no model.")
    ] = False,
    exit_zero: Annotated[bool, typer.Option("--exit-zero", help="Exit 0 even when findings are reported.")] = False,
    varset: Annotated[
        str | None,
        typer.Option("--varset", help="Apply [varset:NAME] bindings.", autocompletion=_complete_fobos_varset),
    ] = None,
):
    """Report the lint findings on the changed lines only (staged, since a base, or uncommitted)."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = lint_namespace(
        which="review",
        lint_paths=paths or [],
        lint_select=select or [],
        lint_ignore=ignore or [],
        lint_format=output_format,
        lint_compiler_feedback=compiler_feedback,
        lint_exit_zero=exit_zero,
        review_base=base,
        review_staged=staged,
        review_context=context,
        review_deep=deep or deep_context,
        review_deep_context=deep_context,
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        src=src or ["./"],
        varset=varset or "",
    )
