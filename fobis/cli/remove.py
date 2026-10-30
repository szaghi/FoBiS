"""remove.py — FoBiS.py ``remove`` command: take a dependency out of the fobos ``[dependencies]``.

The counterpart of ``add``: the entry goes (with the comment line ``add`` wrote above it), and so does the recipe
``add`` copied for it (``recipes/NAME.toml``). The fetched clone is left in the deps directory: the next ``fetch``
writes a deps config without it, so the build no longer uses it.
"""

from __future__ import annotations

import configparser
import json
import os
from typing import Annotated

import typer

from ._app import app
from .registry import _fail


@app.command("remove")
def cmd_remove(
    name: Annotated[str, typer.Argument(help="The dependency's name in the fobos.")],
    fobos: Annotated[str, typer.Option("--fobos", "-f", help="The fobos to edit.")] = "fobos",
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output.")] = False,
) -> None:
    """Remove a dependency from the fobos (and the recipe fobis add copied for it)."""
    from ..Fobos import DEPENDENCY_SETTINGS
    from ..registry.fobosedit import SECTION, remove_entry

    if not os.path.isfile(fobos):
        _fail(f"{fobos} not found")
    name = name.lower()
    if name in DEPENDENCY_SETTINGS:
        _fail(f"{name} is a setting of [dependencies], not a dependency")
    config = configparser.RawConfigParser(strict=False)
    config.read(fobos, encoding="utf-8")
    spec = config.get(SECTION, name, fallback=None) if config.has_section(SECTION) else None
    if spec is None or not remove_entry(fobos, name):
        _fail(f"{fobos} has no dependency {name}")
    recipe = ""
    copied = f"recipe=recipes/{name}.toml"  # what add writes: a recipe the user named elsewhere is theirs
    if any(part.strip() == copied for part in spec.split("::")):
        path = os.path.join(os.path.dirname(os.path.abspath(fobos)), "recipes", f"{name}.toml")
        if os.path.isfile(path):
            os.remove(path)
            recipe = os.path.relpath(path)
    deps_dir = config.get(SECTION, "deps_dir", fallback=".fobis_deps").strip() or ".fobis_deps"
    clone = os.path.join(os.path.dirname(os.path.abspath(fobos)), deps_dir, name)
    left = os.path.relpath(clone) if os.path.isdir(clone) else ""
    if as_json:
        typer.echo(json.dumps({"name": name, "spec": spec.strip(), "recipe_removed": recipe, "clone": left}, indent=2))
        return
    typer.echo(f"Removed {name} = {spec.strip()}")
    if recipe:
        typer.echo(f"Removed its recipe {recipe}")
    if left:
        typer.echo(f"Run 'fobis fetch' to drop it from the build; its clone {left} can be deleted.")
    else:
        typer.echo("Run 'fobis fetch' to drop it from the build.")
