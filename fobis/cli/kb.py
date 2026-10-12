"""kb.py — FoBiS.py ``kb`` subcommand group: knowledge packs (list, search, show, build, add, remove)."""

from __future__ import annotations

import json
import os
import shutil
import textwrap
from typing import Annotated

import typer

kb_app = typer.Typer(
    name="kb",
    help="Search the knowledge packs (Fortran, OpenMP, OpenACC, MPI references; your own packs).",
    no_args_is_help=True,
)

_ProjectOpt = Annotated[
    bool, typer.Option("--project", help="Use the project's packs (.fobis/kb) instead of the user's.")
]


def _fail(message: str) -> None:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


def _scope_dir(project: bool) -> str:
    from ..kb import project_dir, user_dir

    return project_dir() if project else user_dir()


@kb_app.command("list")
def cmd_kb_list() -> None:
    """List the installed packs (shipped, user, project)."""
    from ..kb import discover_packs

    packs = discover_packs()
    if not packs:
        typer.echo("No knowledge pack installed.")
        return
    for pack in packs:
        meta = pack.meta
        typer.echo(
            f"{pack.name:<14} {meta.get('version', '-'):<7} {pack.scope:<8} {len(pack.chunks):>4} chunks  "
            f"{meta.get('license') or 'PRIVATE':<10} {meta.get('title', '')}"
        )


@kb_app.command("search")
def cmd_kb_search(
    query: Annotated[str, typer.Argument(help="Words, symbols (firstprivate, mpi_isend) or constraint ids (C1004).")],
    pack: Annotated[
        list[str] | None, typer.Option("--pack", "-p", help="Search only these packs (repeatable).")
    ] = None,
    k: Annotated[int, typer.Option("-k", help="Number of results.")] = 5,
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output.")] = False,
) -> None:
    """Find the sections that best match QUERY."""
    from ..kb import KnowledgeBase, PackError

    try:
        kb = KnowledgeBase.load(names=pack)
    except PackError as exc:
        _fail(str(exc))
    results = kb.search(query, k=k)
    if as_json:
        payload = [
            {"id": r.chunk.id, "score": round(r.score, 3), "heading": r.chunk.heading, "text": r.chunk.text}
            for r in results
        ]
        typer.echo(json.dumps(payload, indent=2))
        return
    if not results:
        typer.echo("No match.")
        return
    for rank, result in enumerate(results, 1):
        excerpt = " ".join(result.chunk.text.split())[:220]
        typer.echo(f"{rank}. {result.chunk.id}  ({result.score:.1f})")
        typer.echo(f"   {result.chunk.heading}")
        typer.echo(textwrap.indent(textwrap.fill(excerpt, 100), "   ") + "\n")
    typer.echo("Read a section with: fobis kb show <id>")


@kb_app.command("show")
def cmd_kb_show(
    chunk_id: Annotated[str, typer.Argument(help="Section id, as printed by 'fobis kb search'.")],
    context: Annotated[int, typer.Option("--context", "-C", help="Also show N neighbouring sections.")] = 0,
) -> None:
    """Print a section (and optionally its neighbours)."""
    from ..kb import KnowledgeBase

    kb = KnowledgeBase.load()
    if chunk_id not in kb.by_id:
        _fail(f"no section '{chunk_id}' (see fobis kb search)")
    for chunk in kb.neighbours(chunk_id, before=context, after=context):
        typer.echo(f"## {chunk.heading}  [{chunk.id}]\n\n{chunk.text}\n")
    pack = kb.packs[kb.get(chunk_id).pack]
    if pack.meta.get("license"):
        credit = f"{pack.meta['license']}, {pack.meta.get('attribution', '')}"
        typer.echo(f"-- {pack.name}: {credit} (fobis kb notice {pack.name})")


@kb_app.command("notice")
def cmd_kb_notice(name: Annotated[str, typer.Argument(help="Pack name.")]) -> None:
    """Print a pack's licence, attribution and NOTICE."""
    from ..kb import discover_packs

    pack = next((p for p in discover_packs() if p.name == name), None)
    if pack is None:
        _fail(f"pack '{name}' is not installed (see fobis kb list)")
    meta = pack.meta
    typer.echo(f"{pack.name} {meta.get('version', '')}: {meta.get('title', '')}")
    typer.echo(f"License: {meta.get('license') or 'none (private pack: do not redistribute)'}")
    for key in ("attribution", "source", "source_rev"):
        if meta.get(key):
            typer.echo(f"{key.replace('_', ' ').capitalize()}: {meta[key]}")
    notice = pack.notice()
    if notice:
        typer.echo("\n" + notice.rstrip())


@kb_app.command("build")
def cmd_kb_build(
    sources: Annotated[
        list[str], typer.Argument(help="Markdown files or directories (e.g. a Claude skill directory).")
    ],
    name: Annotated[str, typer.Option("--name", help="Pack name (lower case, digits, '-').")],
    license_: Annotated[str | None, typer.Option("--license", help="Licence of the content (SPDX id).")] = None,
    title: Annotated[str, typer.Option("--title", help="One-line description.")] = "",
    attribution: Annotated[str, typer.Option("--attribution", help="Author / source to credit.")] = "",
    notice: Annotated[str | None, typer.Option("--notice", help="NOTICE file to include.")] = None,
    private: Annotated[bool, typer.Option("--private", help="Build without licence: for your own use only.")] = False,
    out: Annotated[
        str | None, typer.Option("--out", help="Output directory [default: the user or project pack dir].")
    ] = None,
    project: _ProjectOpt = False,
) -> None:
    """Build a pack from markdown and install it (user packs by default)."""
    from ..kb import PackError, Source, build_pack, skill_sources

    target = out or os.path.join(_scope_dir(project), name)
    try:
        found: list[Source] = []
        for source in sources:
            found.extend(skill_sources(source))
        meta = {"name": name, "version": "local", "title": title, "license": license_ or "", "attribution": attribution}
        count = build_pack(found, target, meta, notice=notice, allow_unlicensed=private)
    except PackError as exc:
        _fail(str(exc))
    typer.echo(f"Pack '{name}': {count} sections from {len(found)} document(s) written to {target}")


@kb_app.command("add")
def cmd_kb_add(
    path: Annotated[str, typer.Argument(help="A built pack directory (with pack.ini and index.json).")],
    project: _ProjectOpt = False,
) -> None:
    """Install an already built pack."""
    from ..kb import PackError, load_pack

    try:
        pack = load_pack(path)
    except PackError as exc:
        _fail(str(exc))
    target = os.path.join(_scope_dir(project), pack.name)
    if os.path.abspath(target) != os.path.abspath(path):
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(path, target)
    typer.echo(f"Pack '{pack.name}' installed in {target}")


@kb_app.command("remove")
def cmd_kb_remove(name: Annotated[str, typer.Argument(help="Pack name.")], project: _ProjectOpt = False) -> None:
    """Remove a user (or project) pack; shipped packs cannot be removed."""
    target = os.path.join(_scope_dir(project), name)
    if not os.path.isfile(os.path.join(target, "pack.ini")):
        _fail(f"no {'project' if project else 'user'} pack '{name}' in {os.path.dirname(target)}")
    shutil.rmtree(target)
    typer.echo(f"Pack '{name}' removed from {os.path.dirname(target)}")
