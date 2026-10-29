"""audit.py — FoBiS.py ``audit`` command: advisories of the fetched dependencies, and witnesses of their tags.

There is no central advisory database: each package publishes ``fortran-advisories.toml`` (see
`fobis.registry.advisories`), read here from its source for the version the lock records. ``--witness`` compares the
commit each locked tag names at the source with the one it names at every mirror of the spec and with the lock: a
disagreement means the tag was moved somewhere (several independent copies instead of one central checksum database).
"""

from __future__ import annotations

import configparser
import json
import os
from typing import Annotated

import typer

from ._app import app
from .registry import _fail


def _deps_dir(fobos: str) -> tuple[str, dict[str, str]]:
    config = configparser.RawConfigParser(strict=False)
    config.read(fobos, encoding="utf-8")
    specs = dict(config.items("dependencies")) if config.has_section("dependencies") else {}
    deps_dir = specs.pop("deps_dir", ".fobis_deps").strip()
    specs.pop("transitive", None)
    base = os.path.dirname(os.path.abspath(fobos))
    return (deps_dir if os.path.isabs(deps_dir) else os.path.join(base, deps_dir)), specs


@app.command("audit")
def cmd_audit(
    witness: Annotated[
        bool, typer.Option("--witness", help="Also check every locked tag against the mirrors and the lock.")
    ] = False,
    fobos: Annotated[str, typer.Option("--fobos", "-f", help="The project's fobos.")] = "fobos",
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output.")] = False,
) -> None:
    """Report the advisories that affect the fetched dependencies (exit 1 when one does)."""
    from ..Fetcher import Fetcher
    from ..registry.advisories import read_advisories, tag_commits
    from ..registry.index import RegistryError

    if not os.path.isfile(fobos):
        _fail(f"{fobos} not found")
    deps_dir, specs = _deps_dir(fobos)
    lock_path = os.path.join(deps_dir, "fobos.lock")
    if not os.path.isfile(lock_path):
        _fail("no fobos.lock: run 'fobis fetch' first (the audit reads the versions it recorded)")
    lock = configparser.RawConfigParser()
    lock.read(lock_path)
    fetcher = Fetcher(deps_dir=deps_dir)
    report, problems, notes = [], [], []
    for name in lock.sections():
        entry = dict(lock.items(name))
        url = entry.get("url")
        if not url:  # a path dependency: nothing published to audit
            continue
        provider = entry.get("provider", "git")
        version = entry.get("version") or entry.get("resolved") or entry.get("tag") or ""
        row = {"name": name, "url": url, "version": version, "advisories": [], "witnesses": []}
        try:
            advisories = read_advisories(url, provider)
        except RegistryError as error:
            notes.append(f"{name}: {error}")
            advisories = []
        if not version and advisories:
            notes.append(f"{name}: not pinned to a version ({entry.get('branch') or entry.get('rev')}): "
                         f"{len(advisories)} advisory(-ies) published, check them by hand")  # fmt: skip
        for advisory in advisories:
            if version and advisory.affects(version):
                row["advisories"].append(advisory.to_dict())
                problems.append(f"{name} {version}: {advisory.id} ({advisory.severity}) {advisory.summary}")
        if (witness and provider == "git" and entry.get("tag")) or (witness and entry.get("resolved")):
            tag = entry.get("resolved") or entry.get("tag")
            try:
                parsed = fetcher.parse_dep_spec(specs.get(name, url))
            except ValueError:
                parsed = {}
            mirrors = [m.strip() for m in parsed.get("mirror", "").split(",") if m.strip()]
            for location in [url, *mirrors]:
                try:
                    commit = tag_commits(location).get(tag, "")
                except RegistryError as error:
                    row["witnesses"].append({"location": location, "commit": "", "agrees": None, "error": str(error)})
                    continue
                agrees = commit == entry.get("commit", "")
                row["witnesses"].append({"location": location, "commit": commit, "agrees": agrees})
                if not agrees:
                    problems.append(
                        f"{name}: tag {tag} names {commit[:12] or 'nothing'} at {location}, the lock recorded "
                        f"{entry.get('commit', '')[:12]}"
                    )
        report.append(row)
    if as_json:
        typer.echo(json.dumps({"dependencies": report, "problems": problems, "notes": notes}, indent=2))
    else:
        for row in report:
            state = "AFFECTED" if row["advisories"] else "ok"
            typer.echo(f"{row['name']:<20} {row['version'] or '-':<12} {state}")
            for advisory in row["advisories"]:
                typer.echo(f"    {advisory['id']} [{advisory['severity']}] {advisory['summary']} {advisory['url']}")
            for w in row["witnesses"]:
                verdict = {True: "agrees", False: "DIFFERS", None: "unreachable"}[w["agrees"]]
                typer.echo(f"    witness {w['location']}: {verdict}")
        for note in notes:
            typer.echo(f"note: {note}", err=True)
        if not report:
            typer.echo("No fetched dependency to audit.")
    if problems:
        raise typer.Exit(1)
