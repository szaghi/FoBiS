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
    update: Annotated[
        bool, typer.Option("--update", help="Update already-fetched dependencies (git fetch + re-checkout)")
    ] = False,
    no_build: Annotated[bool, typer.Option("--no-build", help="Only fetch dependencies, do not build them")] = False,
    no_dev: Annotated[
        bool,
        typer.Option("--no-dev", help="Skip the test-only dependencies (:: dev), e.g. for a production build"),
    ] = False,
    frozen: Annotated[
        bool,
        typer.Option(
            "--frozen",
            help="Check every dependency out at the commit of <deps_dir>/fobos.lock; abort if the lock is absent",
        ),
    ] = False,
    colors: ColorsOpt = False,
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
        update=update,
        no_build=no_build,
        no_dev=no_dev,
        frozen=frozen,
        colors=colors,
        json_output=json_output,
    )
