"""fetch.py — FoBiS.py ``fetch`` subcommand."""

from typing import Annotated

import typer

from ._app import _ns, app
from ._options import *


@app.command("fetch")
def cmd_fetch(
    ctx: typer.Context,
    # fobos group
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    lmodes: LmodesOpt = False,
    # fetch-specific options
    deps_dir: Annotated[
        str | None,
        typer.Option(
            "--deps-dir",
            help="Directory for storing fetched dependencies [default: .fobis_deps or fobos [dependencies] setting]",
        ),
    ] = None,
    update: Annotated[
        bool, typer.Option("--update", help="Update already-fetched dependencies (git fetch + re-checkout)")
    ] = False,
    no_build: Annotated[bool, typer.Option("--no-build", help="Only fetch dependencies, do not build them")] = False,
    frozen: Annotated[
        bool,
        typer.Option(
            "--frozen",
            help="Enforce exact lockfile state; abort if fobos.lock is absent or any dep mismatches",
        ),
    ] = False,
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Disable build artifact cache for fetched dependencies"),
    ] = False,
    # fancy group
    force_compile: ForceCompileOpt = False,
    colors: ColorsOpt = False,
    log: LogOpt = False,
    graph: GraphOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    jobs: JobsOpt = 1,
    makefile: MakefileOpt = None,
    json_output: JsonOpt = False,
):
    """Fetch and build GitHub-hosted Fortran dependencies listed in the fobos [dependencies] section."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _ns(
        which="fetch",
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        lmodes=lmodes,
        deps_dir=deps_dir,
        update=update,
        no_build=no_build,
        frozen=frozen,
        no_cache=no_cache,
        force_compile=force_compile,
        colors=colors,
        log=log,
        graph=graph,
        quiet=quiet,
        verbose=verbose,
        jobs=jobs,
        makefile=makefile,
        json_output=json_output,
    )
