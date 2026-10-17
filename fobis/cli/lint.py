"""lint.py — FoBiS.py ``lint`` subcommand: rule-based analysis of Fortran sources."""

from __future__ import annotations

from typing import Annotated

import typer

from ._app import _ns, app
from ._completions import _complete_fobos_varset
from ._constants import __extensions_inc__, __extensions_parsed__
from ._options import FciOpt, FobosOpt, ModeOpt, SrcOpt


@app.command("lint")
def cmd_lint(
    ctx: typer.Context,
    paths: Annotated[
        list[str] | None,
        typer.Argument(help="Files or directories to lint [default: the sources of the fobos mode, else ./]"),
    ] = None,
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    src: SrcOpt = None,
    select: Annotated[
        list[str] | None,
        typer.Option(
            "--select",
            help="Rule ids or prefixes to run (repeatable, comma-separated; 'ALL' for every rule). "
            "Replaces the default set.",
        ),
    ] = None,
    ignore: Annotated[
        list[str] | None,
        typer.Option("--ignore", help="Rule ids or prefixes to skip (repeatable, comma-separated)."),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text, json, sarif or github."),
    ] = "text",
    baseline: Annotated[
        str | None,
        typer.Option("--baseline", help="Baseline file: findings recorded there are not reported."),
    ] = None,
    update_baseline: Annotated[
        bool,
        typer.Option("--update-baseline", help="Record all current findings into the baseline file and exit."),
    ] = False,
    compiler_feedback: Annotated[
        str | None,
        typer.Option(
            "--compiler-feedback",
            help="Build log with compiler optimisation reports (nvfortran -Minfo, gfortran -fopt-info); '-' reads stdin.",
        ),
    ] = None,
    diff: Annotated[
        bool,
        typer.Option("--diff", help="Print the automatic fixes as a unified diff; change nothing."),
    ] = False,
    fix: Annotated[
        bool,
        typer.Option("--fix", help="Apply the automatic fixes to the files, then report what remains."),
    ] = False,
    exit_zero: Annotated[
        bool,
        typer.Option("--exit-zero", help="Exit 0 even when findings are reported."),
    ] = False,
    list_rules: Annotated[bool, typer.Option("--list-rules", help="List every rule and exit.")] = False,
    explain: Annotated[str | None, typer.Option("--explain", help="Explain a rule (by id) and exit.")] = None,
    deep: Annotated[
        bool,
        typer.Option(
            "--deep",
            help="Review the findings with the LLM, region by region: a cited verdict per finding (confirmed, "
            "dismissed, uncertain) and advisory concerns. Nothing is hidden; the exit status is unchanged.",
        ),
    ] = False,
    deep_max: Annotated[
        int, typer.Option("--deep-max", help="Review at most this many regions (most severe first).")
    ] = 10,
    deep_context: Annotated[
        bool,
        typer.Option("--deep-context", help="With --deep or --ask: print what the model would receive, run no model."),
    ] = False,
    ask: Annotated[
        str | None,
        typer.Option(
            "--ask",
            help="Ask a question about the code around FILE:LINE (given as the path), answered with citations.",
        ),
    ] = None,
    varset: Annotated[
        str | None,
        typer.Option(
            "--varset",
            help="Apply one or more [varset:NAME] sections' $variable bindings before linting.",
            autocompletion=_complete_fobos_varset,
        ),
    ] = None,
):
    """Report bug-prone and obsolescent Fortran constructs (rules: fobis lint --list-rules)."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = lint_namespace(
        which="lint",
        lint_paths=paths or [],
        lint_select=select or [],
        lint_ignore=ignore or [],
        lint_format=output_format,
        lint_baseline=baseline,
        lint_update_baseline=update_baseline,
        lint_exit_zero=exit_zero,
        lint_diff=diff,
        lint_compiler_feedback=compiler_feedback,
        lint_fix=fix,
        lint_list_rules=list_rules,
        lint_explain=explain,
        lint_deep=deep or deep_context,
        lint_deep_max=deep_max,
        lint_deep_context=deep_context,
        lint_ask=ask,
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        src=src or ["./"],
        varset=varset or "",
    )


def lint_namespace(**fields):
    """The ``cliargs`` of a lint-like command (``lint``, ``review``): the build settings a fobos mode may
    override, with their defaults, plus *fields*."""
    defaults = {
        "lmodes": False,
        "build_dir": "./",
        "obj_dir": "./obj/",
        "mod_dir": "./mod/",
        "lib_dir": [],
        "include": [],
        "exclude_dirs": [],
        "disable_recursive_search": False,
        "target": None,
        "output": None,
        "exclude": [],
        "libs": [],
        "vlibs": [],
        "ext_libs": [],
        "ext_vlibs": [],
        "dependon": [],
        "inc": list(__extensions_inc__),
        "extensions": list(__extensions_parsed__),
        "build_all": False,
        "compiler": "gnu",
        "fc": None,
        "cflags": None,
        "lflags": None,
        "modsw": None,
        "mpi": False,
        "openmp": False,
        "openmp_offload": False,
        "coarray": False,
        "coverage": False,
        "profile": False,
        "build_profile": "",
        "features": "",
        "intrinsic_modules": [],
        "no_default_features": False,
        "pre_build": [],
        "post_build": [],
        "no_auto_discover": False,
        "examples": False,
        "target_filter": [],
        "mklib": None,
        "ar": "ar",
        "arflags": "-rcs",
        "ranlib": "ranlib",
        "cflags_heritage": False,
        "track_build": False,
        "preprocessor": None,
        "preproc": None,
        "preprocessor_args": "",
        "preprocessor_no_o": False,
        "preprocessor_dir": None,
        "preprocessor_ext": [],
        "force_compile": False,
        "colors": False,
        "log": False,
        "graph": False,
        "quiet": False,
        "verbose": False,
        "jobs": 1,
        "makefile": None,
        "json_output": False,
        "active_features": [],
    }
    return _ns(**{**defaults, **fields})
