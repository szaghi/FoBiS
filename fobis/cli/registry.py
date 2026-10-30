"""registry.py — FoBiS.py package-index commands: ``index`` (sub-app), ``search``, ``info``.

None of them reads a fobos mode: like ``kb`` they do their work in the Typer function and never set ``cliargs``.
The project's fobos (``-f``, default ``fobos`` in the current directory) is read only for its ``[indexes]`` section.
"""

from __future__ import annotations

import configparser
import json
import os
from typing import Annotated, Any

import typer

from ._app import app

index_app = typer.Typer(
    name="index",
    help="Manage the package indexes searched by search, info and add (several side by side, none by default).",
    no_args_is_help=True,
)
app.add_typer(index_app)

_ConfigOpt = Annotated[
    str | None, typer.Option("--config", help="User configuration file (default ~/.config/fobis/config.ini).")
]
_FobosOpt = Annotated[str, typer.Option("--fobos", "-f", help="Project fobos whose [indexes] are searched first.")]
_DepthOpt = Annotated[int, typer.Option("--depth", help="How far 'follows' is walked (0: configured indexes only).")]
_RefreshOpt = Annotated[bool, typer.Option("--refresh", help="Fetch the indexes again instead of using the cache.")]
_JsonOpt = Annotated[bool, typer.Option("--json", help="Machine-readable output.")]


def _fail(message: str, code: int = 2) -> None:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code)


class _FobosIndexes:
    """The ``[indexes]`` of a fobos, read without building a Fobos (no mode is involved)."""

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.fobos = configparser.RawConfigParser(strict=False)
        if os.path.isfile(filename):
            try:
                self.fobos.read(filename, encoding="utf-8")
            except configparser.Error as error:
                _fail(f"{filename}: {error}")


def index_set(config: str | None = None, fobos: str = "fobos", depth: int = 2, refresh: bool = False):
    """The user's IndexSet (project indexes first, then the user configuration's), loaded."""
    from ..registry.index import IndexSet, configured_roots
    from ..UserConfig import UserConfig

    roots = configured_roots(UserConfig(path=config), _FobosIndexes(fobos))
    if not roots:
        _fail(
            "no package index configured: add one with 'fobis index add NAME URL' "
            "(a git repository, a static index.toml or a local directory)"
        )
    indexes = IndexSet(roots, depth=depth).load(refresh=refresh)
    for error in indexes.errors:
        typer.echo(f"warning: index {error}", err=True)
    for notice in indexes.notices:
        typer.echo(f"note: index {notice}", err=True)
    return indexes


def _echo_json(payload: Any) -> None:
    typer.echo(json.dumps(payload, indent=2))


# ── index sub-app ─────────────────────────────────────────────────────────────


@index_app.command("add")
def cmd_index_add(
    name: Annotated[str, typer.Argument(help="Name of the index (used in qualified package names NAME:package).")],
    url: Annotated[str, typer.Argument(help="Git repository, static index.toml URL, or local file/directory.")],
    config: _ConfigOpt = None,
    check: Annotated[bool, typer.Option("--check/--no-check", help="Read and validate the index first.")] = True,
) -> None:
    """Add an index at the end of the user configuration's [indexes] (lowest priority)."""
    from ..registry.index import RegistryError, default_cache_root, load_index, read_index_text
    from ..UserConfig import UserConfig

    name = name.lower()
    cfg = UserConfig(path=config)
    entries = cfg.indexes
    if any(n == name for n, _ in entries):
        _fail(f"index {name} already configured ({dict(entries)[name]}): remove it first")
    if not os.path.isabs(os.path.expanduser(url)) and "://" not in url and not url.startswith("git@"):
        url = os.path.abspath(url)  # a relative path would change meaning with the working directory
    if check:
        try:
            text, provider = read_index_text(url, os.path.join(default_cache_root(), name), refresh=True)
            index = load_index(text, origin=url, strict=False)  # someone else's index: never refused for a new key
        except RegistryError as error:
            _fail(str(error), 1)
        typer.echo(f"{name}: {len(index.packages)} package(s), {provider} index")
        if index.ignored:
            typer.echo(
                f"note: index {name} uses keys unknown to this FoBiS ({', '.join(index.ignored)}): "
                "upgrade FoBiS to use them",
                err=True,
            )
    cfg.set_indexes([*entries, (name, url)])
    typer.echo(f"Added index {name} = {url} to {cfg.path}")


@index_app.command("remove")
def cmd_index_remove(
    name: Annotated[str, typer.Argument(help="Name of the index to remove.")],
    config: _ConfigOpt = None,
) -> None:
    """Remove an index from the user configuration (and its cache)."""
    from ..registry.index import default_cache_root, remove_cache
    from ..UserConfig import UserConfig

    name = name.lower()
    cfg = UserConfig(path=config)
    entries = cfg.indexes
    if not any(n == name for n, _ in entries):
        _fail(f"index {name} is not configured")
    cfg.set_indexes([(n, u) for n, u in entries if n != name])
    remove_cache(default_cache_root(), name)
    typer.echo(f"Removed index {name}")


@index_app.command("list")
def cmd_index_list(config: _ConfigOpt = None, fobos: _FobosOpt = "fobos", as_json: _JsonOpt = False) -> None:
    """List the configured indexes in priority order, with their cache state."""
    from ..registry.index import cache_meta, configured_roots, default_cache_root, fobos_indexes, provider_of
    from ..UserConfig import UserConfig

    project = {n for n, _ in fobos_indexes(_FobosIndexes(fobos))}
    rows = []
    for name, url in configured_roots(UserConfig(path=config), _FobosIndexes(fobos)):
        meta = cache_meta(os.path.join(default_cache_root(), name))
        provider = provider_of(url)
        rows.append(
            {
                "name": name,
                "url": url,
                "provider": provider,
                "scope": "project" if name in project else "user",
                "fetched_at": meta.get("fetched_at", "") if provider in ("git", "http") else "local",
            }
        )
    if as_json:
        _echo_json({"indexes": rows})
        return
    if not rows:
        typer.echo("No package index configured (fobis index add NAME URL).")
        return
    for row in rows:
        state = row["fetched_at"] or "not fetched"
        typer.echo(f"{row['name']:<16} {row['provider']:<5} {row['scope']:<8} {state:<26} {row['url']}")


@index_app.command("update")
def cmd_index_update(
    name: Annotated[str | None, typer.Argument(help="Update only this index (default: all).")] = None,
    config: _ConfigOpt = None,
    fobos: _FobosOpt = "fobos",
    depth: _DepthOpt = 2,
) -> None:
    """Fetch the indexes again (and the indexes they follow)."""
    from ..registry.index import IndexSet, configured_roots
    from ..UserConfig import UserConfig

    roots = configured_roots(UserConfig(path=config), _FobosIndexes(fobos))
    if name and not any(n == name.lower() for n, _ in roots):
        _fail(f"index {name} is not configured")
    indexes = IndexSet(roots, depth=depth).load(refresh=True, only=name.lower() if name else None)
    for loaded in indexes.loaded:
        via = f" (followed by {loaded.via})" if loaded.via else ""
        typer.echo(f"{loaded.qualifier}: {len(loaded.index.packages)} package(s){via}")
    for notice in indexes.notices:
        typer.echo(f"note: index {notice}", err=True)
    for error in indexes.errors:
        typer.echo(f"warning: index {error}", err=True)
    if indexes.errors and not indexes.loaded:
        raise typer.Exit(1)


@index_app.command("check")
def cmd_index_check(
    path: Annotated[str, typer.Argument(help="Index file, directory or URL to validate.")],
    online: Annotated[
        bool, typer.Option("--online", help="Also check that every source is a readable source.")
    ] = False,
    as_json: _JsonOpt = False,
) -> None:
    """Validate an index: schema, names, and (with --online) that each source answers."""
    from ..registry.index import RegistryError, load_index, read_index_text
    from ..registry.sources import probe

    try:
        text, _ = read_index_text(path)
        index = load_index(text, origin=path)
    except RegistryError as error:
        _fail(str(error))
    problems = []
    if online:
        for package in index.packages.values():
            try:
                info = probe(package.source, inspect=False)
            except RegistryError as error:
                problems.append({"package": package.name, "problem": str(error)})
                continue
            if not info.versions:
                problems.append({"package": package.name, "problem": "no version (semantic-version tag) found"})
    if as_json:
        _echo_json({"index": index.to_dict(), "problems": problems, "ok": not problems})
    else:
        typer.echo(f"{path}: valid index '{index.name or '(unnamed)'}', {len(index.packages)} package(s)")
        for problem in problems:
            typer.echo(f"  {problem['package']}: {problem['problem']}")
    if problems:
        raise typer.Exit(1)


@index_app.command("build")
def cmd_index_build(
    seeds: Annotated[str | None, typer.Argument(help="Seed index (entries with at least a source).")] = None,
    output: Annotated[str, typer.Option("--output", "-o", help="Where to write the index.")] = "index.toml",
    name: Annotated[str | None, typer.Option("--name", help="Name of the index (default: the seeds' name).")] = None,
    from_ecosystem: Annotated[
        bool, typer.Option("--from-ecosystem", help="Seed from the projects of the user's ecosystem registry.")
    ] = False,
    config: _ConfigOpt = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing output file.")] = False,
) -> None:
    """Write an index from seeds, filling description, license and provides from each source."""
    from ..registry.index import Index, Package, RegistryError, build_index, dump_index, load_index, read_index_text
    from ..registry.sources import probe

    if not seeds and not from_ecosystem:
        _fail("give a seed index or --from-ecosystem")
    if os.path.exists(output) and not force and os.path.abspath(output) != os.path.abspath(seeds or ""):
        _fail(f"{output} exists (use --force to overwrite it)")
    index = Index(name=name or "")
    if seeds:
        try:
            text, _ = read_index_text(seeds)
            index = load_index(text, origin=seeds)
        except RegistryError as error:
            _fail(str(error))
    added: set[str] = set()
    if from_ecosystem:
        for pname, source in _ecosystem_seeds(config):
            if pname not in index.packages and not any(p.source == source for p in index.packages.values()):
                index.packages[pname] = Package(name=pname, source=source)
                added.add(pname)
    if name:
        index.name = name
    # the projects of the ecosystem are probed without the user's credentials: a private one must not be published
    built, errors = build_index(
        index, lambda url: probe(url, anonymous=url in {index.packages[n].source for n in added})
    )
    for error in errors:
        pname = error.split(":", 1)[0]
        if pname in added:  # not readable anonymously (a private repository): never published
            del built.packages[pname]
            typer.echo(f"warning: {pname}: not publicly readable, left out ({error.split(': ', 1)[1]})", err=True)
        else:
            typer.echo(f"warning: {error}", err=True)
    tmp = output + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(dump_index(built))
    os.replace(tmp, output)
    typer.echo(f"Wrote {output}: {len(built.packages)} package(s)" + (f", {len(errors)} not read" if errors else ""))


def _ecosystem_seeds(config: str | None) -> list[tuple[str, str]]:
    """
    (name, public origin URL) of every project of the ecosystem registry that has an origin remote: an SSH remote
    becomes its HTTPS form, the URL other people can clone.
    """
    from ..registry.index import run_git
    from ..registry.sources import public_url, read_manifests
    from ..UserConfig import UserConfig

    seeds = []
    for path in UserConfig(path=config).ecosystem_projects:
        result = run_git("remote", "get-url", "origin", cwd=path) if os.path.isdir(path) else None
        if result is None or result.returncode != 0:
            typer.echo(f"warning: {path}: no origin remote, not listed", err=True)
            continue
        pname = read_manifests(path)["name"] or os.path.basename(path)
        seeds.append((pname, public_url(result.stdout.strip())))
    if not seeds:
        _fail("the ecosystem registry has no project with an origin remote (fobis ecosystem add)")
    return seeds


# ── search, info ──────────────────────────────────────────────────────────────


@app.command("search")
def cmd_search(
    term: Annotated[str, typer.Argument(help="Words matched against names, descriptions and keywords.")] = "",
    module: Annotated[str | None, typer.Option("--module", help="Find the packages providing this module.")] = None,
    build: Annotated[
        str | None,
        typer.Option("--build", help="Only packages built with fobis, fpm, cmake or make (as their index lists)."),
    ] = None,
    config: _ConfigOpt = None,
    fobos: _FobosOpt = "fobos",
    depth: _DepthOpt = 2,
    refresh: _RefreshOpt = False,
    as_json: _JsonOpt = False,
) -> None:
    """Search the configured package indexes (and the indexes they follow)."""
    from ..registry.index import BUILD_SYSTEMS

    if build is not None and build.lower() not in BUILD_SYSTEMS:
        _fail(f"--build {build}: one of {', '.join(BUILD_SYSTEMS)}")
    indexes = index_set(config, fobos, depth, refresh)
    found = indexes.providers(module) if module else indexes.search(term)
    if term and module:
        found = [p for p in found if p in indexes.search(term)]
    if build is not None:  # an index built before `builds` existed lists none: those packages are not shown
        found = [p for p in found if build.lower() in p.builds]
    if as_json:
        _echo_json({"packages": [p.to_dict() for p in found], "errors": indexes.errors, "notices": indexes.notices})
        return
    if not found:
        typer.echo("No package found.")
        return
    for package in found:
        qualified = f"{package.index}:{package.name}"  # padded whole: the sources line up whatever the index
        typer.echo(f"{qualified:<28} {package.source}")
        if package.description:
            typer.echo(f"    {package.description}")


@app.command("info")
def cmd_info(
    package: Annotated[str, typer.Argument(help="A package name (NAME or INDEX:NAME) or a source URL.")],
    config: _ConfigOpt = None,
    fobos: _FobosOpt = "fobos",
    depth: _DepthOpt = 2,
    refresh: _RefreshOpt = False,
    as_json: _JsonOpt = False,
) -> None:
    """Show what a package's source holds: versions, build system, modules, licence."""
    from ..registry.index import RegistryError
    from ..registry.sources import probe

    entry = None
    if _is_url(package):
        url = package
    else:
        entry = resolve_name(package, index_set(config, fobos, depth, refresh))
        url = entry.source
    try:
        info = probe(url)
    except RegistryError as error:
        _fail(str(error), 1)
    payload = info.to_dict()
    if entry is not None:
        payload["index"] = entry.index
        payload["index_entry"] = entry.to_dict()
    if as_json:
        _echo_json(payload)
        return
    typer.echo(f"{info.name}  ({url})")
    if entry is not None:
        typer.echo(f"  index     : {entry.index}")
    if info.description:
        typer.echo(f"  summary   : {info.description}")
    typer.echo(f"  license   : {info.license or 'unknown'}")
    typer.echo(f"  build     : {', '.join(info.builds) or 'not recognised'}")
    shown = ", ".join(info.versions[:8]) + (f" (+{len(info.versions) - 8} older)" if len(info.versions) > 8 else "")
    typer.echo(f"  versions  : {shown or 'none (no semantic-version tag)'}")
    typer.echo(f"  modules   : {', '.join(info.modules) if info.modules else 'none found'}")
    if entry is not None and entry.recipe:
        from ..registry.recipe import RecipeError, parse_recipe, read_index_recipe

        loaded = next(i for i in index_set(config, fobos, depth, False).loaded if i.qualifier == entry.index)
        try:
            recipe = parse_recipe(read_index_recipe(loaded.url, entry.recipe), origin=entry.recipe)
            typer.echo(f"  recipe    : {entry.recipe} ({recipe.backend})")
        except RecipeError as error:
            typer.echo(f"  recipe    : {entry.recipe} (not readable: {error})")


def _is_url(text: str) -> bool:
    return "://" in text or text.startswith(("git@", "/", "./", "../", "~"))


def resolve_name(name: str, indexes: Any) -> Any:
    """
    The one package a name designates (``NAME`` or ``INDEX:NAME``): not found or ambiguous -> exit 2, the message
    listing the qualified names to choose from.
    """
    found = indexes.lookup(name)
    if not found:
        _fail(f"no package {name} in the configured indexes (fobis search {name.rpartition(':')[2]})")
    if len(found) > 1:
        choices = "\n".join(f"  {p.index}:{p.name}  {p.source}" for p in found)
        _fail(f"{name} is in {len(found)} indexes, name one of them:\n{choices}")
    return found[0]
