"""add.py — FoBiS.py ``add`` command: resolve a package once and write it into the fobos ``[dependencies]``.

The name is resolved through the package indexes HERE and only here: the fobos receives the source URL, so
``fetch`` and ``build`` never read an index (with every index unreachable, every build keeps working).
"""

from __future__ import annotations

import json
import os
import re
from typing import Annotated

import typer

from ._app import app
from .registry import _ConfigOpt, _DepthOpt, _fail, _is_url, _RefreshOpt, index_set, resolve_name

_DEP_NAME = re.compile(r"^[a-z0-9][a-z0-9_.\-]*$")


@app.command("add")
def cmd_add(
    package: Annotated[str | None, typer.Argument(help="A package name (NAME or INDEX:NAME) or a source URL.")] = None,
    module: Annotated[str | None, typer.Option("--module", help="Add the package providing this module.")] = None,
    as_name: Annotated[str | None, typer.Option("--as", help="Name of the dependency in the fobos.")] = None,
    semver: Annotated[str | None, typer.Option("--semver", help="Version range (default: ^ the newest).")] = None,
    tag: Annotated[str | None, typer.Option("--tag", help="Pin a tag.")] = None,
    rev: Annotated[str | None, typer.Option("--rev", help="Pin a commit.")] = None,
    branch: Annotated[str | None, typer.Option("--branch", help="Follow a branch.")] = None,
    use: Annotated[
        str | None, typer.Option("--use", help="sources (compiled with yours, default) or fobos (built apart).")
    ] = None,
    mode: Annotated[
        str | None, typer.Option("--mode", "-m", help="Mode of the dependency's fobos (use=fobos).")
    ] = None,
    dev: Annotated[bool, typer.Option("--dev", help="A test-only dependency.")] = False,
    force: Annotated[bool, typer.Option("--force", help="Replace an existing dependency of that name.")] = False,
    fobos: Annotated[str, typer.Option("--fobos", "-f", help="The fobos to edit.")] = "fobos",
    config: _ConfigOpt = None,
    depth: _DepthOpt = 2,
    refresh: _RefreshOpt = False,
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output.")] = False,
) -> None:
    """Add a dependency to the fobos, resolved through the package indexes (the fobos gets its URL)."""
    from ..registry.fobosedit import has_entry, set_entry
    from ..registry.index import RegistryError
    from ..registry.sources import default_name, probe

    if not os.path.isfile(fobos):
        _fail(f"{fobos} not found (fobis new creates a project with its fobos)")
    pins = [k for k, v in (("semver", semver), ("tag", tag), ("rev", rev), ("branch", branch)) if v]
    if len(pins) > 1:
        _fail(f"give one of --semver, --tag, --rev, --branch, not {' and '.join('--' + p for p in pins)}")
    if use not in (None, "sources", "fobos"):
        _fail(f"--use {use}: sources or fobos")
    if bool(package) == bool(module):
        _fail("give a package (NAME, INDEX:NAME or URL) or --module, one of them")
    entry = None
    if module:
        indexes = index_set(config, fobos, depth, refresh)
        found = indexes.providers(module)
        if not found:
            _fail(f"no package of the configured indexes provides module {module}")
        if len(found) > 1:
            choices = "\n".join(f"  {p.index}:{p.name}  {p.source}" for p in found)
            _fail(f"module {module} is provided by {len(found)} packages, name one of them:\n{choices}")
        entry = found[0]
        url = entry.source
    elif _is_url(package):
        url = package
    else:
        entry = resolve_name(package, index_set(config, fobos, depth, refresh))
        url = entry.source
    try:
        info = probe(url, inspect=False)
    except RegistryError as error:
        _fail(str(error), 1)
    name = (as_name or (entry.name if entry else default_name(url))).lower()
    if not _DEP_NAME.match(name):
        _fail(f"{name!r} is not a valid dependency name (use --as NAME)")
    if has_entry(fobos, name) and not force:
        _fail(f"{fobos} already has dependency {name} (--force replaces it, --as gives another name)")
    pin = ""
    warning = ""
    if semver:
        pin = f"semver={semver}"
    elif tag:
        if tag not in info.versions + info.other_tags:
            _fail(f"{url} has no tag {tag} (versions: {', '.join(info.versions[:8]) or 'none'})", 1)
        pin = f"tag={tag}"
    elif rev:
        pin = f"rev={rev}"
    elif branch:
        pin = f"branch={branch}"
    elif info.latest:
        from ..SemVer import Version

        newest = Version(info.latest)
        pin = f"semver=^{newest.major}.{newest.minor}.{newest.patch}"
    else:
        warning = f"{url} has no semantic-version tag: the dependency follows its default branch (unpinned)"
    recipe_spec = ""
    if entry is not None and entry.recipe:  # copied into the project: builds never depend on the index
        from ..registry.recipe import RecipeError, parse_recipe, read_index_recipe

        loaded = next(i for i in index_set(config, fobos, depth, False).loaded if i.qualifier == entry.index)
        try:
            text = read_index_recipe(loaded.url, entry.recipe)
            parse_recipe(text, origin=entry.recipe)
        except RecipeError as error:
            _fail(str(error), 1)
        target = os.path.join(os.path.dirname(os.path.abspath(fobos)), "recipes", f"{name}.toml")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(text)
        recipe_spec = f"recipe=recipes/{name}.toml"
    parts = [url] + ([pin] if pin else [])
    parts += [f"use={use}"] if use else []
    parts += [f"mode={mode}"] if mode else []
    parts += ["dev"] if dev else []
    parts += [recipe_spec] if recipe_spec else []
    spec = " :: ".join(parts)
    comment = f"added by fobis add from index {entry.index}" if entry else ""
    replaced = set_entry(fobos, name, spec, comment=comment)
    if as_json:
        payload = {
            "name": name,
            "spec": spec,
            "source": url,
            "index": entry.index if entry else "",
            "replaced": replaced,
        }
        typer.echo(json.dumps({**payload, "warning": warning} if warning else payload, indent=2))
        return
    if warning:
        typer.echo(f"warning: {warning}", err=True)
    typer.echo(f"{'Replaced' if replaced else 'Added'} {name} = {spec}")
    typer.echo("Run 'fobis fetch' to fetch it.")
