"""tree.py — FoBiS.py ``tree`` subcommand.

Implements issue #167: print the resolved inter-project dependency tree.
"""

from __future__ import annotations

from typing import Annotated

import typer

from ._app import _ns, app
from ._options import FciOpt, FobosOpt, ModeOpt


@app.command("tree")
def cmd_tree(
    ctx: typer.Context,
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    depth: Annotated[
        int | None,
        typer.Option("--depth", "-d", help="Maximum recursion depth (default: unlimited)"),
    ] = None,
    no_dedupe: Annotated[
        bool,
        typer.Option("--no-dedupe", help="Expand duplicate deps instead of marking them with (*)"),
    ] = False,
):
    """Print the resolved inter-project dependency tree."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _ns(
        which="tree",
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        lmodes=False,
        tree_depth=depth,
        tree_no_dedupe=no_dedupe,
    )
