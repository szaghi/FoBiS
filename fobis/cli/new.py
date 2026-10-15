"""new.py — FoBiS.py ``new`` subcommand: a ready-to-build project.

Like ``cache``, the command never sets ``ctx.obj['cliargs']``: no fobos is read from the current directory (``fobis
new`` runs where there is none, or inside another project).
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Annotated

import typer

from ._app import app
from ._completions import _complete_compiler
from ._options import JsonOpt


@app.command("new")
def cmd_new(
    path: Annotated[str, typer.Argument(help="Directory of the project (created if missing; '.' fills this one).")],
    name: Annotated[
        str | None, typer.Option("--name", help="Fortran name of the project [default: the directory's name].")
    ] = None,
    lib: Annotated[bool, typer.Option("--lib", help="A library: no program, static and shared library modes.")] = False,
    compiler: Annotated[
        str, typer.Option("--compiler", help="Compiler of the modes.", autocompletion=_complete_compiler)
    ] = "gnu",
    scaffold: Annotated[
        bool, typer.Option("--scaffold", help="Then run 'fobis scaffold init --yes': CI, docs, release scripts.")
    ] = False,
    no_git: Annotated[bool, typer.Option("--no-git", help="Do not initialise a git repository.")] = False,
    json_output: JsonOpt = False,
):
    """Create a project: a module in src/, a program in app/, a test in test/, a fobos with debug and release modes
    and a [test] section, a .gitignore and a git repository (nothing committed). An existing file is never
    overwritten."""
    from ..new import NewError, create
    from ..utils import fobis_command

    try:
        created = create(path, name=name, lib=lib, compiler=compiler.lower(), git=not no_git)
    except NewError as error:
        if json_output:
            typer.echo(json.dumps({"status": "error", "error": str(error), "conflicts": error.conflicts}, indent=2))
        else:
            typer.echo(f"Error: {error}" + "".join(f"\n  {c}" for c in error.conflicts), err=True)
        raise typer.Exit(2) from None
    shown = os.path.relpath(created.root)
    if not json_output:
        typer.echo(f"Created {'library' if lib else 'project'} {created.name} in {shown}/ (git: {created.git})")
        for target in created.files:
            typer.echo(f"  {target}")
    scaffolded = None
    if scaffold:
        result = subprocess.run(
            [*fobis_command(), "scaffold", "init", "--yes"],
            cwd=created.root,
            capture_output=json_output,
            text=True,
            check=False,
        )
        scaffolded = result.returncode == 0
    if json_output:
        document = {"status": "ok", "name": created.name, "path": created.root, "files": created.files}
        document["git"] = created.git
        if scaffolded is not None:
            document["scaffold"] = scaffolded
        typer.echo(json.dumps(document, indent=2))
    else:
        typer.echo("Next:" + (f" cd {shown} &&" if shown != "." else "") + " fobis build && fobis test")
    if scaffolded is False:
        typer.echo("Error: fobis scaffold init failed", err=True)
        raise typer.Exit(1)
