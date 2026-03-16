"""
_options.py — Shared Annotated option type aliases for FoBiS.py CLI commands.

Each alias captures the Typer Option metadata (flag names, help text,
autocompletion).  Command functions use these as parameter type annotations;
the default value is still declared at the call site so Typer can inspect it.
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

from typing import Annotated

import typer

from ._completions import (
    _complete_compiler,
    _complete_extensions,
    _complete_fobos_mode,
    _complete_mklib,
)

# ---------------------------------------------------------------------------
# Fobos group  (shared by all 6 commands)
# ---------------------------------------------------------------------------

FobosOpt = Annotated[
    str | None, typer.Option("--fobos", "-f", help='Specify a "fobos" file named differently from "fobos"')
]
FciOpt = Annotated[bool, typer.Option("--fci", help="Assume fobos inputs as case insensitive")]
ModeOpt = Annotated[
    str | None,
    typer.Option("--mode", help="Select a mode defined into a fobos file", autocompletion=_complete_fobos_mode),
]
LmodesOpt = Annotated[bool, typer.Option("--lmodes", help="List the modes defined into a fobos file")]
PrintFobosTemplateOpt = Annotated[
    bool, typer.Option("--print-fobos-template", help="Print a comprehensive fobos template")
]

# ---------------------------------------------------------------------------
# Compiler group  (build, clean, rule, doctests)
# ---------------------------------------------------------------------------

CompilerOpt = Annotated[
    str,
    typer.Option("--compiler", help="Compiler used (case insensitive, default gnu)", autocompletion=_complete_compiler),
]
FcOpt = Annotated[str | None, typer.Option("--fc", help="Fortran compiler statement (for --compiler custom)")]
CflagsOpt = Annotated[str | None, typer.Option("--cflags", help="Compile flags")]
LflagsOpt = Annotated[str | None, typer.Option("--lflags", help="Link flags")]
ModswOpt = Annotated[str | None, typer.Option("--modsw", help="Module search path switch (for --compiler custom)")]
MpiOpt = Annotated[bool, typer.Option("--mpi", help="Use MPI enabled version of compiler")]
OpenmpOpt = Annotated[bool, typer.Option("--openmp", help="Use OpenMP pragmas")]
OpenmpOffloadOpt = Annotated[bool, typer.Option("--openmp-offload", help="Use OpenMP Offload pragmas")]
CoarrayOpt = Annotated[bool, typer.Option("--coarray", help="Use coarrays")]
CoverageOpt = Annotated[bool, typer.Option("--coverage", help="Instrument for coverage analysis")]
ProfileOpt = Annotated[bool, typer.Option("--profile", help="Instrument for profiling analysis")]
MklibOpt = Annotated[
    str | None,
    typer.Option("--mklib", help="Build library instead of program (static|shared)", autocompletion=_complete_mklib),
]
ArOpt = Annotated[str, typer.Option("--ar", help="Archiver executable for static libraries [default: ar]")]
ArflagsOpt = Annotated[str, typer.Option("--arflags", help="Archiver flags for static libraries [default: -rcs]")]
RanlibOpt = Annotated[str, typer.Option("--ranlib", help="Ranlib executable; empty string to skip [default: ranlib]")]
CflagsHeritageOpt = Annotated[
    bool,
    typer.Option("--cflags-heritage", "--ch", help="Store cflags for heritage checking; re-compile all if they change"),
]
TrackBuildOpt = Annotated[bool, typer.Option("--track-build", "--tb", help="Store build info for the install command")]

# ---------------------------------------------------------------------------
# Directories group  (build, clean, rule, doctests)
# ---------------------------------------------------------------------------

SrcOpt = Annotated[list[str] | None, typer.Option("--src", "-s", help="Root-directory of source files [default: ./]")]
BuildDirOpt = Annotated[
    str, typer.Option("--build-dir", "--dbld", help="Directory containing built objects [default: ./]")
]
ObjDirOpt = Annotated[
    str, typer.Option("--obj-dir", "--dobj", help="Directory containing compiled objects [default: ./obj/]")
]
ModDirOpt = Annotated[
    str, typer.Option("--mod-dir", "--dmod", help="Directory containing .mod files [default: ./mod/]")
]
LibDirOpt = Annotated[list[str] | None, typer.Option("--lib-dir", "--dlib", help="Directories searched for libraries")]
IncludeListOpt = Annotated[
    list[str] | None, typer.Option("--include", "-i", help="Directories for searching included files")
]
ExcludeDirsOpt = Annotated[
    list[str] | None,
    typer.Option("--exclude-dirs", "--ed", help="Exclude directories from the building process"),
]
DisableRecursiveSearchOpt = Annotated[
    bool, typer.Option("--disable-recursive-search", "--drs", help="Disable recursive search inside directories")
]

# ---------------------------------------------------------------------------
# Files group  (build, clean, rule, doctests)
# ---------------------------------------------------------------------------

TargetOpt = Annotated[
    str | None, typer.Option("--target", "-t", help="Specify a target file [default: all programs found]")
]
OutputOpt = Annotated[str | None, typer.Option("--output", "-o", help="Output file name (used with --target)")]
ExcludeOpt = Annotated[
    list[str] | None, typer.Option("--exclude", "-e", help="Exclude files from the building process")
]
LibsOpt = Annotated[list[str] | None, typer.Option("--libs", help="External libraries with full paths")]
VlibsOpt = Annotated[list[str] | None, typer.Option("--vlibs", help="Volatile external libraries with full paths")]
ExtLibsOpt = Annotated[list[str] | None, typer.Option("--ext-libs", help="External libraries in compiler path")]
ExtVlibsOpt = Annotated[
    list[str] | None, typer.Option("--ext-vlibs", help="Volatile external libraries in compiler path")
]
DependonOpt = Annotated[
    list[str] | None,
    typer.Option("--dependon", help="Interdependent external fobos files for interdependent building"),
]
IncOpt = Annotated[
    list[str] | None,
    typer.Option("--inc", help="Extensions for include files", autocompletion=_complete_extensions),
]
ExtensionsOpt = Annotated[
    list[str] | None,
    typer.Option("--extensions", help="Extensions of parsed files", autocompletion=_complete_extensions),
]
BuildAllOpt = Annotated[bool, typer.Option("--build-all", help="Build all sources parsed")]

# ---------------------------------------------------------------------------
# Preprocessor group  (build, rule, doctests)
# ---------------------------------------------------------------------------

PreprocessorOpt = Annotated[
    str | None,
    typer.Option("--preprocessor", help="Preprocessor name for pre-processing sources (e.g. PreForM.py)"),
]
PreprocOpt = Annotated[str | None, typer.Option("--preproc", help="Preprocessor flags for the main compiler")]
PreprocessorArgsOpt = Annotated[str, typer.Option("--preprocessor-args", "--app", help="Preprocessor-specific flags")]
PreprocessorNoOOpt = Annotated[
    bool,
    typer.Option("--preprocessor-no-o", "--npp", help="Do not add -o in front of output in preprocessor command"),
]
PreprocessorDirOpt = Annotated[
    str | None, typer.Option("--preprocessor-dir", "--dpp", help="Directory for preprocessed files")
]
PreprocessorExtOpt = Annotated[
    list[str] | None, typer.Option("--preprocessor-ext", "--epp", help="File extensions to preprocess")
]

# ---------------------------------------------------------------------------
# Fancy group  (shared by all 6 commands)
# ---------------------------------------------------------------------------

ForceCompileOpt = Annotated[bool, typer.Option("--force-compile", help="Force to (re-)compile all")]
ColorsOpt = Annotated[bool, typer.Option("--colors", help="Activate colors in shell prints")]
LogOpt = Annotated[bool, typer.Option("--log", "-l", help="Activate log file creation")]
GraphOpt = Annotated[bool, typer.Option("--graph", help="Generate a dependencies graph via graphviz")]
QuietOpt = Annotated[bool, typer.Option("--quiet", "-q", help="Less verbose output")]
VerboseOpt = Annotated[bool, typer.Option("--verbose", help="Extremely verbose output for debugging")]
JobsOpt = Annotated[int, typer.Option("--jobs", "-j", help="Number of concurrent compilation jobs [default: 1]")]
MakefileOpt = Annotated[
    str | None, typer.Option("--makefile", "-m", help="Generate a GNU Makefile for building the project")
]

# ---------------------------------------------------------------------------
# rule-specific options
# ---------------------------------------------------------------------------

ExecuteOpt = Annotated[
    str | None, typer.Option("--execute", "--ex", help="Specify a rule (defined in fobos) to execute")
]
ListRulesOpt = Annotated[bool, typer.Option("--list", "--ls", help="List the rules defined in a fobos file")]
GetOpt = Annotated[str | None, typer.Option("--get", help="Get option value defined in fobos (e.g. --get build_dir)")]
GetOutputNameOpt = Annotated[
    bool, typer.Option("--get-output-name", help="Get the final output name from fobos options")
]
FordOpt = Annotated[str | None, typer.Option("--ford", help="Build docs with Ford tool (specify project-file.md)")]
GcovAnalyzerOpt = Annotated[
    list[str] | None,
    typer.Option("--gcov-analyzer", help="Analyse .gcov files; args: REPORTS_DIR [SUMMARY_FILE]"),
]
IsAsciiKindSupportedOpt = Annotated[
    bool, typer.Option("--is-ascii-kind-supported", help="Check if compiler supports ASCII kind")
]
IsUcs4KindSupportedOpt = Annotated[
    bool, typer.Option("--is-ucs4-kind-supported", help="Check if compiler supports UCS4 kind")
]
IsFloat128KindSupportedOpt = Annotated[
    bool, typer.Option("--is-float128-kind-supported", help="Check if compiler supports float128 kind")
]

# ---------------------------------------------------------------------------
# doctests-specific options
# ---------------------------------------------------------------------------

KeepVolatileDoctestsOpt = Annotated[
    bool, typer.Option("--keep-volatile-doctests", help="Keep the volatile doctests programs")
]
ExcludeFromDoctestsOpt = Annotated[
    list[str] | None, typer.Option("--exclude-from-doctests", help="Exclude files from the doctests process")
]

# ---------------------------------------------------------------------------
# Output format option  (build, clean, fetch)
# ---------------------------------------------------------------------------

JsonOpt = Annotated[
    bool,
    typer.Option(
        "--json",
        help="Emit structured JSON to stdout instead of human-readable output (useful for scripting / agents)",
    ),
]
