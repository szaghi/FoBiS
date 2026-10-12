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
    """A size in GB, or MB below 1 GB."""
    return f"{size / 1e9:.1f} GB" if size >= 1e9 else f"{size / 1e6:.0f} MB"


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


runtime_app = typer.Typer(
    name="runtime", help="Install, list and remove the llama.cpp runtime (llama-server).", no_args_is_help=True
)
llm_app.add_typer(runtime_app, name="runtime")


def _manager():
    from ..llm.runtime import RuntimeManager

    return RuntimeManager()


@runtime_app.command("install")
def cmd_runtime_install(
    variant: Annotated[
        str, typer.Option("--variant", help="auto, cpu, metal, cuda12, cuda13, vulkan, rocm or sycl.")
    ] = "auto",
    build: Annotated[
        str | None, typer.Option("--build", help="A llama.cpp build tag other than the pinned one.")
    ] = None,
    sha256: Annotated[str | None, typer.Option("--sha256", help="Expected sha256 of a non-pinned build.")] = None,
    trust: Annotated[bool, typer.Option("--trust", help="Accept a non-pinned build without a known sha256.")] = False,
) -> None:
    """Download, verify and install llama-server (the pinned build by default)."""
    from ..llm import LLMError

    try:
        runtime, reason = _manager().install(
            variant=variant, build=build, sha256=sha256, trust=trust, progress=_progress()
        )
    except LLMError as exc:
        _fail(str(exc))
    typer.echo(f"Installed {runtime.name} ({reason})\n  {runtime.binary}\n  {runtime.version or 'version: unknown'}")
    if not runtime.version:
        typer.echo(
            "Warning: llama-server did not run (--version failed). On an older system set "
            "'runtime = /path/to/llama-server' in the [llm] section of the user config.",
            err=True,
        )


@runtime_app.command("list")
def cmd_runtime_list() -> None:
    """List the installed llama.cpp builds."""
    from ..llm.pins import PINNED_BUILD
    from ..llm.runtime import available_variants, platform_key

    installed = _manager().installed()
    if not installed:
        typer.echo("No runtime installed. Install with: fobis llm runtime install")
    for runtime in installed:
        pinned = " (pinned)" if runtime.build == PINNED_BUILD else ""
        typer.echo(f"{runtime.name:<18}{pinned:<10} {runtime.version}")
    key = platform_key()
    typer.echo(f"\nPinned build {PINNED_BUILD}; variants for {key[0]}/{key[1]}: {', '.join(available_variants(key))}")


@runtime_app.command("remove")
def cmd_runtime_remove(name: Annotated[str, typer.Argument(help="<build>-<variant>, as listed.")]) -> None:
    """Remove an installed llama.cpp build."""
    from ..llm import LLMError

    try:
        runtime = _manager().remove(name)
    except LLMError as exc:
        _fail(str(exc))
    typer.echo(f"Removed {runtime.name}")


def _llm_config(provider: str | None, model: str | None):
    from ..llm import LLMConfig
    from ..UserConfig import UserConfig

    return LLMConfig.from_user_config(UserConfig(), provider=provider, model=model)


@llm_app.command("ask")
def cmd_llm_ask(
    prompt: Annotated[str, typer.Argument(help="The question; '-' reads it from standard input.")],
    schema: Annotated[
        str | None, typer.Option("--schema", help="JSON Schema file: the answer is constrained to it.")
    ] = None,
    system: Annotated[str | None, typer.Option("--system", help="System prompt.")] = None,
    provider: Annotated[str | None, typer.Option("--provider", help="managed, ollama or openai.")] = None,
    model: Annotated[str | None, typer.Option("--model", "-m", help="Model (alias or spec for managed).")] = None,
) -> None:
    """Ask the configured model a question (smoke test, scripting); the answer streams to standard output."""
    from ..llm import LLMError, get_provider, messages

    text = sys.stdin.read() if prompt == "-" else prompt
    constraint = None
    if schema:
        try:
            with open(schema, encoding="utf-8") as handle:
                constraint = json.load(handle)
        except (OSError, ValueError) as exc:
            _fail(f"cannot read the schema {schema}: {exc}")
    client = None
    try:
        client = get_provider(_llm_config(provider, model), on_status=lambda m: typer.echo(m, err=True))
        client.chat(
            messages(text, system=system),
            schema=constraint,
            temperature=0.0,
            on_token=lambda t: (sys.stdout.write(t), sys.stdout.flush()),
        )
        sys.stdout.write("\n")
    except LLMError as exc:
        _fail(str(exc))
    finally:
        if client is not None and hasattr(client, "close"):
            client.close()


@llm_app.command("doctor")
def cmd_llm_doctor(
    sample: Annotated[
        bool, typer.Option("--sample/--no-sample", help="Start the model and time a short answer.")
    ] = True,
) -> None:
    """Check the local LLM setup: platform, runtime, model, and (managed) a timed sample answer."""
    import time

    from ..llm import LLMError, get_provider, messages
    from ..llm.pins import PINNED_BUILD
    from ..llm.runtime import available_variants, detect_variant, platform_key, server_version

    ok = True

    def report(label: str, value: str, good: bool = True) -> None:
        nonlocal ok
        ok = ok and good
        typer.echo(f"{'ok ' if good else 'BAD'}  {label:<10} {value}")

    try:
        cfg = _llm_config(None, None)
    except LLMError as exc:
        _fail(str(exc))
    key = platform_key()
    report("provider", f"{cfg.provider}  (model {cfg.model})")
    if cfg.provider != "managed":
        report("server", f"{cfg.url} (not managed by fobis: start it yourself)")
    else:
        try:
            variant, reason = detect_variant(key)
            report(
                "platform",
                f"{key[0]}/{key[1]}, variants {', '.join(available_variants(key))}; auto -> {variant} ({reason})",
            )
        except LLMError as exc:
            report("platform", str(exc), False)
        try:
            binary = _manager().resolve(cfg.runtime, cfg.runtime_variant)
            version = server_version(binary)
            report(
                "runtime", f"{binary}\n                {version or 'does not run (--version failed)'}", bool(version)
            )
            if cfg.runtime == "pinned" and f"build {PINNED_BUILD[1:]}" not in version:
                report("build", f"expected {PINNED_BUILD}", False)
        except LLMError as exc:
            report("runtime", str(exc), False)
        try:
            report("model", _store().locate(cfg.model))
        except LLMError as exc:
            report("model", str(exc), False)
    if sample and ok:
        client = None
        try:
            client = get_provider(cfg)
            started = time.monotonic()
            if hasattr(client, "start"):
                client.start()
                report("start", f"server ready in {time.monotonic() - started:.1f} s")
            started = time.monotonic()
            answer = client.chat(
                messages("Reply with the single word: ready"), temperature=0.0, seed=0, max_tokens=16
            ).text.strip()
            speed = client.server.generation_speed() if getattr(client, "server", None) else None
            detail = f", {speed:.0f} tokens/s" if speed else ""
            report("sample", f"{answer!r} in {time.monotonic() - started:.1f} s{detail}")
        except LLMError as exc:
            report("sample", str(exc), False)
        finally:
            if client is not None and hasattr(client, "close"):
                client.close()
    if not ok:
        raise typer.Exit(1)
