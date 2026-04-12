"""introspect.py — FoBiS.py ``introspect`` subcommand.

Implements issue #178: machine-readable JSON project metadata for IDE and
tooling integration.
"""

from __future__ import annotations

import json
import os
from typing import Annotated

import typer

from ._app import _ns, app
from ._options import FobosOpt, FciOpt, ModeOpt
from ._constants import __extensions_inc__, __extensions_parsed__


@app.command("introspect")
def cmd_introspect(
    ctx: typer.Context,
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    sources: Annotated[bool, typer.Option("--sources", help="Show source files")] = False,
    compiler_info: Annotated[bool, typer.Option("--compiler", help="Show compiler info")] = False,
    dependencies: Annotated[bool, typer.Option("--dependencies", help="Show declared dependencies")] = False,
    targets: Annotated[bool, typer.Option("--targets", help="Show build targets")] = False,
    include_dirs: Annotated[bool, typer.Option("--include-dirs", help="Show include directories")] = False,
    buildoptions: Annotated[bool, typer.Option("--buildoptions", help="Show all fobos mode options")] = False,
    projectinfo: Annotated[bool, typer.Option("--projectinfo", help="Show [project] section metadata")] = False,
    all_info: Annotated[bool, typer.Option("--all", help="Show all introspection data")] = False,
    write: Annotated[
        bool,
        typer.Option("--write", help="Write individual intro-*.json files into .fobis-info/"),
    ] = False,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: json (default) or toml"),
    ] = "json",
):
    """Emit machine-readable JSON project metadata."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _ns(
        which="introspect",
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        lmodes=False,
        introspect_sources=sources or all_info,
        introspect_compiler=compiler_info or all_info,
        introspect_dependencies=dependencies or all_info,
        introspect_targets=targets or all_info,
        introspect_include_dirs=include_dirs or all_info,
        introspect_buildoptions=buildoptions or all_info,
        introspect_projectinfo=projectinfo or all_info,
        introspect_all=all_info,
        introspect_write=write,
        introspect_format=output_format,
        # Minimal build-like attrs needed by FoBiSConfig
        src=["./"],
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
        no_auto_discover=True,  # no auto-discovery for introspect
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
