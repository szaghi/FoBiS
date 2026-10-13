"""ask.py — FoBiS.py ``ask`` subcommand: questions answered from the knowledge packs and the project, with citations."""

from __future__ import annotations

import json
import sys
from typing import Annotated

import typer

from ._app import app


def _fail(message: str) -> None:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


@app.command("ask")
def cmd_ask(
    question: Annotated[str, typer.Argument(help="The question; '-' reads it from standard input.")],
    project: Annotated[
        list[str] | None,
        typer.Option("--project", "-p", help="Also search the procedures of these source directories (repeatable)."),
    ] = None,
    pack: Annotated[list[str] | None, typer.Option("--pack", help="Search only these packs (repeatable).")] = None,
    k: Annotated[int, typer.Option("-k", help="Number of sections given to the model.")] = 6,
    show_context: Annotated[
        bool, typer.Option("--show-context", help="Print what the model would receive, and stop (no model is run).")
    ] = False,
    verbose: Annotated[bool, typer.Option("--verbose", help="Also print the statements dropped as uncited.")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output.")] = False,
    provider: Annotated[str | None, typer.Option("--provider", help="managed, ollama or openai.")] = None,
    model: Annotated[str | None, typer.Option("--model", "-m", help="Model (alias or spec for managed).")] = None,
) -> None:
    """Answer a question from the knowledge packs (and, with --project, the project's procedures), citing sources.

    Every statement of the answer cites the sections it comes from; statements citing nothing are dropped.
    """
    from ..ai.ask import PROJECT_PACK, ask, build_bundle, project_pack
    from ..ai.grounding import load_prompt, render_answer, to_json
    from ..kb import KnowledgeBase, PackError

    text = sys.stdin.read().strip() if question == "-" else question.strip()
    if not text:
        _fail("empty question")
    try:
        kb = KnowledgeBase.load(names=pack)
    except PackError as exc:
        _fail(str(exc))
    if project:
        from ..analysis import read_source
        from ..lint.engine import analyse, discover_files
        from ._constants import __extensions_parsed__

        analysed = []
        for path in discover_files(project, __extensions_parsed__):
            try:
                analysed.append(analyse(read_source(path), path))
            except OSError:
                continue
        kb = KnowledgeBase([*kb.packs.values(), project_pack(analysed)])
        pack = [*pack, PROJECT_PACK] if pack else None
    bundle = build_bundle(text, kb, k=k, packs=pack)
    if show_context and as_json:  # the retrieved, citable sections: what an agent reasons on itself
        sources = [
            {"label": label, "id": src.id, "title": src.title, "text": src.text}
            for label, src in zip(bundle.labels, bundle.sources, strict=True)
        ]
        typer.echo(json.dumps({"question": text, "sources": sources}, indent=2))
        return
    if show_context:
        typer.echo("=== system prompt ===\n" + load_prompt("ask") + "\n=== user message ===\n" + bundle.render())
        return
    if not bundle.sources:
        _fail("no knowledge-pack section matches the question: rephrase it, or check with 'fobis kb search'")
    from ..llm import LLMConfig, LLMError, get_provider
    from ..UserConfig import UserConfig

    client = None
    try:
        cfg = LLMConfig.from_user_config(UserConfig(), provider=provider, model=model)
        client = get_provider(cfg, on_status=lambda m: typer.echo(m, err=True))
        result = ask(bundle, client)
    except LLMError as exc:
        _fail(str(exc))
    finally:
        if client is not None and hasattr(client, "close"):
            client.close()
    if as_json:
        typer.echo(json.dumps(to_json(result), indent=2))
    else:
        typer.echo(render_answer(result, verbose=verbose))
