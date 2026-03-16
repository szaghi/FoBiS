"""
cli_parser.py, FoBiS.py CLI definition built with Typer.
"""

# Copyright (C) 2015  Stefano Zaghi
#
# This file is part of FoBiS.py.
#
# FoBiS.py is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# FoBiS.py is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with FoBiS.py. If not, see <http://www.gnu.org/licenses/>.
import argparse
import re
from typing import List, Optional

import typer
from typing_extensions import Annotated

# ---------------------------------------------------------------------------
# Module-level constants (imported by other modules — do not rename)
# ---------------------------------------------------------------------------
__extensions_inc__ = [".inc", ".INC", ".h", ".H"]
__extensions_old__ = [".f", ".F", ".for", ".FOR", ".fpp", ".FPP", ".fortran", ".f77", ".F77"]
__extensions_modern__ = [".f90", ".F90", ".f95", ".F95", ".f03", ".F03", ".f08", ".F08", ".f2k", ".F2K"]
__extensions_parsed__ = __extensions_inc__ + __extensions_old__ + __extensions_modern__
__compiler_supported__ = (
    "gnu",
    "intel",
    "intel_nextgen",
    "g95",
    "opencoarrays-gnu",
    "pgi",
    "ibm",
    "nag",
    "nvfortran",
    "amd",
    "custom",
)

# ---------------------------------------------------------------------------
# Argument normaliser — preserves backward compat with argparse-style options
# ---------------------------------------------------------------------------
_MULTI_CHAR_OPT = re.compile(r"^-[A-Za-z][A-Za-z0-9_-]+$")


def _normalize_args(args):
    """
    Normalise FoBiS legacy single-dash long options for Click/Typer.

    Rules applied to each token:
    - Single-dash multi-char option (-compiler, -mode, -get_output_name)
      → double-dash with underscores turned to hyphens (--compiler, --mode, --get-output-name)
    - Double-dash option with underscores (--build_dir, --cflags_heritage)
      → double-dash with hyphens (--build-dir, --cflags-heritage)
    - Single-char short options (-f, -m, -q), values, and negative numbers
      are left unchanged.
    """
    result = []
    for arg in args:
        if _MULTI_CHAR_OPT.match(arg):
            # -compiler → --compiler ; -get_output_name → --get-output-name
            result.append("--" + arg[1:].replace("_", "-"))
        elif arg.startswith("--") and len(arg) > 2:
            # --build_dir → --build-dir  (handle optional = form too)
            if "=" in arg:
                opt, val = arg[2:].split("=", 1)
                result.append("--" + opt.replace("_", "-") + "=" + val)
            else:
                result.append("--" + arg[2:].replace("_", "-"))
        else:
            result.append(arg)
    return result


# ---------------------------------------------------------------------------
# Typer application
# ---------------------------------------------------------------------------
app = typer.Typer(
    name="FoBiS.py",
    help="a Fortran Building System for poor men",
    no_args_is_help=True,
    add_completion=True,
    rich_markup_mode=None,
)


def _version_callback(value: bool):
    if value:
        # lazy import avoids circular dependency
        from .FoBiSConfig import __appname__, __version__

        typer.echo(f"{__appname__} {__version__}")
        raise typer.Exit()


@app.callback()
def _app_callback(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-v",
            help="Show version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
):
    ctx.ensure_object(dict)


# ---------------------------------------------------------------------------
# Autocompletion callbacks
# ---------------------------------------------------------------------------


def _complete_compiler(incomplete: str):
    return [c for c in __compiler_supported__ if c.startswith(incomplete.lower())]


def _complete_mklib(incomplete: str):
    return [m for m in ("static", "shared") if m.startswith(incomplete)]


def _complete_extensions(incomplete: str):
    return [e for e in __extensions_parsed__ if e.startswith(incomplete)]


def _complete_doctests_preprocessor(incomplete: str):
    return [p for p in ("cpp", "fpp") if p.startswith(incomplete)]


def _complete_fobos_mode(ctx: typer.Context, incomplete: str):
    import configparser
    import os

    fobos_path = ctx.params.get("fobos") or "fobos"
    if not os.path.exists(fobos_path):
        return []
    cp = configparser.RawConfigParser()
    cp.read(fobos_path)
    if cp.has_option("modes", "modes"):
        modes = [m.strip() for m in cp.get("modes", "modes").split()]
        return [m for m in modes if m.startswith(incomplete)]
    return [
        s for s in cp.sections() if s.startswith(incomplete) and s not in ("modes", "rules", "dependencies", "project")
    ]


# ---------------------------------------------------------------------------
# Namespace factory
# ---------------------------------------------------------------------------


def _ns(**kwargs) -> argparse.Namespace:
    """Build an argparse.Namespace — preserves the duck-type expected by all downstream code."""
    return argparse.Namespace(**kwargs)


# ---------------------------------------------------------------------------
# build command
# ---------------------------------------------------------------------------


@app.command("build")
def cmd_build(
    ctx: typer.Context,
    # fobos group
    fobos: Annotated[
        Optional[str], typer.Option("--fobos", "-f", help='Specify a "fobos" file named differently from "fobos"')
    ] = None,
    fobos_case_insensitive: Annotated[
        bool, typer.Option("--fci", help="Assume fobos inputs as case insensitive")
    ] = False,
    mode: Annotated[
        Optional[str],
        typer.Option("--mode", help="Select a mode defined into a fobos file", autocompletion=_complete_fobos_mode),
    ] = None,
    lmodes: Annotated[bool, typer.Option("--lmodes", help="List the modes defined into a fobos file")] = False,
    print_fobos_template: Annotated[
        bool, typer.Option("--print-fobos-template", help="Print a comprehensive fobos template")
    ] = False,
    # compiler group
    compiler: Annotated[
        str,
        typer.Option(
            "--compiler", help="Compiler used (case insensitive, default gnu)", autocompletion=_complete_compiler
        ),
    ] = "gnu",
    fc: Annotated[
        Optional[str], typer.Option("--fc", help="Fortran compiler statement (for --compiler custom)")
    ] = None,
    cflags: Annotated[Optional[str], typer.Option("--cflags", help="Compile flags")] = None,
    lflags: Annotated[Optional[str], typer.Option("--lflags", help="Link flags")] = None,
    modsw: Annotated[
        Optional[str], typer.Option("--modsw", help="Module search path switch (for --compiler custom)")
    ] = None,
    mpi: Annotated[bool, typer.Option("--mpi", help="Use MPI enabled version of compiler")] = False,
    openmp: Annotated[bool, typer.Option("--openmp", help="Use OpenMP pragmas")] = False,
    openmp_offload: Annotated[bool, typer.Option("--openmp-offload", help="Use OpenMP Offload pragmas")] = False,
    coarray: Annotated[bool, typer.Option("--coarray", help="Use coarrays")] = False,
    coverage: Annotated[bool, typer.Option("--coverage", help="Instrument for coverage analysis")] = False,
    profile: Annotated[bool, typer.Option("--profile", help="Instrument for profiling analysis")] = False,
    mklib: Annotated[
        Optional[str],
        typer.Option(
            "--mklib", help="Build library instead of program (static|shared)", autocompletion=_complete_mklib
        ),
    ] = None,
    ar: Annotated[str, typer.Option("--ar", help="Archiver executable for static libraries [default: ar]")] = "ar",
    arflags: Annotated[
        str, typer.Option("--arflags", help="Archiver flags for static libraries [default: -rcs]")
    ] = "-rcs",
    ranlib: Annotated[
        str, typer.Option("--ranlib", help="Ranlib executable; empty string to skip [default: ranlib]")
    ] = "ranlib",
    cflags_heritage: Annotated[
        bool,
        typer.Option(
            "--cflags-heritage", "--ch", help="Store cflags for heritage checking; re-compile all if they change"
        ),
    ] = False,
    track_build: Annotated[
        bool, typer.Option("--track-build", "--tb", help="Store build info for the install command")
    ] = False,
    # directories group
    src: Annotated[
        Optional[List[str]], typer.Option("--src", "-s", help="Root-directory of source files [default: ./]")
    ] = None,
    build_dir: Annotated[
        str, typer.Option("--build-dir", "--dbld", help="Directory containing built objects [default: ./]")
    ] = "./",
    obj_dir: Annotated[
        str, typer.Option("--obj-dir", "--dobj", help="Directory containing compiled objects [default: ./obj/]")
    ] = "./obj/",
    mod_dir: Annotated[
        str, typer.Option("--mod-dir", "--dmod", help="Directory containing .mod files [default: ./mod/]")
    ] = "./mod/",
    lib_dir: Annotated[
        Optional[List[str]], typer.Option("--lib-dir", "--dlib", help="Directories searched for libraries")
    ] = None,
    include: Annotated[
        Optional[List[str]], typer.Option("--include", "-i", help="Directories for searching included files")
    ] = None,
    exclude_dirs: Annotated[
        Optional[List[str]],
        typer.Option("--exclude-dirs", "--ed", help="Exclude directories from the building process"),
    ] = None,
    disable_recursive_search: Annotated[
        bool, typer.Option("--disable-recursive-search", "--drs", help="Disable recursive search inside directories")
    ] = False,
    # files group
    target: Annotated[
        Optional[str], typer.Option("--target", "-t", help="Specify a target file [default: all programs found]")
    ] = None,
    output: Annotated[
        Optional[str], typer.Option("--output", "-o", help="Output file name (used with --target)")
    ] = None,
    exclude: Annotated[
        Optional[List[str]], typer.Option("--exclude", "-e", help="Exclude files from the building process")
    ] = None,
    libs: Annotated[Optional[List[str]], typer.Option("--libs", help="External libraries with full paths")] = None,
    vlibs: Annotated[
        Optional[List[str]], typer.Option("--vlibs", help="Volatile external libraries with full paths")
    ] = None,
    ext_libs: Annotated[
        Optional[List[str]], typer.Option("--ext-libs", help="External libraries in compiler path")
    ] = None,
    ext_vlibs: Annotated[
        Optional[List[str]], typer.Option("--ext-vlibs", help="Volatile external libraries in compiler path")
    ] = None,
    dependon: Annotated[
        Optional[List[str]],
        typer.Option("--dependon", help="Interdependent external fobos files for interdependent building"),
    ] = None,
    inc: Annotated[
        Optional[List[str]],
        typer.Option("--inc", help="Extensions for include files", autocompletion=_complete_extensions),
    ] = None,
    extensions: Annotated[
        Optional[List[str]],
        typer.Option("--extensions", help="Extensions of parsed files", autocompletion=_complete_extensions),
    ] = None,
    build_all: Annotated[bool, typer.Option("--build-all", help="Build all sources parsed")] = False,
    # preprocessor group
    preprocessor: Annotated[
        Optional[str],
        typer.Option("--preprocessor", help="Preprocessor name for pre-processing sources (e.g. PreForM.py)"),
    ] = None,
    preproc: Annotated[
        Optional[str], typer.Option("--preproc", help="Preprocessor flags for the main compiler")
    ] = None,
    preprocessor_args: Annotated[
        str, typer.Option("--preprocessor-args", "--app", help="Preprocessor-specific flags")
    ] = "",
    preprocessor_no_o: Annotated[
        bool,
        typer.Option("--preprocessor-no-o", "--npp", help="Do not add -o in front of output in preprocessor command"),
    ] = False,
    preprocessor_dir: Annotated[
        Optional[str], typer.Option("--preprocessor-dir", "--dpp", help="Directory for preprocessed files")
    ] = None,
    preprocessor_ext: Annotated[
        Optional[List[str]], typer.Option("--preprocessor-ext", "--epp", help="File extensions to preprocess")
    ] = None,
    # fancy group
    force_compile: Annotated[bool, typer.Option("--force-compile", help="Force to (re-)compile all")] = False,
    colors: Annotated[bool, typer.Option("--colors", help="Activate colors in shell prints")] = False,
    log: Annotated[bool, typer.Option("--log", "-l", help="Activate log file creation")] = False,
    graph: Annotated[bool, typer.Option("--graph", help="Generate a dependencies graph via graphviz")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Less verbose output")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", help="Extremely verbose output for debugging")] = False,
    jobs: Annotated[int, typer.Option("--jobs", "-j", help="Number of concurrent compilation jobs [default: 1]")] = 1,
    makefile: Annotated[
        Optional[str], typer.Option("--makefile", "-m", help="Generate a GNU Makefile for building the project")
    ] = None,
):
    """Build all programs found or specific target(s)."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _ns(
        which="build",
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        lmodes=lmodes,
        print_fobos_template=print_fobos_template,
        compiler=compiler.lower(),
        fc=fc,
        cflags=cflags,
        lflags=lflags,
        modsw=modsw,
        mpi=mpi,
        openmp=openmp,
        openmp_offload=openmp_offload,
        coarray=coarray,
        coverage=coverage,
        profile=profile,
        mklib=mklib,
        ar=ar,
        arflags=arflags,
        ranlib=ranlib,
        cflags_heritage=cflags_heritage,
        track_build=track_build,
        src=src or ["./"],
        build_dir=build_dir,
        obj_dir=obj_dir,
        mod_dir=mod_dir,
        lib_dir=lib_dir or [],
        include=include or [],
        exclude_dirs=exclude_dirs or [],
        disable_recursive_search=disable_recursive_search,
        target=target,
        output=output,
        exclude=exclude or [],
        libs=libs or [],
        vlibs=vlibs or [],
        ext_libs=ext_libs or [],
        ext_vlibs=ext_vlibs or [],
        dependon=dependon or [],
        inc=inc or list(__extensions_inc__),
        extensions=extensions or list(__extensions_parsed__),
        build_all=build_all,
        preprocessor=preprocessor,
        preproc=preproc,
        preprocessor_args=preprocessor_args,
        preprocessor_no_o=preprocessor_no_o,
        preprocessor_dir=preprocessor_dir,
        preprocessor_ext=preprocessor_ext or [],
        force_compile=force_compile,
        colors=colors,
        log=log,
        graph=graph,
        quiet=quiet,
        verbose=verbose,
        jobs=jobs,
        makefile=makefile,
    )


# ---------------------------------------------------------------------------
# clean command
# ---------------------------------------------------------------------------


@app.command("clean")
def cmd_clean(
    ctx: typer.Context,
    # fobos group
    fobos: Annotated[
        Optional[str], typer.Option("--fobos", "-f", help='Specify a "fobos" file named differently from "fobos"')
    ] = None,
    fobos_case_insensitive: Annotated[
        bool, typer.Option("--fci", help="Assume fobos inputs as case insensitive")
    ] = False,
    mode: Annotated[
        Optional[str],
        typer.Option("--mode", help="Select a mode defined into a fobos file", autocompletion=_complete_fobos_mode),
    ] = None,
    lmodes: Annotated[bool, typer.Option("--lmodes", help="List the modes defined into a fobos file")] = False,
    print_fobos_template: Annotated[
        bool, typer.Option("--print-fobos-template", help="Print a comprehensive fobos template")
    ] = False,
    # clean-specific (were part of compiler group in argparse)
    only_obj: Annotated[
        bool, typer.Option("--only-obj", help="Clean only compiled objects and not built targets")
    ] = False,
    only_target: Annotated[
        bool, typer.Option("--only-target", help="Clean only built targets and not compiled objects")
    ] = False,
    # compiler group
    compiler: Annotated[
        str,
        typer.Option(
            "--compiler", help="Compiler used (case insensitive, default gnu)", autocompletion=_complete_compiler
        ),
    ] = "gnu",
    fc: Annotated[
        Optional[str], typer.Option("--fc", help="Fortran compiler statement (for --compiler custom)")
    ] = None,
    cflags: Annotated[Optional[str], typer.Option("--cflags", help="Compile flags")] = None,
    lflags: Annotated[Optional[str], typer.Option("--lflags", help="Link flags")] = None,
    modsw: Annotated[
        Optional[str], typer.Option("--modsw", help="Module search path switch (for --compiler custom)")
    ] = None,
    mpi: Annotated[bool, typer.Option("--mpi", help="Use MPI enabled version of compiler")] = False,
    openmp: Annotated[bool, typer.Option("--openmp", help="Use OpenMP pragmas")] = False,
    openmp_offload: Annotated[bool, typer.Option("--openmp-offload", help="Use OpenMP Offload pragmas")] = False,
    coarray: Annotated[bool, typer.Option("--coarray", help="Use coarrays")] = False,
    coverage: Annotated[bool, typer.Option("--coverage", help="Instrument for coverage analysis")] = False,
    profile: Annotated[bool, typer.Option("--profile", help="Instrument for profiling analysis")] = False,
    mklib: Annotated[
        Optional[str],
        typer.Option(
            "--mklib", help="Build library instead of program (static|shared)", autocompletion=_complete_mklib
        ),
    ] = None,
    ar: Annotated[str, typer.Option("--ar", help="Archiver executable for static libraries [default: ar]")] = "ar",
    arflags: Annotated[
        str, typer.Option("--arflags", help="Archiver flags for static libraries [default: -rcs]")
    ] = "-rcs",
    ranlib: Annotated[
        str, typer.Option("--ranlib", help="Ranlib executable; empty string to skip [default: ranlib]")
    ] = "ranlib",
    cflags_heritage: Annotated[
        bool, typer.Option("--cflags-heritage", "--ch", help="Store cflags for heritage checking")
    ] = False,
    track_build: Annotated[
        bool, typer.Option("--track-build", "--tb", help="Store build info for the install command")
    ] = False,
    # directories group
    src: Annotated[
        Optional[List[str]], typer.Option("--src", "-s", help="Root-directory of source files [default: ./]")
    ] = None,
    build_dir: Annotated[
        str, typer.Option("--build-dir", "--dbld", help="Directory containing built objects [default: ./]")
    ] = "./",
    obj_dir: Annotated[
        str, typer.Option("--obj-dir", "--dobj", help="Directory containing compiled objects [default: ./obj/]")
    ] = "./obj/",
    mod_dir: Annotated[
        str, typer.Option("--mod-dir", "--dmod", help="Directory containing .mod files [default: ./mod/]")
    ] = "./mod/",
    lib_dir: Annotated[
        Optional[List[str]], typer.Option("--lib-dir", "--dlib", help="Directories searched for libraries")
    ] = None,
    include: Annotated[
        Optional[List[str]], typer.Option("--include", "-i", help="Directories for searching included files")
    ] = None,
    exclude_dirs: Annotated[
        Optional[List[str]],
        typer.Option("--exclude-dirs", "--ed", help="Exclude directories from the building process"),
    ] = None,
    disable_recursive_search: Annotated[
        bool, typer.Option("--disable-recursive-search", "--drs", help="Disable recursive search inside directories")
    ] = False,
    # files group
    target: Annotated[Optional[str], typer.Option("--target", "-t", help="Specify a target file")] = None,
    output: Annotated[
        Optional[str], typer.Option("--output", "-o", help="Output file name (used with --target)")
    ] = None,
    exclude: Annotated[
        Optional[List[str]], typer.Option("--exclude", "-e", help="Exclude files from the building process")
    ] = None,
    libs: Annotated[Optional[List[str]], typer.Option("--libs", help="External libraries with full paths")] = None,
    vlibs: Annotated[
        Optional[List[str]], typer.Option("--vlibs", help="Volatile external libraries with full paths")
    ] = None,
    ext_libs: Annotated[
        Optional[List[str]], typer.Option("--ext-libs", help="External libraries in compiler path")
    ] = None,
    ext_vlibs: Annotated[
        Optional[List[str]], typer.Option("--ext-vlibs", help="Volatile external libraries in compiler path")
    ] = None,
    dependon: Annotated[
        Optional[List[str]], typer.Option("--dependon", help="Interdependent external fobos files")
    ] = None,
    inc: Annotated[Optional[List[str]], typer.Option("--inc", help="Extensions for include files")] = None,
    extensions: Annotated[Optional[List[str]], typer.Option("--extensions", help="Extensions of parsed files")] = None,
    build_all: Annotated[bool, typer.Option("--build-all", help="Build all sources parsed")] = False,
    # fancy group
    force_compile: Annotated[bool, typer.Option("--force-compile", help="Force to (re-)compile all")] = False,
    colors: Annotated[bool, typer.Option("--colors", help="Activate colors in shell prints")] = False,
    log: Annotated[bool, typer.Option("--log", "-l", help="Activate log file creation")] = False,
    graph: Annotated[bool, typer.Option("--graph", help="Generate a dependencies graph via graphviz")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Less verbose output")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", help="Extremely verbose output for debugging")] = False,
    jobs: Annotated[int, typer.Option("--jobs", "-j", help="Number of concurrent compilation jobs [default: 1]")] = 1,
    makefile: Annotated[
        Optional[str], typer.Option("--makefile", "-m", help="Generate a GNU Makefile for building the project")
    ] = None,
):
    """Clean project: remove all OBJs and MODs files. Use carefully."""
    ctx.ensure_object(dict)
    if only_obj and only_target:
        typer.echo("Error: --only-obj and --only-target are mutually exclusive.", err=True)
        raise typer.Exit(1)
    ctx.obj["cliargs"] = _ns(
        which="clean",
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        lmodes=lmodes,
        print_fobos_template=print_fobos_template,
        only_obj=only_obj,
        only_target=only_target,
        compiler=compiler.lower(),
        fc=fc,
        cflags=cflags,
        lflags=lflags,
        modsw=modsw,
        mpi=mpi,
        openmp=openmp,
        openmp_offload=openmp_offload,
        coarray=coarray,
        coverage=coverage,
        profile=profile,
        mklib=mklib,
        ar=ar,
        arflags=arflags,
        ranlib=ranlib,
        cflags_heritage=cflags_heritage,
        track_build=track_build,
        src=src or ["./"],
        build_dir=build_dir,
        obj_dir=obj_dir,
        mod_dir=mod_dir,
        lib_dir=lib_dir or [],
        include=include or [],
        exclude_dirs=exclude_dirs or [],
        disable_recursive_search=disable_recursive_search,
        target=target,
        output=output,
        exclude=exclude or [],
        libs=libs or [],
        vlibs=vlibs or [],
        ext_libs=ext_libs or [],
        ext_vlibs=ext_vlibs or [],
        dependon=dependon or [],
        inc=inc or list(__extensions_inc__),
        extensions=extensions or list(__extensions_parsed__),
        build_all=build_all,
        force_compile=force_compile,
        colors=colors,
        log=log,
        graph=graph,
        quiet=quiet,
        verbose=verbose,
        jobs=jobs,
        makefile=makefile,
    )


# ---------------------------------------------------------------------------
# rule command
# ---------------------------------------------------------------------------


@app.command("rule")
def cmd_rule(
    ctx: typer.Context,
    # fobos group
    fobos: Annotated[
        Optional[str], typer.Option("--fobos", "-f", help='Specify a "fobos" file named differently from "fobos"')
    ] = None,
    fobos_case_insensitive: Annotated[
        bool, typer.Option("--fci", help="Assume fobos inputs as case insensitive")
    ] = False,
    mode: Annotated[
        Optional[str],
        typer.Option("--mode", help="Select a mode defined into a fobos file", autocompletion=_complete_fobos_mode),
    ] = None,
    lmodes: Annotated[bool, typer.Option("--lmodes", help="List the modes defined into a fobos file")] = False,
    print_fobos_template: Annotated[
        bool, typer.Option("--print-fobos-template", help="Print a comprehensive fobos template")
    ] = False,
    # compiler group
    compiler: Annotated[
        str,
        typer.Option(
            "--compiler", help="Compiler used (case insensitive, default gnu)", autocompletion=_complete_compiler
        ),
    ] = "gnu",
    fc: Annotated[
        Optional[str], typer.Option("--fc", help="Fortran compiler statement (for --compiler custom)")
    ] = None,
    cflags: Annotated[Optional[str], typer.Option("--cflags", help="Compile flags")] = None,
    lflags: Annotated[Optional[str], typer.Option("--lflags", help="Link flags")] = None,
    modsw: Annotated[
        Optional[str], typer.Option("--modsw", help="Module search path switch (for --compiler custom)")
    ] = None,
    mpi: Annotated[bool, typer.Option("--mpi", help="Use MPI enabled version of compiler")] = False,
    openmp: Annotated[bool, typer.Option("--openmp", help="Use OpenMP pragmas")] = False,
    openmp_offload: Annotated[bool, typer.Option("--openmp-offload", help="Use OpenMP Offload pragmas")] = False,
    coarray: Annotated[bool, typer.Option("--coarray", help="Use coarrays")] = False,
    coverage: Annotated[bool, typer.Option("--coverage", help="Instrument for coverage analysis")] = False,
    profile: Annotated[bool, typer.Option("--profile", help="Instrument for profiling analysis")] = False,
    mklib: Annotated[
        Optional[str],
        typer.Option(
            "--mklib", help="Build library instead of program (static|shared)", autocompletion=_complete_mklib
        ),
    ] = None,
    ar: Annotated[str, typer.Option("--ar", help="Archiver executable for static libraries [default: ar]")] = "ar",
    arflags: Annotated[
        str, typer.Option("--arflags", help="Archiver flags for static libraries [default: -rcs]")
    ] = "-rcs",
    ranlib: Annotated[
        str, typer.Option("--ranlib", help="Ranlib executable; empty string to skip [default: ranlib]")
    ] = "ranlib",
    cflags_heritage: Annotated[
        bool,
        typer.Option(
            "--cflags-heritage", "--ch", help="Store cflags for heritage checking; re-compile all if they change"
        ),
    ] = False,
    track_build: Annotated[
        bool, typer.Option("--track-build", "--tb", help="Store build info for the install command")
    ] = False,
    # directories group
    src: Annotated[
        Optional[List[str]], typer.Option("--src", "-s", help="Root-directory of source files [default: ./]")
    ] = None,
    build_dir: Annotated[
        str, typer.Option("--build-dir", "--dbld", help="Directory containing built objects [default: ./]")
    ] = "./",
    obj_dir: Annotated[
        str, typer.Option("--obj-dir", "--dobj", help="Directory containing compiled objects [default: ./obj/]")
    ] = "./obj/",
    mod_dir: Annotated[
        str, typer.Option("--mod-dir", "--dmod", help="Directory containing .mod files [default: ./mod/]")
    ] = "./mod/",
    lib_dir: Annotated[
        Optional[List[str]], typer.Option("--lib-dir", "--dlib", help="Directories searched for libraries")
    ] = None,
    include: Annotated[
        Optional[List[str]], typer.Option("--include", "-i", help="Directories for searching included files")
    ] = None,
    exclude_dirs: Annotated[
        Optional[List[str]],
        typer.Option("--exclude-dirs", "--ed", help="Exclude directories from the building process"),
    ] = None,
    disable_recursive_search: Annotated[
        bool, typer.Option("--disable-recursive-search", "--drs", help="Disable recursive search inside directories")
    ] = False,
    # files group
    target: Annotated[Optional[str], typer.Option("--target", "-t", help="Specify a target file")] = None,
    output: Annotated[
        Optional[str], typer.Option("--output", "-o", help="Output file name (used with --target)")
    ] = None,
    exclude: Annotated[
        Optional[List[str]], typer.Option("--exclude", "-e", help="Exclude files from the building process")
    ] = None,
    libs: Annotated[Optional[List[str]], typer.Option("--libs", help="External libraries with full paths")] = None,
    vlibs: Annotated[
        Optional[List[str]], typer.Option("--vlibs", help="Volatile external libraries with full paths")
    ] = None,
    ext_libs: Annotated[
        Optional[List[str]], typer.Option("--ext-libs", help="External libraries in compiler path")
    ] = None,
    ext_vlibs: Annotated[
        Optional[List[str]], typer.Option("--ext-vlibs", help="Volatile external libraries in compiler path")
    ] = None,
    dependon: Annotated[
        Optional[List[str]],
        typer.Option("--dependon", help="Interdependent external fobos files for interdependent building"),
    ] = None,
    inc: Annotated[
        Optional[List[str]],
        typer.Option("--inc", help="Extensions for include files", autocompletion=_complete_extensions),
    ] = None,
    extensions: Annotated[
        Optional[List[str]],
        typer.Option("--extensions", help="Extensions of parsed files", autocompletion=_complete_extensions),
    ] = None,
    build_all: Annotated[bool, typer.Option("--build-all", help="Build all sources parsed")] = False,
    # preprocessor group
    preprocessor: Annotated[
        Optional[str], typer.Option("--preprocessor", help="Preprocessor name (e.g. PreForM.py)")
    ] = None,
    preproc: Annotated[
        Optional[str], typer.Option("--preproc", help="Preprocessor flags for the main compiler")
    ] = None,
    preprocessor_args: Annotated[
        str, typer.Option("--preprocessor-args", "--app", help="Preprocessor-specific flags")
    ] = "",
    preprocessor_no_o: Annotated[
        bool,
        typer.Option("--preprocessor-no-o", "--npp", help="Do not add -o in front of output in preprocessor command"),
    ] = False,
    preprocessor_dir: Annotated[
        Optional[str], typer.Option("--preprocessor-dir", "--dpp", help="Directory for preprocessed files")
    ] = None,
    preprocessor_ext: Annotated[
        Optional[List[str]], typer.Option("--preprocessor-ext", "--epp", help="File extensions to preprocess")
    ] = None,
    # rules group
    execute: Annotated[
        Optional[str], typer.Option("--execute", "--ex", help="Specify a rule (defined in fobos) to execute")
    ] = None,
    list_rules: Annotated[bool, typer.Option("--list", "--ls", help="List the rules defined in a fobos file")] = False,
    # intrinsic rules group
    get: Annotated[
        Optional[str], typer.Option("--get", help="Get option value defined in fobos (e.g. --get build_dir)")
    ] = None,
    get_output_name: Annotated[
        bool, typer.Option("--get-output-name", help="Get the final output name from fobos options")
    ] = False,
    ford: Annotated[
        Optional[str], typer.Option("--ford", help="Build docs with Ford tool (specify project-file.md)")
    ] = None,
    gcov_analyzer: Annotated[
        Optional[List[str]],
        typer.Option("--gcov-analyzer", help="Analyse .gcov files; args: REPORTS_DIR [SUMMARY_FILE]"),
    ] = None,
    is_ascii_kind_supported: Annotated[
        bool, typer.Option("--is-ascii-kind-supported", help="Check if compiler supports ASCII kind")
    ] = False,
    is_ucs4_kind_supported: Annotated[
        bool, typer.Option("--is-ucs4-kind-supported", help="Check if compiler supports UCS4 kind")
    ] = False,
    is_float128_kind_supported: Annotated[
        bool, typer.Option("--is-float128-kind-supported", help="Check if compiler supports float128 kind")
    ] = False,
    # fancy group
    force_compile: Annotated[bool, typer.Option("--force-compile", help="Force to (re-)compile all")] = False,
    colors: Annotated[bool, typer.Option("--colors", help="Activate colors in shell prints")] = False,
    log: Annotated[bool, typer.Option("--log", "-l", help="Activate log file creation")] = False,
    graph: Annotated[bool, typer.Option("--graph", help="Generate a dependencies graph via graphviz")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Less verbose output")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", help="Extremely verbose output for debugging")] = False,
    jobs: Annotated[int, typer.Option("--jobs", "-j", help="Number of concurrent compilation jobs [default: 1]")] = 1,
    makefile: Annotated[
        Optional[str], typer.Option("--makefile", "-m", help="Generate a GNU Makefile for building the project")
    ] = None,
):
    """Execute special rules or user-defined ones from a fobos file."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _ns(
        which="rule",
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        lmodes=lmodes,
        print_fobos_template=print_fobos_template,
        compiler=compiler.lower(),
        fc=fc,
        cflags=cflags,
        lflags=lflags,
        modsw=modsw,
        mpi=mpi,
        openmp=openmp,
        openmp_offload=openmp_offload,
        coarray=coarray,
        coverage=coverage,
        profile=profile,
        mklib=mklib,
        ar=ar,
        arflags=arflags,
        ranlib=ranlib,
        cflags_heritage=cflags_heritage,
        track_build=track_build,
        src=src or ["./"],
        build_dir=build_dir,
        obj_dir=obj_dir,
        mod_dir=mod_dir,
        lib_dir=lib_dir or [],
        include=include or [],
        exclude_dirs=exclude_dirs or [],
        disable_recursive_search=disable_recursive_search,
        target=target,
        output=output,
        exclude=exclude or [],
        libs=libs or [],
        vlibs=vlibs or [],
        ext_libs=ext_libs or [],
        ext_vlibs=ext_vlibs or [],
        dependon=dependon or [],
        inc=inc or list(__extensions_inc__),
        extensions=extensions or list(__extensions_parsed__),
        build_all=build_all,
        preprocessor=preprocessor,
        preproc=preproc,
        preprocessor_args=preprocessor_args,
        preprocessor_no_o=preprocessor_no_o,
        preprocessor_dir=preprocessor_dir,
        preprocessor_ext=preprocessor_ext or [],
        execute=execute,
        list=list_rules,
        get=get,
        get_output_name=get_output_name,
        ford=ford,
        gcov_analyzer=gcov_analyzer,
        is_ascii_kind_supported=is_ascii_kind_supported,
        is_ucs4_kind_supported=is_ucs4_kind_supported,
        is_float128_kind_supported=is_float128_kind_supported,
        force_compile=force_compile,
        colors=colors,
        log=log,
        graph=graph,
        quiet=quiet,
        verbose=verbose,
        jobs=jobs,
        makefile=makefile,
    )


# ---------------------------------------------------------------------------
# install command
# ---------------------------------------------------------------------------


@app.command("install")
def cmd_install(
    ctx: typer.Context,
    repo: Annotated[
        Optional[str], typer.Argument(help='GitHub repository: "user/repo" shorthand or full HTTPS URL')
    ] = None,
    # fobos group
    fobos: Annotated[
        Optional[str], typer.Option("--fobos", "-f", help='Specify a "fobos" file named differently from "fobos"')
    ] = None,
    fobos_case_insensitive: Annotated[
        bool, typer.Option("--fci", help="Assume fobos inputs as case insensitive")
    ] = False,
    mode: Annotated[
        Optional[str],
        typer.Option("--mode", help="Select a mode defined into a fobos file", autocompletion=_complete_fobos_mode),
    ] = None,
    lmodes: Annotated[bool, typer.Option("--lmodes", help="List the modes defined into a fobos file")] = False,
    print_fobos_template: Annotated[
        bool, typer.Option("--print-fobos-template", help="Print a comprehensive fobos template")
    ] = False,
    # directories group (install variant)
    build_dir: Annotated[
        str, typer.Option("--build-dir", "--dbld", help="Directory containing built objects [default: ./]")
    ] = "./",
    prefix: Annotated[
        str, typer.Option("--prefix", "-p", help="Prefix path where built objects are installed [default: ./]")
    ] = "./",
    bin: Annotated[str, typer.Option("--bin", help="Sub-directory for executables [default: bin/]")] = "bin/",
    lib: Annotated[str, typer.Option("--lib", help="Sub-directory for libraries [default: lib/]")] = "lib/",
    include: Annotated[
        str, typer.Option("--include", help="Sub-directory for include files [default: include/]")
    ] = "include/",
    # GitHub install options
    branch: Annotated[
        Optional[str], typer.Option("--branch", help="Branch to check out when installing from GitHub")
    ] = None,
    tag: Annotated[Optional[str], typer.Option("--tag", help="Tag to check out when installing from GitHub")] = None,
    rev: Annotated[
        Optional[str], typer.Option("--rev", help="Commit revision to check out when installing from GitHub")
    ] = None,
    update: Annotated[
        bool, typer.Option("--update", help="Re-fetch (git pull) before building and installing")
    ] = False,
    no_build: Annotated[bool, typer.Option("--no-build", help="Clone only — skip building and installing")] = False,
    deps_dir: Annotated[
        Optional[str], typer.Option("--deps-dir", help="Directory for cloning GitHub repositories [default: ~/.fobis/]")
    ] = None,
    # fancy group
    force_compile: Annotated[bool, typer.Option("--force-compile", help="Force to (re-)compile all")] = False,
    colors: Annotated[bool, typer.Option("--colors", help="Activate colors in shell prints")] = False,
    log: Annotated[bool, typer.Option("--log", "-l", help="Activate log file creation")] = False,
    graph: Annotated[bool, typer.Option("--graph", help="Generate a dependencies graph via graphviz")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Less verbose output")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", help="Extremely verbose output for debugging")] = False,
    jobs: Annotated[int, typer.Option("--jobs", "-j", help="Number of concurrent compilation jobs [default: 1]")] = 1,
    makefile: Annotated[
        Optional[str], typer.Option("--makefile", "-m", help="Generate a GNU Makefile for building the project")
    ] = None,
):
    """Install previously built files, or clone+build+install a GitHub-hosted FoBiS project."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _ns(
        which="install",
        repo=repo,
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        lmodes=lmodes,
        print_fobos_template=print_fobos_template,
        build_dir=build_dir,
        prefix=prefix,
        bin=bin,
        lib=lib,
        include=include,
        branch=branch,
        tag=tag,
        rev=rev,
        update=update,
        no_build=no_build,
        deps_dir=deps_dir,
        force_compile=force_compile,
        colors=colors,
        log=log,
        graph=graph,
        quiet=quiet,
        verbose=verbose,
        jobs=jobs,
        makefile=makefile,
    )


# ---------------------------------------------------------------------------
# doctests command
# ---------------------------------------------------------------------------


@app.command("doctests")
def cmd_doctests(
    ctx: typer.Context,
    # fobos group
    fobos: Annotated[
        Optional[str], typer.Option("--fobos", "-f", help='Specify a "fobos" file named differently from "fobos"')
    ] = None,
    fobos_case_insensitive: Annotated[
        bool, typer.Option("--fci", help="Assume fobos inputs as case insensitive")
    ] = False,
    mode: Annotated[
        Optional[str],
        typer.Option("--mode", help="Select a mode defined into a fobos file", autocompletion=_complete_fobos_mode),
    ] = None,
    lmodes: Annotated[bool, typer.Option("--lmodes", help="List the modes defined into a fobos file")] = False,
    print_fobos_template: Annotated[
        bool, typer.Option("--print-fobos-template", help="Print a comprehensive fobos template")
    ] = False,
    # compiler group
    compiler: Annotated[
        str,
        typer.Option(
            "--compiler", help="Compiler used (case insensitive, default gnu)", autocompletion=_complete_compiler
        ),
    ] = "gnu",
    fc: Annotated[
        Optional[str], typer.Option("--fc", help="Fortran compiler statement (for --compiler custom)")
    ] = None,
    cflags: Annotated[Optional[str], typer.Option("--cflags", help="Compile flags")] = None,
    lflags: Annotated[Optional[str], typer.Option("--lflags", help="Link flags")] = None,
    modsw: Annotated[
        Optional[str], typer.Option("--modsw", help="Module search path switch (for --compiler custom)")
    ] = None,
    mpi: Annotated[bool, typer.Option("--mpi", help="Use MPI enabled version of compiler")] = False,
    openmp: Annotated[bool, typer.Option("--openmp", help="Use OpenMP pragmas")] = False,
    openmp_offload: Annotated[bool, typer.Option("--openmp-offload", help="Use OpenMP Offload pragmas")] = False,
    coarray: Annotated[bool, typer.Option("--coarray", help="Use coarrays")] = False,
    coverage: Annotated[bool, typer.Option("--coverage", help="Instrument for coverage analysis")] = False,
    profile: Annotated[bool, typer.Option("--profile", help="Instrument for profiling analysis")] = False,
    mklib: Annotated[
        Optional[str],
        typer.Option(
            "--mklib", help="Build library instead of program (static|shared)", autocompletion=_complete_mklib
        ),
    ] = None,
    ar: Annotated[str, typer.Option("--ar", help="Archiver executable for static libraries [default: ar]")] = "ar",
    arflags: Annotated[
        str, typer.Option("--arflags", help="Archiver flags for static libraries [default: -rcs]")
    ] = "-rcs",
    ranlib: Annotated[
        str, typer.Option("--ranlib", help="Ranlib executable; empty string to skip [default: ranlib]")
    ] = "ranlib",
    cflags_heritage: Annotated[
        bool, typer.Option("--cflags-heritage", "--ch", help="Store cflags for heritage checking")
    ] = False,
    track_build: Annotated[
        bool, typer.Option("--track-build", "--tb", help="Store build info for the install command")
    ] = False,
    # directories group
    src: Annotated[
        Optional[List[str]], typer.Option("--src", "-s", help="Root-directory of source files [default: ./]")
    ] = None,
    build_dir: Annotated[
        str, typer.Option("--build-dir", "--dbld", help="Directory containing built objects [default: ./]")
    ] = "./",
    obj_dir: Annotated[
        str, typer.Option("--obj-dir", "--dobj", help="Directory containing compiled objects [default: ./obj/]")
    ] = "./obj/",
    mod_dir: Annotated[
        str, typer.Option("--mod-dir", "--dmod", help="Directory containing .mod files [default: ./mod/]")
    ] = "./mod/",
    lib_dir: Annotated[
        Optional[List[str]], typer.Option("--lib-dir", "--dlib", help="Directories searched for libraries")
    ] = None,
    include: Annotated[
        Optional[List[str]], typer.Option("--include", "-i", help="Directories for searching included files")
    ] = None,
    exclude_dirs: Annotated[
        Optional[List[str]],
        typer.Option("--exclude-dirs", "--ed", help="Exclude directories from the building process"),
    ] = None,
    disable_recursive_search: Annotated[
        bool, typer.Option("--disable-recursive-search", "--drs", help="Disable recursive search inside directories")
    ] = False,
    # files group (doctests variant)
    target: Annotated[Optional[str], typer.Option("--target", "-t", help="Specify a target file")] = None,
    output: Annotated[
        Optional[str], typer.Option("--output", "-o", help="Output file name (used with --target)")
    ] = None,
    exclude: Annotated[
        Optional[List[str]], typer.Option("--exclude", "-e", help="Exclude files from the building process")
    ] = None,
    libs: Annotated[Optional[List[str]], typer.Option("--libs", help="External libraries with full paths")] = None,
    vlibs: Annotated[
        Optional[List[str]], typer.Option("--vlibs", help="Volatile external libraries with full paths")
    ] = None,
    ext_libs: Annotated[
        Optional[List[str]], typer.Option("--ext-libs", help="External libraries in compiler path")
    ] = None,
    ext_vlibs: Annotated[
        Optional[List[str]], typer.Option("--ext-vlibs", help="Volatile external libraries in compiler path")
    ] = None,
    dependon: Annotated[
        Optional[List[str]], typer.Option("--dependon", help="Interdependent external fobos files")
    ] = None,
    inc: Annotated[
        Optional[List[str]],
        typer.Option("--inc", help="Extensions for include files", autocompletion=_complete_extensions),
    ] = None,
    extensions: Annotated[
        Optional[List[str]],
        typer.Option("--extensions", help="Extensions of parsed files", autocompletion=_complete_extensions),
    ] = None,
    build_all: Annotated[bool, typer.Option("--build-all", help="Build all sources parsed")] = False,
    keep_volatile_doctests: Annotated[
        bool, typer.Option("--keep-volatile-doctests", help="Keep the volatile doctests programs")
    ] = False,
    exclude_from_doctests: Annotated[
        Optional[List[str]], typer.Option("--exclude-from-doctests", help="Exclude files from the doctests process")
    ] = None,
    # preprocessor group (doctests variant)
    preprocessor: Annotated[
        Optional[str], typer.Option("--preprocessor", help="Preprocessor name (e.g. PreForM.py)")
    ] = None,
    preproc: Annotated[
        Optional[str], typer.Option("--preproc", help="Preprocessor flags for the main compiler")
    ] = None,
    preprocessor_args: Annotated[
        str, typer.Option("--preprocessor-args", "--app", help="Preprocessor-specific flags")
    ] = "",
    preprocessor_no_o: Annotated[
        bool,
        typer.Option("--preprocessor-no-o", "--npp", help="Do not add -o in front of output in preprocessor command"),
    ] = False,
    preprocessor_dir: Annotated[
        Optional[str], typer.Option("--preprocessor-dir", "--dpp", help="Directory for preprocessed files")
    ] = None,
    preprocessor_ext: Annotated[
        Optional[List[str]], typer.Option("--preprocessor-ext", "--epp", help="File extensions to preprocess")
    ] = None,
    doctests_preprocessor: Annotated[
        str,
        typer.Option(
            "--doctests-preprocessor",
            help="Preprocessor used during doctests parsing (cpp|fpp)",
            autocompletion=_complete_doctests_preprocessor,
        ),
    ] = "cpp",
    # fancy group
    force_compile: Annotated[bool, typer.Option("--force-compile", help="Force to (re-)compile all")] = False,
    colors: Annotated[bool, typer.Option("--colors", help="Activate colors in shell prints")] = False,
    log: Annotated[bool, typer.Option("--log", "-l", help="Activate log file creation")] = False,
    graph: Annotated[bool, typer.Option("--graph", help="Generate a dependencies graph via graphviz")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Less verbose output")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", help="Extremely verbose output for debugging")] = False,
    jobs: Annotated[int, typer.Option("--jobs", "-j", help="Number of concurrent compilation jobs [default: 1]")] = 1,
    makefile: Annotated[
        Optional[str], typer.Option("--makefile", "-m", help="Generate a GNU Makefile for building the project")
    ] = None,
):
    """Test all valid doctests snippets found."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _ns(
        which="doctests",
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        lmodes=lmodes,
        print_fobos_template=print_fobos_template,
        compiler=compiler.lower(),
        fc=fc,
        cflags=cflags,
        lflags=lflags,
        modsw=modsw,
        mpi=mpi,
        openmp=openmp,
        openmp_offload=openmp_offload,
        coarray=coarray,
        coverage=coverage,
        profile=profile,
        mklib=mklib,
        ar=ar,
        arflags=arflags,
        ranlib=ranlib,
        cflags_heritage=cflags_heritage,
        track_build=track_build,
        src=src or ["./"],
        build_dir=build_dir,
        obj_dir=obj_dir,
        mod_dir=mod_dir,
        lib_dir=lib_dir or [],
        include=include or [],
        exclude_dirs=exclude_dirs or [],
        disable_recursive_search=disable_recursive_search,
        target=target,
        output=output,
        exclude=exclude or [],
        libs=libs or [],
        vlibs=vlibs or [],
        ext_libs=ext_libs or [],
        ext_vlibs=ext_vlibs or [],
        dependon=dependon or [],
        inc=inc or list(__extensions_inc__),
        extensions=extensions or list(__extensions_parsed__),
        build_all=build_all,
        keep_volatile_doctests=keep_volatile_doctests,
        exclude_from_doctests=exclude_from_doctests or [],
        preprocessor=preprocessor,
        preproc=preproc,
        preprocessor_args=preprocessor_args,
        preprocessor_no_o=preprocessor_no_o,
        preprocessor_dir=preprocessor_dir,
        preprocessor_ext=preprocessor_ext or [],
        doctests_preprocessor=doctests_preprocessor,
        force_compile=force_compile,
        colors=colors,
        log=log,
        graph=graph,
        quiet=quiet,
        verbose=verbose,
        jobs=jobs,
        makefile=makefile,
    )


# ---------------------------------------------------------------------------
# fetch command
# ---------------------------------------------------------------------------


@app.command("fetch")
def cmd_fetch(
    ctx: typer.Context,
    # fobos group
    fobos: Annotated[
        Optional[str], typer.Option("--fobos", "-f", help='Specify a "fobos" file named differently from "fobos"')
    ] = None,
    fobos_case_insensitive: Annotated[
        bool, typer.Option("--fci", help="Assume fobos inputs as case insensitive")
    ] = False,
    mode: Annotated[
        Optional[str],
        typer.Option("--mode", help="Select a mode defined into a fobos file", autocompletion=_complete_fobos_mode),
    ] = None,
    lmodes: Annotated[bool, typer.Option("--lmodes", help="List the modes defined into a fobos file")] = False,
    print_fobos_template: Annotated[
        bool, typer.Option("--print-fobos-template", help="Print a comprehensive fobos template")
    ] = False,
    # fetch-specific options
    deps_dir: Annotated[
        Optional[str],
        typer.Option(
            "--deps-dir",
            help="Directory for storing fetched dependencies [default: .fobis_deps or fobos [dependencies] setting]",
        ),
    ] = None,
    update: Annotated[
        bool, typer.Option("--update", help="Update already-fetched dependencies (git fetch + re-checkout)")
    ] = False,
    no_build: Annotated[bool, typer.Option("--no-build", help="Only fetch dependencies, do not build them")] = False,
    # fancy group
    force_compile: Annotated[bool, typer.Option("--force-compile", help="Force to (re-)compile all")] = False,
    colors: Annotated[bool, typer.Option("--colors", help="Activate colors in shell prints")] = False,
    log: Annotated[bool, typer.Option("--log", "-l", help="Activate log file creation")] = False,
    graph: Annotated[bool, typer.Option("--graph", help="Generate a dependencies graph via graphviz")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Less verbose output")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", help="Extremely verbose output for debugging")] = False,
    jobs: Annotated[int, typer.Option("--jobs", "-j", help="Number of concurrent compilation jobs [default: 1]")] = 1,
    makefile: Annotated[
        Optional[str], typer.Option("--makefile", "-m", help="Generate a GNU Makefile for building the project")
    ] = None,
):
    """Fetch and build GitHub-hosted Fortran dependencies listed in the fobos [dependencies] section."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _ns(
        which="fetch",
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        lmodes=lmodes,
        print_fobos_template=print_fobos_template,
        deps_dir=deps_dir,
        update=update,
        no_build=no_build,
        force_compile=force_compile,
        colors=colors,
        log=log,
        graph=graph,
        quiet=quiet,
        verbose=verbose,
        jobs=jobs,
        makefile=makefile,
    )
