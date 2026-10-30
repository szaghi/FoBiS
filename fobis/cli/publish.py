"""publish.py — FoBiS.py ``publish`` command: make the current project's release available without any server.

``--archive DIR`` writes the release tarball (``git archive`` of the tag) and its entry of ``fortran-releases.toml``
into DIR, which any static web server can serve; ``--index FILE`` adds or refreshes the project's entry in an index
the user controls. Publishing a version is pushing its tag: neither step is needed for a git source.
"""

from __future__ import annotations

import hashlib
import os
from typing import Annotated

import typer

from ._app import app
from .registry import _fail


def _git(*args: str) -> str:
    from ..registry.index import run_git

    result = run_git(*args)
    if result.returncode != 0:
        lines = result.stderr.strip().splitlines()
        _fail(f"git {' '.join(args)}: {lines[-1] if lines else 'failed'}", 1)
    return result.stdout.strip()


@app.command("publish")
def cmd_publish(
    archive: Annotated[
        str | None, typer.Option("--archive", help="Write the release tarball and its manifest entry into DIR.")
    ] = None,
    index: Annotated[
        str | None, typer.Option("--index", help="Add or refresh this project's entry in the index FILE.")
    ] = None,
    version: Annotated[
        str | None, typer.Option("--version", help="Tag to publish (default: the latest tag of HEAD).")
    ] = None,
    name: Annotated[str | None, typer.Option("--name", help="Package name (default: fobos [project] name).")] = None,
    source: Annotated[
        str | None, typer.Option("--source", help="Source URL written in the index (default: the origin remote).")
    ] = None,
) -> None:
    """Publish the current project: a release archive for static hosting, an entry of an index."""
    from ..registry.index import Index, Package, RegistryError, dump_index, load_index
    from ..registry.manifest import MANIFEST, SourceError, parse_manifest
    from ..registry.sources import inspect_tree, public_url, read_manifests

    if not archive and not index:
        _fail("give --archive DIR and/or --index FILE")
    top = _git("rev-parse", "--show-toplevel")
    facts = read_manifests(top)
    package = (name or facts["name"] or os.path.basename(top)).strip()
    if archive:
        tag = version or _git("describe", "--tags", "--abbrev=0")
        _git("rev-parse", "--verify", "--quiet", f"refs/tags/{tag}")
        plain = tag.lstrip("v")
        os.makedirs(archive, exist_ok=True)
        manifest_path = os.path.join(archive, MANIFEST)
        releases = []
        if os.path.isfile(manifest_path):
            with open(manifest_path, encoding="utf-8") as fh:
                try:
                    releases = parse_manifest(fh.read(), manifest_path).releases
                except SourceError as error:
                    _fail(str(error))
        if any(r.version.lstrip("v") == plain for r in releases):
            _fail(f"{package} {plain} is already published in {manifest_path}: a release never changes")
        filename = f"{package}-{plain}.tar.gz"
        target = os.path.join(archive, filename)
        _git(
            "-C", top, "archive", "--format=tar.gz", f"--prefix={package}-{plain}/", "-o", os.path.abspath(target), tag
        )
        with open(target, "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
        lines = ["schema = 1", f'name = "{package}"']
        entries = [(plain, filename, digest)] + [(r.version, os.path.basename(r.archive), r.sha256) for r in releases]
        for rel_version, rel_archive, rel_sha in entries:
            lines += [
                "",
                "[[release]]",
                f'version = "{rel_version}"',
                f'archive = "{rel_archive}"',
                f'sha256 = "{rel_sha}"',
            ]
        tmp = manifest_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        os.replace(tmp, manifest_path)
        typer.echo(f"Wrote {target} and its entry in {manifest_path} (sha256 {digest[:16]}...)")
    if index:
        if not source:
            origin = _git("remote", "get-url", "origin")
            source = public_url(origin)
        current = Index(name="")
        if os.path.isfile(index):
            with open(index, encoding="utf-8") as fh:
                try:
                    current = load_index(fh.read(), origin=index)
                except RegistryError as error:
                    _fail(str(error))
        from ..registry.sources import SourceInfo

        info = inspect_tree(top, SourceInfo(url=source, provider=""))
        old = current.packages.get(package)
        entry = Package(
            name=package,
            source=source,
            description=info.description,
            license=info.license,
            provides=list(info.modules),
            builds=list(info.builds),
            keywords=old.keywords if old else [],
            mirrors=old.mirrors if old else [],
            recipe=old.recipe if old else "",
        )
        current.packages[package] = entry
        os.makedirs(os.path.dirname(os.path.abspath(index)), exist_ok=True)
        tmp = index + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(dump_index(current))
        os.replace(tmp, index)
        typer.echo(f"{'Refreshed' if old else 'Added'} {package} in {index} ({len(entry.provides)} module(s))")
