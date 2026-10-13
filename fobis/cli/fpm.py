"""fpm.py — FoBiS.py ``fpm`` sub-app: import an fpm.toml as a fobos, export a fobos as an fpm.toml."""

from __future__ import annotations

from typing import Annotated

import typer

from ._app import app
from ._options import FciOpt, FobosOpt, JsonOpt, ModeOpt
from .lint import lint_namespace

fpm_app = typer.Typer(
    name="fpm",
    help="Interoperate with the Fortran Package Manager: fpm.toml to fobos and back.",
    no_args_is_help=True,
)
app.add_typer(fpm_app)

_ForceOpt = Annotated[bool, typer.Option("--force", help="Overwrite the output file when it exists.")]
_PrintOpt = Annotated[bool, typer.Option("--print", help="Print the translation; write nothing.")]


@fpm_app.command("import")
def cmd_fpm_import(
    ctx: typer.Context,
    manifest: Annotated[str, typer.Option("--fpm", help="The fpm manifest to read.")] = "fpm.toml",
    output: Annotated[str, typer.Option("--output", "-o", help="The fobos to write.")] = "fobos",
    compiler: Annotated[str, typer.Option("--compiler", help="FoBiS compiler of the generated modes.")] = "gnu",
    force: _ForceOpt = False,
    print_only: _PrintOpt = False,
    json_output: JsonOpt = False,
):
    """Write a fobos for an fpm package: sources, debug/release modes (FoBiS build profiles), a library mode when a
    module is named after the package, tests, git dependencies, macros, libraries; notes for the rest."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = lint_namespace(
        which="fpm",
        fpm_action="import",
        fpm_manifest=manifest,
        fpm_output=output,
        fpm_compiler=compiler,
        fpm_force=force,
        fpm_print=print_only,
        fobos="/nonexistent/fobos",  # the fobos is written, not read
        fobos_case_insensitive=False,
        mode=None,
        src=["./"],
        varset="",
        json_output=json_output,
    )


@fpm_app.command("export")
def cmd_fpm_export(
    ctx: typer.Context,
    output: Annotated[str, typer.Option("--output", "-o", help="The fpm manifest to write.")] = "fpm.toml",
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    force: _ForceOpt = False,
    print_only: _PrintOpt = False,
    json_output: JsonOpt = False,
):
    """Write an fpm.toml for the project: metadata, the library directory (where the modules are), executables and
    tests (where the programs are), git dependencies, MPI/OpenMP metapackages, macros; notes for the rest."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = lint_namespace(
        which="fpm",
        fpm_action="export",
        fpm_output=output,
        fpm_force=force,
        fpm_print=print_only,
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        src=["./"],
        varset="",
        json_output=json_output,
    )
