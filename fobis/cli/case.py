"""case.py — FoBiS.py ``case`` sub-app (list, run) and the ``provenance`` command (verification, phase V1)."""

from __future__ import annotations

from typing import Annotated

import typer

from ._app import _ns, app
from ._options import FciOpt, FobosOpt, JsonOpt, ModeOpt, ShadowOpt

case_app = typer.Typer(
    name="case",
    help="Run the cases declared in the fobos ([case:NAME]) and extract their quantities.",
    no_args_is_help=True,
)
app.add_typer(case_app)


def _case_ns(action: str, **fields):
    return _ns(
        which="case",
        case_action=action,
        lmodes=False,
        colors=False,
        log=False,
        quiet=False,
        verbose=False,
        **fields,
    )


@case_app.command("list")
def cmd_case_list(
    ctx: typer.Context,
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    json_output: JsonOpt = False,
):
    """List the cases declared in the fobos."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _case_ns(
        "list", fobos=fobos, fobos_case_insensitive=fobos_case_insensitive, mode=None, json_output=json_output
    )


@case_app.command("run")
def cmd_case_run(
    ctx: typer.Context,
    names: Annotated[list[str] | None, typer.Argument(help="Cases to run [default: all]")] = None,
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    shadow: ShadowOpt = None,
    json_output: JsonOpt = False,
):
    """Build and run cases; report their quantities, the status of each run and its provenance."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _case_ns(
        "run",
        case_names=names or [],
        case_mode=mode,
        case_shadow=shadow,
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=None,  # the case's own mode is used; --mode overrides it per run, not for loading the fobos
        json_output=json_output,
    )


@app.command("provenance")
def cmd_provenance(
    ctx: typer.Context,
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    json_output: JsonOpt = False,
):
    """Print what a result produced now would depend on: commit, dependency pins, compiler, flags, machine."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _ns(
        which="provenance",
        prov_mode=mode,
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=None,
        lmodes=False,
        colors=False,
        log=False,
        quiet=False,
        verbose=False,
        json_output=json_output,
    )


@app.command("verify")
def cmd_verify(
    ctx: typer.Context,
    names: Annotated[list[str] | None, typer.Argument(help="Cases to verify [default: all]")] = None,
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    shadow: ShadowOpt = None,
    update: Annotated[
        bool,
        typer.Option("--update", help="Accept the runs as the new references (written to the references directory)."),
    ] = False,
    repeat: Annotated[
        int,
        typer.Option("--repeat", min=1, help="Run each case N times; any difference between the runs is reported."),
    ] = 1,
    json_output: JsonOpt = False,
):
    """Run cases and compare their quantities with the stored references, within each quantity's tolerance."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _ns(
        which="verify",
        verify_names=names or [],
        verify_mode=mode,
        verify_shadow=shadow,
        verify_update=update,
        verify_repeat=repeat,
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=None,
        lmodes=False,
        colors=False,
        log=False,
        quiet=False,
        verbose=False,
        json_output=json_output,
    )


def _csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


@app.command("matrix")
def cmd_matrix(
    ctx: typer.Context,
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    modes: Annotated[
        str | None, typer.Option("--modes", help="Comma-separated fobos modes [default: every mode].")
    ] = None,
    shadows: Annotated[
        str,
        typer.Option(
            "--shadows",
            help="Comma-separated shadows: none (the mode's own flags), checks, sanitize, strict.",
        ),
    ] = "none,checks",
    compilers: Annotated[
        str | None,
        typer.Option("--compilers", help="Keep the modes whose compiler (or family: gnu, intel, nvfortran) is listed."),
    ] = None,
    verify: Annotated[
        bool, typer.Option("--verify", help="Also run the declared cases: references and cross-cell agreement.")
    ] = False,
    recheck: Annotated[
        bool, typer.Option("--recheck", help="Run failed tests and cases of a cell again under the checks shadow.")
    ] = False,
    no_tests: Annotated[bool, typer.Option("--no-tests", help="Do not run the test programs.")] = False,
    json_output: JsonOpt = False,
):
    """Build, test (and verify) every mode x shadow combination available on this machine."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _ns(
        which="matrix",
        matrix_modes=_csv(modes),
        matrix_shadows=_csv(shadows),
        matrix_compilers=_csv(compilers),
        matrix_verify=verify,
        matrix_recheck=recheck,
        matrix_no_tests=no_tests,
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=None,
        lmodes=False,
        colors=False,
        log=False,
        quiet=False,
        verbose=False,
        json_output=json_output,
    )


@app.command("assess")
def cmd_assess(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The case to assess")],
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    families: Annotated[
        str | None,
        typer.Option(
            "--families",
            help="Comma-separated: precision, rounding, compiler, parallel, inputs, refinement "
            "[default: the case's [assess:NAME] families, else rounding].",
        ),
    ] = None,
    samples: Annotated[
        int | None, typer.Option("--samples", min=2, help="Monte Carlo samples of the inputs family.")
    ] = None,
    jobs: Annotated[int, typer.Option("--jobs", "-j", min=1, help="Runs at a time (builds are sequential).")] = 1,
    json_output: JsonOpt = False,
):
    """Assess the numerical error and uncertainty of a case's quantities from ensembles of its variants."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _ns(
        which="assess",
        assess_name=name,
        assess_mode=mode,
        assess_families=_csv(families),
        assess_samples=samples,
        assess_jobs=jobs,
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=None,
        lmodes=False,
        colors=False,
        log=False,
        quiet=False,
        verbose=False,
        json_output=json_output,
    )
