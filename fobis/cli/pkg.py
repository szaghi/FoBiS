"""pkg.py — FoBiS.py ``pkg`` sub-app: packages installed for a toolchain (install, list, uninstall, upgrade, path).

A package is built from source with the consumer's compiler and installed under
``<store>/<toolchain key>/<name>/<version>/`` (``$FOBIS_PKGS_DIR``, default ``~/.fobis/pkgs``) with a ``.pc`` file per
library; applications are linked into ``~/.local/bin``. ``fobis install REPO`` (no record kept) is unchanged.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from typing import Annotated, Any

import typer

from ._app import app
from .registry import _ConfigOpt, _fail, _is_url, index_set, resolve_name

pkg_app = typer.Typer(
    name="pkg",
    help="Packages built for your compiler and installed in a store (install, list, uninstall, upgrade, path).",
    no_args_is_help=True,
)
app.add_typer(pkg_app)

_JsonOpt = Annotated[bool, typer.Option("--json", help="Machine-readable output.")]
_KeyOpt = Annotated[str | None, typer.Option("--key", help="Toolchain key (when installed for several).")]


def _store():
    from ..registry.store import Store

    return Store()


def _toolchain(compiler: str, fc: str | None, mpi: bool, cflags: str, lflags: str):
    from ..registry.toolchain import ToolchainError, detect

    try:
        return detect(compiler.lower(), fc, mpi, cflags, lflags)
    except ToolchainError as error:
        _fail(str(error))


def _resolve(package: str, config: str | None):
    """(source URL, index entry or None) of a package argument."""
    if _is_url(package):
        return package, None
    entry = resolve_name(package, index_set(config))
    return entry.source, entry


def install_package(
    package: str,
    toolchain: Any,
    constraint: str = "",
    version: str = "",
    mode: str | None = None,
    bin_dir: str | None = None,
    shims: bool = True,
    force: bool = False,
    config: str | None = None,
    log=lambda m: typer.echo(m, err=True),
    say=lambda m: typer.echo(m, err=True),
) -> dict:
    """Install one package; returns the receipt as a dict (``already`` true when it was installed before)."""
    from ..registry.backends import BackendError, install
    from ..registry.index import RegistryError
    from ..registry.sources import checkout_version, default_name, detect_backend, read_manifests
    from ..registry.store import Receipt, files_under, link_applications

    url, entry = _resolve(package, config)
    store = _store()
    with tempfile.TemporaryDirectory(prefix="fobis-pkg-") as scratch:
        src = os.path.join(scratch, "src")
        try:
            chosen, identity, provider = checkout_version(url, src, constraint, version)
        except RegistryError as error:
            _fail(str(error), 1)
        facts = read_manifests(src)
        name = (entry.name if entry else "") or facts["name"] or default_name(url)
        try:
            prefix = store.prefix(toolchain.key, name, chosen or identity[:12])
        except ValueError as error:
            _fail(f"{url}: {error}")
        previous = [r for r in store.find(name, toolchain.key) if r.version == (chosen or identity[:12])]
        if previous and not force:
            return {**previous[0].to_dict(), "already": True}
        recipe = _recipe_for(src, entry, config)
        backend = recipe.backend if recipe else detect_backend(src)
        prefixes = []
        for depend in recipe.depends if recipe else []:  # built first, for the same toolchain
            dep_url, _, dep_range = depend.partition("::")
            dep_range = dep_range.strip().removeprefix("semver=").strip()
            prefixes.append(
                install_package(dep_url.strip(), toolchain, dep_range, config=config, log=log, say=say)["prefix"]
            )
        if os.path.isdir(prefix):
            shutil.rmtree(prefix)
        say(f"Building {name} {chosen or '(default branch)'} with {toolchain.fc} ({toolchain.key}), {backend or '?'}")
        try:
            artifacts = install(
                backend, src, toolchain, prefix, name, chosen or "0", facts["description"], mode=mode, recipe=recipe,
                prefixes=tuple(prefixes), log=log, warn=say,
            )  # fmt: skip
        except BackendError as error:
            shutil.rmtree(prefix, ignore_errors=True)
            _fail(f"{name}: {error}", 1)
    receipt = Receipt(
        name=name,
        source=url,
        version=chosen or identity[:12],
        identity=identity,
        key=toolchain.key,
        prefix=prefix,
        backend=backend,
        toolchain=toolchain.to_dict(),
        files=files_under(prefix),
        modules=artifacts.modules,
        spec=package,
        constraint=constraint,
    )
    if shims and artifacts.executables:
        made, refused = link_applications(
            artifacts.executables, bin_dir or os.path.join(os.path.expanduser("~"), ".local", "bin")
        )
        receipt.shims = made
        for link in refused:
            say(f"warning: {link} exists and is not one of this package's links: left alone")
    for old in store.find(name, toolchain.key):  # the links of an older version now point to this one
        if old.version != receipt.version:
            old.shims = [s for s in old.shims if s not in receipt.shims]
            store.record(old)
    store.record(receipt)
    return {**receipt.to_dict(), "provider": provider, "pc_files": artifacts.pc_files, "already": False}


def _recipe_for(src: str, entry: Any, config: str | None):
    """The recipe of a package: the one its repository ships, else the one its index entry names, else None."""
    from ..registry.recipe import RecipeError, parse_recipe, read_index_recipe, recipe_in

    try:
        recipe = recipe_in(src)
        if recipe is None and entry is not None and entry.recipe:
            loaded = next(i for i in index_set(config).loaded if i.qualifier == entry.index)
            recipe = parse_recipe(read_index_recipe(loaded.url, entry.recipe), origin=entry.recipe)
    except (RecipeError, StopIteration) as error:
        _fail(f"recipe: {error}", 1)
    return recipe


@pkg_app.command("install")
def cmd_pkg_install(
    package: Annotated[str, typer.Argument(help="A package name (NAME or INDEX:NAME) or a source URL.")],
    version: Annotated[str | None, typer.Option("--version", help="A version range (^1.2) or an exact tag.")] = None,
    compiler: Annotated[str, typer.Option("--compiler", help="Compiler family (gnu, intel_nextgen, ...).")] = "gnu",
    fc: Annotated[
        str | None, typer.Option("--fc", help="The Fortran compiler command (default: the family's).")
    ] = None,
    mpi: Annotated[bool, typer.Option("--mpi", help="Build with the MPI wrapper (mpif90).")] = False,
    cflags: Annotated[str, typer.Option("--cflags", help="Flags added to the package's own (part of the key).")] = "",
    lflags: Annotated[str, typer.Option("--lflags", help="Link flags added (part of the key).")] = "",
    mode: Annotated[str | None, typer.Option("--mode", help="Mode of the package's fobos to build.")] = None,
    bin_dir: Annotated[str | None, typer.Option("--bin-dir", help="Where applications are linked.")] = None,
    no_shims: Annotated[bool, typer.Option("--no-shims", help="Do not link applications.")] = False,
    force: Annotated[bool, typer.Option("--force", help="Rebuild even when installed.")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", help="Show the build's own output.")] = False,
    config: _ConfigOpt = None,
    as_json: _JsonOpt = False,
) -> None:
    """Build a package with your compiler and install it into the store."""
    toolchain = _toolchain(compiler, fc, mpi, cflags, lflags)
    constraint, exact = "", ""
    if version:
        if version[:1] in "^~<>=*" or "," in version:
            constraint = version
        else:
            exact = version

    def quiet(_: str) -> None:
        pass

    def echo(message: str) -> None:
        typer.echo(message, err=True)

    receipt = install_package(
        package, toolchain, constraint, exact, mode, bin_dir, not no_shims, force, config,
        log=echo if verbose and not as_json else quiet, say=quiet if as_json else echo,
    )  # fmt: skip
    if as_json:
        typer.echo(json.dumps(receipt, indent=2))
        return
    if receipt["already"]:
        typer.echo(
            f"{receipt['name']} {receipt['version']} is already installed for {receipt['key']} (--force rebuilds)"
        )
        return
    typer.echo(f"Installed {receipt['name']} {receipt['version']} for {receipt['key']} in {receipt['prefix']}")
    if receipt["modules"]:
        typer.echo(f"  modules : {', '.join(receipt['modules'])}")
    for shim in receipt["shims"]:
        typer.echo(f"  linked  : {shim}")
    if receipt["pc_files"]:
        typer.echo(f"  use it  : export PKG_CONFIG_PATH={os.path.dirname(receipt['pc_files'][0])}")


@pkg_app.command("list")
def cmd_pkg_list(as_json: _JsonOpt = False) -> None:
    """List the installed packages (name, version, toolchain key, build system)."""
    receipts = _store().receipts()
    if as_json:
        typer.echo(json.dumps({"packages": [r.to_dict() for r in receipts]}, indent=2))
        return
    if not receipts:
        typer.echo("No package installed (fobis pkg install NAME).")
        return
    for r in sorted(receipts, key=lambda r: (r.name.lower(), r.key, r.version)):
        typer.echo(f"{r.name:<20} {r.version:<12} {r.key:<28} {r.backend:<6} {r.source}")


def _one(name: str, key: str | None, version: str | None):
    found = [r for r in _store().find(name, key or "") if not version or r.version.lstrip("v") == version.lstrip("v")]
    if not found:
        _fail(f"{name} is not installed" + (f" for {key}" if key else ""))
    if len(found) > 1:
        rows = "\n".join(f"  {r.version}  --key {r.key}" for r in found)
        _fail(f"{name} is installed {len(found)} times, choose with --key/--version:\n{rows}")
    return found[0]


@pkg_app.command("uninstall")
def cmd_pkg_uninstall(
    name: Annotated[str, typer.Argument(help="The installed package.")],
    key: _KeyOpt = None,
    version: Annotated[str | None, typer.Option("--version", help="The installed version.")] = None,
) -> None:
    """Remove an installed package: exactly the files and links its install recorded."""
    receipt = _one(name, key, version)
    removed = _store().remove(receipt)
    typer.echo(f"Removed {receipt.name} {receipt.version} ({receipt.key}): {len(removed)} file(s) and link(s)")


@pkg_app.command("path")
def cmd_pkg_path(
    name: Annotated[str, typer.Argument(help="The installed package.")],
    key: _KeyOpt = None,
    version: Annotated[str | None, typer.Option("--version", help="The installed version.")] = None,
    pkgconfig: Annotated[bool, typer.Option("--pkgconfig", help="Print its pkg-config directory instead.")] = False,
) -> None:
    """Print the install prefix of a package (for scripts, CMAKE_PREFIX_PATH, PKG_CONFIG_PATH)."""
    receipt = _one(name, key, version)
    if not pkgconfig:
        typer.echo(receipt.prefix)
        return
    ours = os.path.join("lib", "pkgconfig")
    pc = sorted(
        {os.path.dirname(f) for f in receipt.files if f.endswith(".pc") and "pkgconfig" in f.split(os.sep)},
        key=lambda d: (d != ours, d),
    )
    typer.echo(os.path.join(receipt.prefix, pc[0] if pc else ours))


@pkg_app.command("upgrade")
def cmd_pkg_upgrade(
    name: Annotated[str | None, typer.Argument(help="Upgrade only this package (default: all).")] = None,
    config: _ConfigOpt = None,
    bin_dir: Annotated[str | None, typer.Option("--bin-dir", help="Where applications are linked.")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", help="Show the build's own output.")] = False,
) -> None:
    """Install the newest version allowed by the original request, for the same toolchain; remove the old one."""
    from ..registry.index import RegistryError
    from ..registry.sources import probe
    from ..registry.toolchain import Toolchain, ToolchainError, detect

    store = _store()
    receipts = [r for r in store.receipts() if not name or r.name == name]
    if name and not receipts:
        _fail(f"{name} is not installed")
    for receipt in receipts:
        try:
            info = probe(receipt.source, inspect=False)
        except RegistryError as error:
            typer.echo(f"warning: {receipt.name}: {error}", err=True)
            continue
        from ..SemVer import resolve

        target = resolve(info.versions, receipt.constraint) if receipt.constraint else (info.latest or "")
        if not target or target.lstrip("v") == receipt.version.lstrip("v"):
            typer.echo(f"{receipt.name} {receipt.version} ({receipt.key}): up to date")
            continue
        recorded = Toolchain(**{k: v for k, v in receipt.toolchain.items() if k != "key"})
        try:
            current = detect(recorded.family, recorded.fc, recorded.mpi, recorded.cflags, recorded.lflags)
        except ToolchainError as error:
            typer.echo(f"warning: {receipt.name}: {error}", err=True)
            continue
        if current.key != receipt.key:
            typer.echo(
                f"warning: {receipt.name}: the compiler changed ({receipt.key} -> {current.key}): "
                f"installing {target} for {current.key}, the old install stays",
                err=True,
            )
        new = install_package(
            receipt.source,
            current,
            version=target,
            bin_dir=bin_dir,
            config=config,
            log=(lambda m: typer.echo(m, err=True)) if verbose else (lambda _m: None),
        )  # fmt: skip  (as pkg install: the build's own output only with --verbose)
        if current.key == receipt.key and not new["already"]:
            store.remove(receipt)
        typer.echo(f"{receipt.name}: {receipt.version} -> {new['version']} ({current.key})")
