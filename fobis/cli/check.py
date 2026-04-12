"""check.py — FoBiS.py ``check`` subcommand.

Implements issue #170: validate the dependency graph without building.
"""

from __future__ import annotations

from typing import Annotated

import typer

from ._app import _ns, app
from ._constants import __extensions_inc__, __extensions_parsed__
from ._options import FciOpt, FobosOpt, ModeOpt, SrcOpt


@app.command("check")
def cmd_check(
    ctx: typer.Context,
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    src: SrcOpt = None,
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Treat warnings as errors; exit 1 on any warning"),
    ] = False,
):
    """Validate the dependency graph without building."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _ns(
        which="check",
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        lmodes=False,
        strict=strict,
        src=src or ["./"],
        build_dir="./",
        obj_dir="./obj/",
        mod_dir="./mod/",
        lib_dir=[],
        include=[],
        exclude_dirs=[],
        disable_recursive_search=False,
        target=None,
        output=None,
        exclude=[],
        libs=[],
        vlibs=[],
        ext_libs=[],
        ext_vlibs=[],
        dependon=[],
        inc=list(__extensions_inc__),
        extensions=list(__extensions_parsed__),
        build_all=False,
        compiler="gnu",
        fc=None,
        cflags=None,
        lflags=None,
        modsw=None,
        mpi=False,
        openmp=False,
        openmp_offload=False,
        coarray=False,
        coverage=False,
        profile=False,
        build_profile="",
        features="",
        no_default_features=False,
        pre_build=[],
        post_build=[],
        no_auto_discover=False,
        no_cache=False,
        cache_dir=None,
        examples=False,
        target_filter=[],
        mklib=None,
        ar="ar",
        arflags="-rcs",
        ranlib="ranlib",
        cflags_heritage=False,
        track_build=False,
        preprocessor=None,
        preproc=None,
        preprocessor_args="",
        preprocessor_no_o=False,
        preprocessor_dir=None,
        preprocessor_ext=[],
        force_compile=False,
        colors=False,
        log=False,
        graph=False,
        quiet=False,
        verbose=False,
        jobs=1,
        makefile=None,
        json_output=False,
        active_features=[],
    )
