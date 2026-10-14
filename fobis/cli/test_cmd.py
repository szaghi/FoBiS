"""test_cmd.py — FoBiS.py ``test`` subcommand.

Implements issue #173: first-class test runner with auto-discovery.
"""

from __future__ import annotations

from typing import Annotated

import typer

from ._app import _ns, app
from ._options import CompilerOpt, FciOpt, FobosOpt, JsonOpt, ModeOpt, QuietOpt, RunnerOpt, ShadowOpt


@app.command("test", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def cmd_test(
    ctx: typer.Context,
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    shadow: ShadowOpt = None,
    compiler: CompilerOpt = "gnu",
    suite: Annotated[
        str | None,
        typer.Option("--suite", help="Run only tests tagged with this suite name"),
    ] = None,
    filter_pattern: Annotated[
        str | None,
        typer.Option("--filter", help="Run only tests whose name matches this glob pattern"),
    ] = None,
    timeout: Annotated[
        float,
        typer.Option("--timeout", help="Per-test timeout in seconds [default: 60]"),
    ] = 60.0,
    no_build: Annotated[
        bool,
        typer.Option("--no-build", help="Skip (re-)compilation; run existing test binaries"),
    ] = False,
    list_tests: Annotated[
        bool,
        typer.Option("--list", help="List discovered tests without running them"),
    ] = False,
    coverage: Annotated[
        bool,
        typer.Option("--coverage", help="Generate coverage report after running tests"),
    ] = False,
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
    runner: RunnerOpt = "local",
    quiet: QuietOpt = False,
    json_output: JsonOpt = False,
):
    """Discover, build, and run Fortran test programs."""
    ctx.ensure_object(dict)
    extra_args = list(ctx.args)
    ctx.obj["cliargs"] = _ns(
        which="test",
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        shadow=shadow,
        lmodes=False,
        compiler=compiler.lower(),
        test_suite=suite,
        test_filter=filter_pattern,
        test_timeout=timeout,
        test_no_build=no_build,
        test_list=list_tests,
        test_coverage=coverage,
        test_extra_args=extra_args,
        explain=explain or explain_context,
        explain_context=explain_context,
        runner=runner,
        quiet=quiet,
        json_output=json_output,
    )
