"""llm.py — FoBiS.py ``llm`` subcommand group: the local LLM harness (model store: pull, list, rm, recommended)."""

from __future__ import annotations

import json
import sys
from typing import Annotated

import typer

llm_app = typer.Typer(
    name="llm",
    help="Manage the local LLM: models pulled from the Hugging Face Hub (nothing is downloaded implicitly).",
    no_args_is_help=True,
)


def _fail(message: str) -> None:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


def _gb(size: int) -> str:
    return f"{size / 1e9:.1f} GB"


def _store():
    from ..llm.models import ModelStore

    return ModelStore()


def _progress():
    """A progress printer on stderr: one line per file, rewritten in place on a terminal."""
    tty = sys.stderr.isatty()
    last = {"name": "", "percent": -1}

    def report(name: str, done: int, total: int) -> None:
        percent = int(100 * done / total) if total else 100
        if name == last["name"] and percent == last["percent"]:
            return
        if tty:
            end = "\n" if done >= total else ""
            sys.stderr.write(f"\r  {name}: {percent:3d}% of {_gb(total)}{end}")
        elif percent % 10 == 0:
            sys.stderr.write(f"  {name}: {percent}% of {_gb(total)}\n")
        sys.stderr.flush()
        last.update(name=name, percent=percent)

    return report


@llm_app.command("recommended")
def cmd_llm_recommended() -> None:
    """List curated models (alias, size, licence): nothing is downloaded."""
    from ..llm.models import RECOMMENDED

    for model in RECOMMENDED.values():
        typer.echo(f"{model.alias:<14} {_gb(model.size):>8}  {model.license:<11} {model.note}")
    typer.echo("\nPull one with: fobis llm pull <alias>   (or any hf:<org>/<repo>[@<rev>]/<file>.gguf)")


@llm_app.command("pull")
def cmd_llm_pull(
    model: Annotated[
        str, typer.Argument(help="Alias (see 'fobis llm recommended') or hf:<org>/<repo>[@<rev>]/<file>.gguf.")
    ],
) -> None:
    """Download a model into the store (resumable; verified against the Hub's sha256)."""
    from ..llm import LLMError

    store = _store()
    try:
        stored, downloaded = store.pull(model, progress=_progress())
    except LLMError as exc:
        _fail(str(exc))
    if downloaded:
        typer.echo(f"Pulled {stored.spec} ({_gb(stored.size)})\n  {stored.path}")
    else:
        typer.echo(f"Already in the store: {stored.spec}\n  {stored.path}")


@llm_app.command("list")
def cmd_llm_list(
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output.")] = False,
) -> None:
    """List the models in the store."""
    from ..llm import LLMError

    store = _store()
    try:
        entries = store.entries()
    except LLMError as exc:
        _fail(str(exc))
    if as_json:
        rows = [
            {"spec": m.spec, "path": m.path, "size": m.size, "revision": m.revision, "pulled_at": m.pulled_at}
            for m in entries
        ]
        typer.echo(json.dumps(rows, indent=2))
        return
    if not entries:
        typer.echo(f"No model in {store.root}. See: fobis llm recommended")
        return
    for m in entries:
        typer.echo(f"{_gb(m.size):>8}  {m.pulled_at}  {m.spec}")
    typer.echo(f"\nStore: {store.root}")


@llm_app.command("rm")
def cmd_llm_rm(
    model: Annotated[str, typer.Argument(help="Alias or spec; a spec without @revision removes every revision.")],
) -> None:
    """Remove a model from the store."""
    from ..llm import LLMError

    try:
        removed = _store().remove(model)
    except LLMError as exc:
        _fail(str(exc))
    for m in removed:
        typer.echo(f"Removed {m.spec} ({_gb(m.size)})")
