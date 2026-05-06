"""
ParsedFile.py, module definition of Dependency class.
This is a class designed for handling a single parsed file.
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

import sys
from typing import Any

try:
    import functools

    import graphviz as gvz

    __graph__ = functools.partial(gvz.Graph, format="svg")
    __digraph__ = functools.partial(gvz.Digraph, format="svg")
    __styles__ = {
        "graph": {"fontsize": "16", "fontcolor": "black", "bgcolor": "white", "rankdir": "BT"},
        "nodes": {
            "fontname": "Helvetica",
            "shape": "box",
            "fontcolor": "black",
            "color": "black",
            "style": "filled, rounded",
            "fillcolor": "white",
        },
        "edges": {
            "style": "dashed",
            "color": "black",
            "arrowhead": "open",
            "fontname": "Courier",
            "fontsize": "12",
            "fontcolor": "black",
        },
    }
    __graphviz__ = True

    def add_nodes(graph, nodes):
        """
        Auxiliary function for adding nodes to the dependency graph.

        Parameters
        ----------
        graph : __graph__ object
        nodes : nodes to be added to the graph
        """
        for node in nodes:
            if isinstance(node, tuple):
                graph.node(node[0], **node[1])
            else:
                graph.node(node)
        return graph

    def add_edges(graph, edges):
        """
        Auxiliary function for adding edges to the dependency graph.

        Parameters
        ----------
        graph : __graph__ object
        edges : nodes to be added to the graph
        """
        for edge in edges:
            if isinstance(edge[0], tuple):
                graph.edge(*edge[0], **edge[1])
            else:
                graph.edge(*edge)
        return graph

    def apply_styles(graph):
        """
        Auxiliary function for adding styles to the dependency graph.

        Parameters
        ----------
        graph : __graph__ object
        """
        graph.graph_attr.update(("graph" in __styles__ and __styles__["graph"]) or {})
        graph.node_attr.update(("nodes" in __styles__ and __styles__["nodes"]) or {})
        graph.edge_attr.update(("edges" in __styles__ and __styles__["edges"]) or {})
        return graph
except ImportError:
    __graphviz__ = False
import operator
import os
import re
import shlex
from subprocess import STDOUT, CalledProcessError, check_output

from .Dependency import Dependency
from .Doctest import Doctest
from .utils import traverse_recursive, unique_seq

# definition of regular expressions
__str_apex__ = r"('|" + r'")'
__str_kw_include__ = r"[Ii][Nn][Cc][Ll][Uu][Dd][Ee]"
__str_kw_intrinsic__ = r"[Ii][Nn][Tt][Rr][Ii][Nn][Ss][Ii][Cc]"
__str_kw_module__ = r"[Mm][Oo][Dd][Uu][Ll][Ee]"
__str_kw_submodule__ = r"[Ss][Uu][Bb][Mm][Oo][Dd][Uu][Ll][Ee]"
__str_kw_program__ = r"[Pp][Rr][Oo][Gg][Rr][Aa][Mm]"
__str_kw_use__ = r"[Uu][Ss][Ee]"
__str_kw_mpifh__ = r"[Mm][Pp][Ii][Ff]\.[Hh]"
__str_name__ = r"(?P<name>[a-zA-Z][a-zA-Z0-9_]*)"
__str_submodule_ancestor__ = r"(\((?P<submancestor>[a-zA-Z][a-zA-Z0-9_]*)\))"
__str_eol__ = r"(?P<eol>\s*!.*|\s*)?$"
# __str_f95_mod_rename__ = r"(\s*,\s*[a-zA-Z][a-zA-Z0-9_]*\s*=>\s*[a-zA-Z][a-zA-Z0-9_]*)*"
# __str_f95_mod_only__ = r"(\s*,\s*[Oo][Nn][Ll][Yy]\s*:\s*([a-zA-Z][a-zA-Z0-9_]*\s*=>\s*[a-zA-Z][a-zA-Z0-9_]*|[a-zA-Z][a-zA-Z0-9_]*))*"
__str_use_mod__ = (
    r"^(\s*)"  # eventual initial white spaces
    + __str_kw_use__  # keyword "use"
    +
    # r"(\s*,\s*.*\s*::)*" +  # eventual module nature
    # r"(\s+)" +  # 1 or more white spaces
    r"((\s*,\s*.*\s*::)|(\s*::\s*)|(\s+))"  # eventual module nature
    + __str_name__  # construct name
    + r"(?P<mod_eol>(.*))"
)
__str_use_mod_intrinsic__ = (
    r"^(\s*)"  # eventual initial white spaces
    + __str_kw_use__  # keyword "use"
    + r"\s*,\s*"
    + __str_kw_intrinsic__
    + r"\s*::.*"  # keyword intrinsic
    + r"(?P<mod_eol>(.*))"
)
# Per-module intrinsic regexes (`__str_use_mod_iso_fortran_env__` etc.) used
# to live here.  They were replaced by name-based lookup against
# ``_INTRINSIC_MODULES`` in the parse loop.  Only the syntactic form
# ``use, intrinsic :: NAME`` (above) is still regex-matched, because that
# is a *form* — name-agnostic — and cannot fold into a name set.
__str_include__ = (
    r"^(\s*|\#)"  # eventual initial white spaces or "#" character
    + __str_kw_include__  # keyword "include"
    + r"(\s+)"  # 1 or more white spaces
    + __str_apex__  # character "'" or '"'
    + r"(\s*)"  # eventaul white spaces
    + r"(?P<name>.*)"  # name of included file
    + r"(\s*)"  # eventaul white spaces
    + __str_apex__  # character "'" or '"'
    + __str_eol__
)  # eventual eol white space and or comment
__str_module__ = (
    r"^(\s*)"  # eventual initial white spaces
    + r"(?P<scplevel>"
    + __str_kw_module__
    + r")"  # keyword "module"
    + r"(\s+)"  # 1 or more white spaces
    + __str_name__  # construct name
    + __str_eol__
)  # eventual eol white space and or comment
__str_submodule__ = (
    r"^(\s*)"  # eventual initial white spaces
    + r"(?P<scplevel>"
    + __str_kw_submodule__
    + r")"  # keyword "submodule"
    + r"(\s+)"  # 1 or more white spaces
    +
    # r"(\(.*\))" +
    __str_submodule_ancestor__  # (ancestor-module-name [:parent-submodule-name])
    + r"(\s+)"  # 1 or more white spaces
    + __str_name__  # construct name
    + __str_eol__
)  # eventual eol white space and or comment
__str_program__ = (
    r"^(\s*)"  # eventual initial white spaces
    + r"(?P<scplevel>"
    + __str_kw_program__
    + r")"  # keyword "program"
    + r"(\s+)"  # 1 or more white spaces
    + __str_name__  # construct name
    + __str_eol__
)  # eventual eol white space and or comment
__str_mpifh__ = r"(.*)" + __str_kw_mpifh__ + r"(.*)"
__regex_use_mod__ = re.compile(__str_use_mod__)
__regex_include__ = re.compile(__str_include__)
__regex_program__ = re.compile(__str_program__)
__regex_module__ = re.compile(__str_module__)
__regex_submodule__ = re.compile(__str_submodule__)
__regex_use_mod_intrinsic__ = re.compile(__str_use_mod_intrinsic__)
# Single-element list for the surviving syntactic form.  The list shape is
# kept (rather than collapsing to a scalar) so the parse loop's
# ``any(re.match(...) for ...)`` idiom continues to work and reads the
# same as before.
__regex_use_intrinsic_modules__ = [
    __regex_use_mod_intrinsic__,
]
__regex_mpifh__ = re.compile(__str_mpifh__)

# Universal intrinsic modules — recognised by every supported Fortran
# compiler.  Names are lowercased; the parser's lookup also lowercases the
# matched `use NAME` token before checking membership.  Replaces the legacy
# per-module regex chain (kept in parallel during the refactor; deleted in
# a later step).  The `use, intrinsic :: NAME` syntactic form (where the
# user explicitly forces the intrinsic version of a same-named module) is
# still handled by ``__regex_use_mod_intrinsic__`` — that's a *form*, not
# a *name*, and can't fold into a name set.
_INTRINSIC_MODULES: frozenset[str] = frozenset(
    {
        "iso_fortran_env",
        "iso_c_binding",
        "ieee_exceptions",
        "ieee_arithmetic",
        "ieee_features",
        "openacc",
        "omp_lib",
        "mpi",
    }
)

# Compiler-specific intrinsic modules.  Filtering is conditional: a module
# is silently skipped only when the *active* compiler ships it as built-in.
# Switching compiler (e.g. nvfortran → gnu) makes the dependency reappear
# as unresolved, which is the right behaviour — gnu does NOT supply
# cudafor, so the project must redirect the `use` line via #ifdef guards
# or grow a portable backend abstraction.
#
# Names are stored lowercased; the lookup compares the lowercased module
# name from the parser.  Keep this list conservative — adding an entry
# silences a real-world warning whose only fix path is "use a different
# compiler", which is rare.
_COMPILER_INTRINSIC_MODULES: dict[str, frozenset[str]] = {
    "nvfortran": frozenset(
        {
            "cudafor",  # CUDA Fortran runtime
            "cudadeviceprop",
            "cublas",
            "cublas_v2",
            "cusparse",
            "cusolverdn",
            "curand",
            "curand_device",
            "cufft",
            "nccl",
            "nvtx",
            "thrust",
        }
    ),
    "pgi": frozenset(
        {
            "cudafor",
            "cudadeviceprop",
            "cublas",
            "cublas_v2",
            "cusparse",
            "cusolverdn",
            "curand",
            "cufft",
        }
    ),
    "intel": frozenset(
        {
            "ifport",
            "ifcore",
            "ifqwin",
            "iflogm",
            "dfport",
            "mkl_service",
        }
    ),
    "intel_nextgen": frozenset(
        {
            "ifport",
            "ifcore",
            "ifqwin",
            "iflogm",
            "dfport",
            "mkl_service",
        }
    ),
}


def _is_intrinsic_module(name: str, compiler: str = "", extra: list[str] | None = None) -> bool:
    """
    Return True iff ``name`` is an intrinsic module that should be filtered
    from the dependency graph.

    Membership is checked, in order, against:

      1. ``_INTRINSIC_MODULES`` — universal Fortran intrinsics
         (``iso_fortran_env``, ``iso_c_binding``, ``ieee_*``, ``openacc``,
         ``omp_lib``, ``mpi``).  Always filtered regardless of compiler.
      2. ``_COMPILER_INTRINSIC_MODULES[compiler]`` — modules supplied as
         intrinsic only by specific compilers (e.g. nvfortran's ``cudafor``).
         Filtered only when that compiler is active.
      3. ``extra`` — caller-supplied list (e.g. the fobos
         ``intrinsic_modules = ...`` mode key).  Always filtered.

    Lookup is case-insensitive — Fortran identifiers are.  An empty or
    unknown ``compiler`` skips step 2 only; the universal set in step 1
    still applies.

    Parameters
    ----------
    name : str
        Module name as captured from a ``use`` statement.
    compiler : str
        Active compiler key (``"gnu"``, ``"nvfortran"``, …).
    extra : list[str] | None
        Additional names treated as intrinsic regardless of compiler.

    Returns
    -------
    bool
    """
    n = (name or "").lower()
    if not n:
        return False
    if n in _INTRINSIC_MODULES:
        return True
    if compiler:
        builtin = _COMPILER_INTRINSIC_MODULES.get(compiler.lower())
        if builtin is not None and n in builtin:
            return True
    return bool(extra and n in {x.lower() for x in extra})


# Legacy alias retained for any external caller that might import the old
# name.  New code should use ``_is_intrinsic_module``.
_is_compiler_intrinsic_module = _is_intrinsic_module


def openReader(filename: str) -> Any:
    return open(filename, newline="", encoding="utf8")


def _needs_preprocessing(extension: str, inc: list[str]) -> bool:
    """
    Decide whether ``cpp`` should expand a file before the parser scans it.

    Two triggers:

      * Extension is in ``inc`` — the legacy "include file" path (``.h``,
        ``.H``, ``.inc``, ``.INC``).  Preserves prior behaviour for the
        files this was originally designed for.
      * Extension is uppercase Fortran (``.F``, ``.F90``, ``.F03``,
        ``.FPP``, …) — the long-standing convention every Fortran compiler
        uses to mean "this file needs preprocessing".  Lowercase
        counterparts (``.f90``) skip cpp.

    The uppercase rule lets ``use MACRO_NAME`` lines (and ``#ifdef``-guarded
    ``use`` statements) be expanded *before* dependency scanning, so the
    parser sees the real module names instead of unresolvable cpp tokens.

    Parameters
    ----------
    extension : str
        Extension of the file, including the leading dot (e.g. ``".F90"``).
    inc : list[str]
        Extensions explicitly marked as include-files in cliargs.

    Returns
    -------
    bool
    """
    if extension in inc:
        return True
    # Uppercase-Fortran convention: ".F90", ".F03", ".F", ".FPP", ".F95", …
    return len(extension) >= 2 and extension.startswith(".") and extension[1:].isupper()


class ParsedFile:
    """ParsedFile is an object that handles a single parsed file, its attributes and methods."""

    def __init__(
        self,
        name: str,
        program: bool = False,
        module: bool = False,
        submodule: bool = False,
        include: bool = False,
        nomodlib: bool = False,
        to_compile: bool = False,
        output: str | None = None,
        is_doctest: bool = False,
    ) -> None:
        """
        Parameters
        ----------
        name : str
          file name
        program : {False}
          flag for tagging program file
        module : {False}
          flag for tagging module file
        submodule : {False}
          flag for tagging submodule file
        include : {False}
          flag for tagging include file
        nomodlib : {False}
          flag for tagging library of procedures without an enclosing module (old Fortran style)
        to_compile : {False}
          flag for tagging file to be compiled
        output : {None}
          string of output file name

        Attributes
        ----------
        name : str
          file name
        program : bool
          flag for tagging program file
        module : bool
          flag for tagging module file
        submodule : bool
          flag for tagging submodule file
        include : bool
          flag for tagging include file
        nomodlib : bool
          flag for tagging library of procedures without an enclosing module (old Fortran style)
        to_compile : bool
          flag for tagging file to be compiled
        output : str
          string of output file name
        basename : str
          basename of file name
        extension : str
          extension of file name
        timestamp : str
          timestamp of file
        order :
        pfile_dep : list
          list of parsed file dependencies
        doctest : Doctest()
          doctest object
        """
        self.name = name
        self.program = program
        self.module = module
        self.submodule = submodule
        self.include = include
        self.nomodlib = nomodlib
        self.to_compile = to_compile
        self.output = output
        self.is_doctest = is_doctest
        self.basename = os.path.splitext(os.path.basename(self.name))[0]
        self.extension = os.path.splitext(os.path.basename(self.name))[1]
        self.timestamp = os.path.getmtime(self.name)
        self.order = 0
        self.pfile_dep = None
        self.pfile_dep_all = None
        self.module_names = None
        self.submodule_names = None
        self.dependencies = None
        self.doctest = None
        return

    def sort_dependencies(self) -> None:
        """
        Sort dependencies.
        """
        for dep in self.pfile_dep_all:
            for other_dep in self.pfile_dep_all:
                if other_dep != dep:
                    if dep in other_dep.pfile_dep_all:
                        dep.order += 1
        self.pfile_dep_all.sort(key=operator.attrgetter("order"), reverse=True)
        return

    def parse(
        self,
        inc: list[str] = [".INC", ".F", ".FOR", ".FPP", ".F77", ".F90", ".F95", ".F03", ".F08"],
        preprocessor: str = "cpp",
        preproc: str = "",
        include: str | list[str] = "",
        compiler: str = "",
        intrinsic_modules: list[str] | None = None,
    ) -> None:
        """
        Parse the file creating its the dependencies list and the list of modules names that self eventually contains.

        Parameters
        ----------
        inc : list
          list of extensions of included files
        preprocessor : str
          preprocessor name
        preproc : str
          preprocessor flags
        include : list
          include directories
        compiler : str
          active compiler key (e.g. ``"nvfortran"``); used to filter
          compiler-specific intrinsic modules like ``cudafor``.  An empty
          or unknown compiler disables compiler-conditional filtering
          (preserves prior behaviour).
        intrinsic_modules : list[str] | None
          extra module names to treat as intrinsic regardless of compiler
          (e.g. fobos-declared ``intrinsic_modules = my_helper``).
        """
        self.module_names = []
        self.submodule_names = []
        self.dependencies = []

        if _needs_preprocessing(self.extension, inc):
            preprocessor_exist = False
            for path in os.environ["PATH"].split(os.pathsep):
                preprocessor_exist = os.path.exists(os.path.join(path, preprocessor))
                if preprocessor_exist:
                    break
            if preprocessor_exist:
                if preprocessor == "cpp":
                    preprocessor += " -C -w "
                elif preprocessor == "fpp":
                    preprocessor += " -w "
                if preproc is None:
                    preproc = ""
                # Always add the source file's own directory to the search
                # path so `#include "header.H"` finds source-co-located
                # headers (the common Fortran-with-cpp pattern).
                includes_list = [os.path.dirname(self.name) or "."]
                if len(include) > 0:
                    if isinstance(include, str):
                        includes_list.append(include)
                    else:
                        includes_list.extend(include)
                includes = " " + " ".join(f"-I{p}" for p in includes_list) + " "
                try:
                    source = str(
                        check_output(
                            shlex.split(preprocessor + " " + preproc + includes + self.name),
                            shell=False,
                            stderr=STDOUT,
                            encoding="UTF-8",
                        )
                    )
                    source = source.replace("\\n", "\n")
                except CalledProcessError:
                    # cpp failed (e.g. missing include path the user must
                    # provide).  Fall back to the raw file so dependency
                    # scanning can still proceed; macro-driven `use` lines
                    # may show up as "unreachable" warnings, but that's
                    # better than crashing the whole parse.
                    source = str(openReader(self.name).read())
            else:
                source = str(openReader(self.name).read())
        else:
            source = str(openReader(self.name).read())

        for line in source.split("\n"):
            matching = re.match(__regex_program__, line)
            if matching:
                self.program = True
            matching = re.match(__regex_module__, line)
            if matching:
                self.module = True
                self.module_names.append(matching.group("name"))
            matching = re.match(__regex_submodule__, line)
            if matching:
                self.submodule = True
                self.submodule_names.append(matching.group("name"))
                dep = Dependency(dtype="module", name=matching.group("submancestor"))
                self.dependencies.append(dep)
            matching = re.match(__regex_use_mod__, line)
            if matching:
                # Two-stage filter:
                #   1. Legacy regex chain — matches `use, intrinsic ::` form
                #      (a *syntactic* declaration, name-agnostic) plus the
                #      historical per-module regexes (kept in parallel for
                #      this refactor; pruned in a later step).
                #   2. Unified name-set helper — universal intrinsics
                #      (iso_*, ieee_*, openacc, omp_lib, mpi) plus
                #      compiler-specific (cudafor under nvfortran, …) plus
                #      user-supplied `intrinsic_modules` list.
                # Either filter triggering means the use is intrinsic and
                # not a real dependency.
                name = matching.group("name")
                if not any(
                    re.match(regex, line) for regex in __regex_use_intrinsic_modules__
                ) and not _is_intrinsic_module(name, compiler, intrinsic_modules):
                    dep = Dependency(dtype="module", name=name)
                    self.dependencies.append(dep)
            matching = re.match(__regex_include__, line)
            if matching:
                if not re.match(__regex_mpifh__, line):
                    dep = Dependency(dtype="include", name=matching.group("name"))
                    self.dependencies.append(dep)

        if self.module:
            self.doctest = Doctest()
            self.doctest.parse(source=source)
            self.doctest.make_volatile_programs()

        if not self.program and not self.module and not self.submodule:
            if os.path.splitext(os.path.basename(self.name))[1] not in inc:
                self.nomodlib = True

    def save_build_log(self, builder: Any) -> None:
        """
        Save a log file containing information about the building options used.

        Parameters
        ----------
        builder : Builder object
          builder used for building self
        """
        with open(os.path.join(builder.build_dir, "build_" + self.basename + ".log"), "w") as log_file:
            log_file.writelines("Hierarchical dependencies list of: " + self.name + "\n")
            for dep in self.pfile_dep:
                log_file.writelines("  " + dep.name + "\n")
                log_file.writelines(dep.str_dependencies(pref="    "))
            log_file.writelines("Complete ordered dependencies list of: " + self.name + "\n")
            for dep in self.pfile_dep_all:
                log_file.writelines("  " + dep.name + "\n")
            log_file.writelines(builder.verbose())
        return

    def save_dep_graph(self) -> None:
        """
        Save dependency graph.
        """
        if __graphviz__:
            depgraph = __digraph__()
            depgraph = add_nodes(depgraph, [self.name])
            depgraph.graph_attr["label"] = "Dependencies graph of " + self.name
            for dep in self.pfile_dep:
                depgraph = add_nodes(depgraph, [dep.name])
                depgraph = add_edges(depgraph, [(self.name, dep.name)])
                for subdep in dep.str_dependencies().split("\n"):
                    if subdep != "":
                        depgraph = add_nodes(depgraph, [subdep])
                        depgraph = add_edges(depgraph, [(dep.name, subdep)])
            depgraph = apply_styles(depgraph)
            depgraph.render("dependency_graph_" + self.basename)
        else:
            print("Module 'graphviz' not found: saving of dependency graph disabled")
        return

    def gnu_make_rule(self, builder: Any) -> str:
        """
        Return the file compiling rule in GNU Make format

        Parameters
        ----------
        builder : Builder object

        Returns
        -------
        str
          string containing the compiling rule of the file
        """
        string = []
        target = self.basename.lower()
        if not self.include:
            objs = []
            for dep in self.pfile_dep:
                if not dep.include and os.path.splitext(os.path.basename(dep.name))[0].lower() != target:
                    objs.append("\t$(DOBJ)" + os.path.splitext(os.path.basename(dep.name))[0].lower() + ".o")
            deps = [self.name]
            for dep in self.pfile_dep:
                if dep.include:
                    deps.append(dep.name)
            if len(objs) > 0:
                string.append("$(DOBJ)" + target + ".o:" + "".join([" " + dep for dep in deps]) + " \\" + "\n")
                for obj in objs[:-1]:
                    string.append(obj + " \\" + "\n")
                string.append(objs[-1] + "\n")
            else:
                string.append("$(DOBJ)" + target + ".o:" + "".join([" " + dep for dep in deps]) + "\n")
            string.append("\t@echo $(COTEXT)\n")
            string.append("\t@$(FC) $(OPTSC) " + "".join(["-I" + i + " " for i in builder.dinc]) + " $< -o $@\n")
            string.append("\n")
        return "".join(string)

    def str_dependencies(self, pref: str = "") -> str:
        """
        Create a string containing the depencies files list.

        Parameters
        ----------
        pref : {""}
          prefixing string
        """
        str_dep = ""
        for dep in self.pfile_dep:
            str_dep += pref + dep.name + "\n"
        return str_dep

    def obj_dependencies(self, exclude_programs: bool = False) -> list[str]:
        """
        Create a list containing the dependencies object files list.

        Parameters
        ----------
        exclude_programs : {False}
          flag for excluding programs obj from the list
        """
        if exclude_programs:
            return [p.basename + ".o" for p in self.pfile_dep_all if not p.include and not p.program]
        else:
            return [p.basename + ".o" for p in self.pfile_dep_all if not p.include]

    def check_compile(self, obj_dir: str, force_compile: bool = False) -> None:
        """
        Check if self must be compiled.

        Parameters
        ----------
        obj_dir : str
          directory where compiled objects are saved
        force_compile : {False}
          flag for forcing (re-)compiling of all dependency
        """
        if not self.include:
            # verifying if dependencies are up-to-date
            for dep in self.pfile_dep_all:
                if not dep.include:
                    if force_compile:
                        self.to_compile = True
                    else:
                        obj = os.path.join(obj_dir, dep.basename + ".o")
                        # verifying if dep is up-to-date
                        if os.path.exists(obj):
                            if os.path.getmtime(obj) < dep.timestamp:
                                # found a dependency object that is out-of-date, thus self (and dep) must be compiled
                                self.to_compile = True
                        else:
                            # compiled object of a dependency is absent, thus self must be compiled
                            self.to_compile = True
                else:
                    # verifying if dep is newer than self
                    if not os.path.exists(dep.name):
                        print(
                            "error: file " + dep.name + " does not exist, but it is a dependency of file " + self.name
                        )
                        sys.exit(1)
                    else:
                        # comparing the include dependency with the self-compiled-object if exist
                        obj = os.path.join(obj_dir, self.basename + ".o")
                        # verifying if dep is up-to-date
                        if os.path.exists(obj):
                            if os.path.getmtime(obj) < os.path.getmtime(dep.name):
                                # found an include that is newer than self-compiled-object, thus self must be compiled
                                self.to_compile = True
            # verifying if self is up-to-date
            if not self.to_compile:
                obj = os.path.join(obj_dir, self.basename + ".o")
                if os.path.exists(obj):
                    if os.path.getmtime(obj) < self.timestamp:
                        # the compiled object is out-of-date, thus self must be compiled
                        self.to_compile = True
                else:
                    # compiled object is absent, thus self must be compiled
                    self.to_compile = True

    def create_pfile_dep_all(self) -> None:
        """
        Create a complete list of all dependencies direct and indirect.
        """
        self.pfile_dep_all = []
        for path in traverse_recursive(self):
            self.pfile_dep_all.append(path[-1])
        self.pfile_dep_all = unique_seq(self.pfile_dep_all)
        return
