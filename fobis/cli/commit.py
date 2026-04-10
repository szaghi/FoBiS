"""commit.py — FoBiS.py ``commit`` subcommand."""

from typing import Annotated

import typer

from ._app import _ns, app

_BackendOpt = Annotated[
    str | None,
    typer.Option("--backend", "-b", help='LLM backend: "ollama" or "openai".'),
]
_UrlOpt = Annotated[
    str | None,
    typer.Option("--url", "-u", help="Base URL of the LLM server."),
]
_ModelOpt = Annotated[
    str | None,
    typer.Option("--model", "-m", help="Model identifier to use."),
]
_MaxDiffOpt = Annotated[
    int | None,
    typer.Option("--max-diff", help="Maximum staged-diff characters sent to the model."),
]
_RefinePasses = Annotated[
    int | None,
    typer.Option(
        "--refine-passes",
        help="Critique-and-rewrite iterations after the initial draft (0 = single pass). "
        "Recommended: 1-3 for small/fast models.",
    ),
]
_ApplyOpt = Annotated[
    bool,
    typer.Option("--apply", help="Run `git commit` with the generated message after review."),
]
_ConfigOpt = Annotated[
    str | None,
    typer.Option("--config", "-c", help="Path to a custom FoBiS user config file."),
]
_ShowConfigOpt = Annotated[
    bool,
    typer.Option("--show-config", help="Show effective LLM configuration and exit."),
]
_InitConfigOpt = Annotated[
    bool,
    typer.Option("--init-config", help="Create a commented default config file and exit."),
]


@app.command("commit")
def cmd_commit(
    ctx: typer.Context,
    backend: _BackendOpt = None,
    url: _UrlOpt = None,
    model: _ModelOpt = None,
    max_diff: _MaxDiffOpt = None,
    refine_passes: _RefinePasses = None,
    apply: _ApplyOpt = False,
    config: _ConfigOpt = None,
    show_config: _ShowConfigOpt = False,
    init_config: _InitConfigOpt = False,
):
    """Generate a Conventional Commits message for staged changes via a local LLM."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _ns(
        which="commit",
        backend=backend,
        url=url,
        model=model,
        max_diff=max_diff,
        refine_passes=refine_passes,
        apply=apply,
        config=config,
        show_config=show_config,
        init_config=init_config,
        # unused by commit but required by FoBiSConfig common path
        fobos=None,
        fobos_case_insensitive=False,
        mode=None,
        lmodes=False,
        print_fobos_template=False,
        colors=False,
        log=False,
        quiet=False,
        verbose=False,
    )
