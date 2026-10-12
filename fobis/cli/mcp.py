"""mcp.py — FoBiS.py ``mcp`` subcommand: serve FoBiS tools over the Model Context Protocol (stdio)."""

from __future__ import annotations

import sys
from typing import Annotated

import typer

from ._app import app


@app.command("mcp")
def cmd_mcp(
    root: Annotated[
        str, typer.Option("--root", help="Project directory the tools work in [default: the current directory].")
    ] = ".",
):
    """Serve lint, rules, knowledge packs and build commands to MCP clients over stdio."""
    from ..mcp_server import Server

    Server(root=root).serve(sys.stdin, sys.stdout)
