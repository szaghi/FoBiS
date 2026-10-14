"""explain.py — ``fobis build --explain``: why a compile or link step failed.

Two stages. First the **deterministic** classes, answered from the project's facts with no model: a missing
module (defined where? compiled by this build? a declared dependency not fetched? a library module needing
``--mpi``/``--openmp``?), an undefined or multiply defined symbol (demangled, located in the sources, and why
its object is not linked), objects of another compiler (its runtime symbols are missing), and internal compiler
errors. Later errors of a file whose module is missing, or of a link whose runtime is wrong, are consequences
and are not explained one by one.

Then, for the first error no class covers, a **grounded** explanation (`fobis.ai.grounding`): the message, the
build settings, and numbered sources (the code around the error, the declarations of the enclosing procedure,
the interfaces of the project procedures named on the line, knowledge-pack sections), answered as cited
``cause`` / ``fix`` claims. ``--explain-context`` prints that input without running a model.
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

from __future__ import annotations

import difflib
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..analysis import FileUnits, Unit, read_source
from ..lint.engine import analyse, display_path
from ..llm.provider import messages
from .ask import route_packs
from .diagnostics import Diagnostic, Symbol, demangle
from .grounding import ANSWER_TOKENS, ContextBundle, Grounded, Source, check_claims, claims_schema, load_prompt

if TYPE_CHECKING:
    from ..kb import KnowledgeBase
    from ..llm.provider import Provider

KINDS = ["cause", "fix"]
GROUPS = {"cause": "Cause", "fix": "Fix"}

_MPI = "build with `--mpi` (the MPI wrapper compiler, e.g. mpif90) or set `mpi = True` in the fobos mode"
_OPENMP = "build with `--openmp` or set `openmp = True` in the fobos mode (the flag must reach the link too)"
_OPENACC = "compile and link with the OpenACC flag of the compiler (nvfortran `-acc`, gfortran `-fopenacc`)"
_HDF5 = "add the HDF5 Fortran include directory to `cflags` and `-lhdf5_fortran -lhdf5` to `lflags` (`h5fc -show`)"
_NETCDF = "add `$(nf-config --fflags)` to `cflags` and `$(nf-config --flibs)` to `lflags`"

# Modules provided by libraries, not by sources: (library, what to do)
LIBRARY_MODULES = {
    "mpi": ("MPI", _MPI),
    "mpi_f08": ("MPI", _MPI),
    "omp_lib": ("OpenMP", _OPENMP),
    "omp_lib_kinds": ("OpenMP", _OPENMP),
    "openacc": ("OpenACC", _OPENACC),
    "cudafor": ("CUDA Fortran", "compile and link with nvfortran `-cuda`"),
    "hdf5": ("HDF5", _HDF5),
    "h5lt": ("HDF5", _HDF5),
    "netcdf": ("netCDF", _NETCDF),
}
# Symbols of libraries: (pattern, library, what to do)
LIBRARY_SYMBOLS = [
    (re.compile(r"^(p?mpi_|ompi_|__mpi_f08)", re.IGNORECASE), "MPI", _MPI),
    (re.compile(r"^(omp_|GOMP_|__kmpc_)"), "OpenMP", _OPENMP),
    (re.compile(r"^(acc_|GOACC_|__pgi_uacc_)"), "OpenACC", _OPENACC),
    (re.compile(r"^(h5\w*_f_|H5)"), "HDF5", _HDF5),
    (re.compile(r"^(nf90_|nf_|nc_)"), "netCDF", _NETCDF),
    (
        re.compile(r"^[sdcz](gemm|gemv|ger|gesv|getrf|getrs|getri|potrf|potrs|syev|heev|axpy|dot|scal|copy|nrm2)_$"),
        "BLAS/LAPACK",
        "add the BLAS/LAPACK libraries to `lflags` or `libs` (e.g. `-llapack -lblas`, or the vendor library)",
    ),
]
# Fortran runtime libraries: symbol pattern -> compiler (the `compiler` names of FoBiS)
RUNTIMES = [
    (re.compile(r"^_gfortran_"), "gnu"),
    (re.compile(r"^(for_|__intel_)"), "intel"),
    (re.compile(r"^(pgf90_|f90io_|fort_|__pgi_)"), "nvfortran"),
    (re.compile(r"^_lfortran_"), "lfortran"),
]
COMPILER_NAMES = {
    "gnu": "gfortran",
    "intel": "Intel ifort",
    "intel_nextgen": "Intel ifx",
    "nvfortran": "nvfortran",
    "pgi": "PGI/nvfortran",
    "lfortran": "LFortran",
}
_SAME_RUNTIME = {"intel_nextgen": "intel", "pgi": "nvfortran", "opencoarrays-gnu": "gnu"}
_MAIN_SYMBOLS = {"MAIN__", "MAIN_", "main"}

_MISSING_MODULE = [
    re.compile(r"Cannot open module file [\u2018'`\"](?P<name>\w+)\.s?mod[\u2019'`\"]", re.IGNORECASE),
    re.compile(r"Unable to open MODULE file (?P<name>\w+)\.s?mod", re.IGNORECASE),
    re.compile(r"Module '(?P<name>\w+)' modfile was not found", re.IGNORECASE),
]
_MODULE_STATEMENT = re.compile(r"^\s*module\s+(?!procedure\b|function\b|subroutine\b)(\w+)\s*(?:!.*)?$", re.I | re.M)
_IDENTIFIER = re.compile(r"\b[a-z_]\w*\b", re.IGNORECASE)


# ── facts ──────────────────────────────────────────────────────────────────────


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


@dataclass
class BuildFacts:
    """What FoBiS knows about the project and the failed build.

    Attributes
    ----------
    compiler : str
        FoBiS compiler name (``gnu``, ``intel_nextgen`` ...).
    mode : str or None
        The fobos mode.
    cflags : str
        Compile flags.
    files : dict
        Normalised path to the analysed sources of the project (fetched dependencies apart).
    built : set or None
        Normalised paths of the files this build compiles (None: unknown).
    linked : set or None
        Normalised paths of the files whose objects the failed target links (None: unknown).
    target : str or None
        The target being built when the build failed.
    dependencies : dict
        fobos ``[dependencies]``: name to specification.
    deps_dir : str
        Where fetched dependencies live.
    dep_files : dict
        Normalised path to (dependency name, analysed source) for the fetched dependencies.
    raw_modules : dict
        Module name to the files whose text has a ``module`` statement, active or not.
    src, exclude, exclude_dirs : list of str
        The build's source directories and exclusions (to say why a file is not compiled).
    """

    compiler: str = "gnu"
    mode: str | None = None
    cflags: str = ""
    files: dict[str, FileUnits] = field(default_factory=dict)
    built: set[str] | None = None
    linked: set[str] | None = None
    target: str | None = None
    dependencies: dict[str, str] = field(default_factory=dict)
    deps_dir: str = ".fobis_deps"
    dep_files: dict[str, tuple[str, FileUnits]] = field(default_factory=dict)
    raw_modules: dict[str, list[str]] = field(default_factory=dict)
    src: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    exclude_dirs: list[str] = field(default_factory=list)
    _memo: dict = field(default_factory=dict, repr=False, compare=False)

    def not_built_reason(self, path: str) -> str:
        """Why this build does not compile *path* (normalised), as far as the settings tell."""
        if os.path.basename(path) in {os.path.basename(e) for e in self.exclude}:
            return f"`exclude` lists {os.path.basename(path)}"
        for directory in self.exclude_dirs:
            if directory and _norm(directory) in path:
                return f"`exclude_dirs` lists {directory}"
        if self.src and not any(path.startswith(_norm(d).rstrip(os.sep) + os.sep) for d in self.src):
            return f"it is outside the source directories (`src = {' '.join(self.src)}`)"
        return "the build did not select it"

    @classmethod
    def scan(
        cls,
        sources: Iterable[str],
        deps_dir: str = ".fobis_deps",
        defines: dict[str, str] | None = None,
        **kwargs,
    ) -> BuildFacts:
        """Facts from the source files *sources* (already discovered) and the dependencies in *deps_dir*."""
        from ..cli._constants import __extensions_parsed__

        facts = cls(deps_dir=deps_dir, **kwargs)
        for path in sources:
            units = _analyse(path, defines)
            if units is not None:
                facts.files[_norm(path)] = units
                for name in _MODULE_STATEMENT.findall(read_source(path)):
                    facts.raw_modules.setdefault(name.lower(), []).append(_norm(path))
        if os.path.isdir(deps_dir):
            for name in sorted(os.listdir(deps_dir)):
                top = os.path.join(deps_dir, name)
                if not os.path.isdir(top):
                    continue
                for root, dirs, names in os.walk(top):
                    dirs[:] = sorted(d for d in dirs if not d.startswith("."))
                    for fname in sorted(names):
                        if os.path.splitext(fname)[1] in __extensions_parsed__:
                            path = os.path.join(root, fname)
                            units = _analyse(path, defines)
                            if units is not None:
                                facts.dep_files[_norm(path)] = (name, units)
        return facts

    def modules(self) -> dict[str, list[str]]:
        """Module name to the project files defining it (in the active preprocessor branches)."""
        if "modules" in self._memo:
            return self._memo["modules"]
        found: dict[str, list[str]] = self._memo.setdefault("modules", {})
        for path, units in self.files.items():
            for unit in units.units:
                if unit.kind == "module" and unit.name:
                    found.setdefault(unit.name, []).append(path)
        return found

    def dep_modules(self) -> dict[str, tuple[str, str]]:
        """Module name to (dependency, file) for the fetched dependencies."""
        if "dep_modules" in self._memo:
            return self._memo["dep_modules"]
        found: dict[str, tuple[str, str]] = self._memo.setdefault("dep_modules", {})
        for path, (dep, units) in self.dep_files.items():
            for unit in units.units:
                if unit.kind == "module" and unit.name:
                    found.setdefault(unit.name, (dep, path))
        return found

    def procedures(self) -> dict[str, list[tuple[str, Unit]]]:
        """Procedure name to (file, unit) for every non-interface procedure of the project and dependencies."""
        if "procedures" in self._memo:
            return self._memo["procedures"]
        found: dict[str, list[tuple[str, Unit]]] = self._memo.setdefault("procedures", {})
        everything = [*self.files.items(), *((p, u) for p, (_, u) in self.dep_files.items())]
        for path, units in everything:
            for unit in units.walk():
                if unit.is_procedure and unit.name and not unit.is_interface_body:
                    found.setdefault(unit.name, []).append((path, unit))
        return found

    def find_file(self, name: str | None) -> str | None:
        """The analysed file a diagnostic names (as given, relative to the cwd, or by unique basename)."""
        if not name:
            return None
        key = _norm(name)
        if key in self.files:
            return key
        matches = [p for p in self.files if os.path.basename(p) == os.path.basename(name)]
        return matches[0] if len(matches) == 1 else None


def _analyse(path: str, defines: dict[str, str] | None) -> FileUnits | None:
    try:
        return analyse(read_source(path), path, defines=defines)
    except (OSError, UnicodeDecodeError):
        return None


def _show(path: str) -> str:
    return display_path(path)


# ── deterministic diagnoses ────────────────────────────────────────────────────


@dataclass
class Diagnosis:
    """A failure FoBiS explains from facts.

    Attributes
    ----------
    kind : str
        ``missing-module``, ``undefined-reference``, ``multiple-definition``, ``wrong-runtime``,
        ``missing-library`` or ``internal-compiler-error``.
    diagnostic : Diagnostic
        The message explained.
    summary : str
        One line.
    facts : list of str
        What FoBiS found.
    advice : list of str
        What to do.
    consequences : list of Diagnostic
        Later messages that follow from this one.
    """

    kind: str
    diagnostic: Diagnostic
    summary: str
    facts: list[str] = field(default_factory=list)
    advice: list[str] = field(default_factory=list)
    consequences: list[Diagnostic] = field(default_factory=list)

    def to_dict(self) -> dict:
        """JSON-ready form (``build --json``, the MCP server)."""
        return {
            "kind": self.kind,
            "summary": self.summary,
            "diagnostic": self.diagnostic.to_dict(),
            "facts": list(self.facts),
            "advice": list(self.advice),
            "consequences": len(self.consequences),
        }


def missing_module_name(diagnostic: Diagnostic) -> str | None:
    """The module a "cannot open module file" message is about."""
    if diagnostic.tool == "intel" and diagnostic.code == "7002" and diagnostic.symbol:
        return diagnostic.symbol.lower()
    for pattern in _MISSING_MODULE:
        match = pattern.search(diagnostic.message)
        if match:
            return match.group("name").lower()
    return None


def _missing_module(diagnostic: Diagnostic, name: str, facts: BuildFacts) -> Diagnosis:
    summary = f"module {name} is not available when {diagnostic.file or 'this file'} is compiled"
    diag = Diagnosis("missing-module", diagnostic, summary)
    defining = facts.modules().get(name, [])
    if defining:
        shown = ", ".join(_show(p) for p in defining)
        compiled = [p for p in defining if facts.built is None or p in facts.built]
        if not compiled:
            diag.facts.append(
                f"{name} is defined in {shown}, which this build does not compile: "
                f"{facts.not_built_reason(defining[0])}."
            )
            diag.advice.append("add the file to the build (fobos mode `src`, `exclude`, `exclude_dirs`)")
        else:
            diag.facts.append(f"{name} is defined in {shown}, which this build compiles.")
            diag.advice.append(
                f"if {_show(compiled[0])} failed to compile, fix its errors first; otherwise rebuild with "
                "`--force-compile` (a stale or misplaced .mod file, see `mod_dir`)"
            )
        return diag
    disabled = facts.raw_modules.get(name, [])
    if disabled:
        diag.facts.append(
            f"{name} is defined in {', '.join(_show(p) for p in disabled)}, inside a preprocessor branch "
            f"that the defines of this build disable."
        )
        diag.advice.append("build with the defines that enable it (the mode's `preproc`/`cflags` `-D` flags)")
        return diag
    dependency = facts.dep_modules().get(name)
    if dependency:
        dep, path = dependency
        diag.facts.append(f"{name} is defined in {_show(path)}, part of the fetched dependency {dep}.")
        diag.advice.append(
            "re-run `fobis fetch` so that the build configuration of the dependencies "
            f"({facts.deps_dir}/.deps_config.ini) includes it"
        )
        return diag
    if name in LIBRARY_MODULES:
        library, todo = LIBRARY_MODULES[name]
        diag.facts.append(f"{name} is the module of the {library} library, not a project source.")
        diag.advice.append(todo)
        return diag
    known = {m: paths[0] for m, paths in facts.modules().items() if paths}
    known.update({m: path for m, (_dep, path) in facts.dep_modules().items()})
    close = difflib.get_close_matches(name, sorted(known), n=3, cutoff=0.8)
    if close:  # most likely a misspelt name
        shown = ", ".join(f"{m} ({_show(known[m])})" for m in close)
        diag.facts.append(f"no source defines module {name}; modules with a close name: {shown}.")
        diag.advice.append(f"if the name is misspelt, use {close[0]}")
        return diag
    unfetched = [d for d in facts.dependencies if not os.path.isdir(os.path.join(facts.deps_dir, d))]
    diag.facts.append(f"no project source defines module {name}, and it is not a known library module.")
    if unfetched:
        diag.facts.append(f"fobos declares dependencies that are not fetched yet: {', '.join(unfetched)}.")
        diag.advice.append("run `fobis fetch`")
    else:
        diag.advice.append(
            "declare the project that provides it in fobos `[dependencies]` and run `fobis fetch`, or add the "
            "directory of its .mod files to `cflags` (`-I...`)"
        )
    return diag


def _runtime_of(symbol: str) -> str | None:
    for pattern, compiler in RUNTIMES:
        if pattern.match(symbol):
            return compiler
    return None


def _library_of(raw: str, symbol: Symbol) -> tuple[str, str] | None:
    if symbol.module and symbol.module in LIBRARY_MODULES:
        return LIBRARY_MODULES[symbol.module]
    for pattern, library, todo in LIBRARY_SYMBOLS:
        if pattern.match(raw):
            return library, todo
    return None


def _module_of(unit: Unit) -> str | None:
    node = unit.parent
    while node is not None:
        if node.kind == "module":
            return node.name
        node = node.parent
    return None


def _undefined(diagnostic: Diagnostic, facts: BuildFacts) -> Diagnosis:
    raw = diagnostic.symbol or ""
    if raw in _MAIN_SYMBOLS:
        diag = Diagnosis("undefined-reference", diagnostic, "no main program is linked")
        diag.facts.append("the link has no object defining the main program.")
        diag.advice.append("build a target that is a `program`, or build a library with `--mklib static|shared`")
        return diag
    symbol = demangle(raw, set(facts.modules()) | set(facts.dep_modules()))
    library = _library_of(raw, symbol)
    if library:
        name, todo = library
        diag = Diagnosis("missing-library", diagnostic, f"{raw} belongs to the {name} library, which is not linked")
        diag.advice.append(todo)
        return diag
    where = f" (referenced from {diagnostic.context})" if diagnostic.context else ""
    diag = Diagnosis("undefined-reference", diagnostic, f"{symbol} is referenced{where} but not linked")
    candidates = [
        (path, unit)
        for path, unit in facts.procedures().get(symbol.name, [])
        if (unit.is_external if symbol.module is None else _module_of(unit) == symbol.module)
    ]
    if not candidates:
        kind = f"module procedure {symbol.module}::{symbol.name}" if symbol.module else f"procedure {symbol.name}"
        diag.facts.append(f"no project source or fetched dependency defines the {kind}.")
        diag.advice.append(
            "add the library that provides it to `libs`/`lflags`, or the source that defines it to the build"
        )
        return diag
    path, unit = candidates[0]
    diag.facts.append(f"{symbol.name} is defined in {_show(path)}:{unit.line}.")
    if path in facts.dep_files:
        dep = facts.dep_files[path][0]
        diag.facts.append(f"that file belongs to the fetched dependency {dep}.")
        diag.advice.append(
            "link the dependency: `use=fobos` in `[dependencies]` builds it as a library linked through "
            "`dependon`, `use=sources` compiles it with the project; then re-run `fobis fetch`"
        )
    elif facts.built is not None and path not in facts.built:
        diag.facts.append(f"this build does not compile that file: {facts.not_built_reason(path)}.")
        diag.advice.append("add the file to the build (fobos mode `src`, `exclude`, `exclude_dirs`)")
    elif facts.linked is not None and path not in facts.linked:
        modules = sorted(u.name for u in facts.files[path].units if u.kind == "module" and u.name)
        target = f"the target {_show(facts.target)}" if facts.target else "the target"
        reason = f"no file it links uses the module(s) {', '.join(modules)}" if modules else "it does not reach it"
        diag.facts.append(f"{target} does not link that file: {reason}.")
        diag.advice.append(
            "FoBiS links the files a program reaches through `use`, plus the files without modules: put "
            f"{symbol.name} in a module that the caller uses, or in a file without modules"
        )
    else:
        diag.facts.append("this build compiles and links that file.")
        diag.advice.append(
            "the object is stale or comes from another mode: rebuild with `--force-compile` (or `fobis clean` "
            "with the same mode first)"
        )
    return diag


def _multiple(diagnostic: Diagnostic, facts: BuildFacts) -> Diagnosis:
    raw = diagnostic.symbol or ""
    diag = Diagnosis("multiple-definition", diagnostic, f"{raw} is defined more than once in the link")
    if raw in _MAIN_SYMBOLS:
        diag.summary = "two main programs are linked together"
        diag.advice.append("build one program at a time (`--target`), or keep only one `program` in the sources")
        return diag
    symbol = demangle(raw, set(facts.modules()))
    places = [
        (p, u)
        for p, u in facts.procedures().get(symbol.name, [])
        if (u.is_external if symbol.module is None else _module_of(u) == symbol.module)
    ]
    if len(places) > 1:
        diag.facts.append(f"{symbol.name} is defined in " + ", ".join(f"{_show(p)}:{u.line}" for p, u in places) + ".")
        diag.advice.append("keep one definition: exclude one of the files, or rename one of the procedures")
    else:
        diag.advice.append("an object or library is linked twice: check `libs`, `vlibs` and `dependon`")
    return diag


def _ice(diagnostic: Diagnostic) -> Diagnosis:
    diag = Diagnosis(
        "internal-compiler-error", diagnostic, "the compiler crashed (internal compiler error): a compiler defect"
    )
    diag.facts.append(
        "an internal compiler error is a bug of the compiler: valid code or not, a compiler must not crash on it."
    )
    diag.advice += [
        "note the compiler version (`--version`); lowering the optimisation of this file often avoids it",
        "reduce the file to a small reproducer and report it to the compiler vendor",
    ]
    return diag


def classify(diagnostics: list[Diagnostic], facts: BuildFacts) -> tuple[list[Diagnosis], list[Diagnostic]]:
    """The diagnoses FoBiS can make from facts, and the errors left for the model (in order)."""
    diagnoses: list[Diagnosis] = []
    remaining: list[Diagnostic] = []
    missing_in: dict[str, Diagnosis] = {}
    errors = [d for d in diagnostics if d.is_error]
    linker = [d for d in errors if d.tool == "linker"]
    ours = _SAME_RUNTIME.get(facts.compiler, facts.compiler)
    foreign = [d for d in linker if (_runtime_of(d.symbol or "") or ours) != ours]
    if foreign:
        first = foreign[0]
        names = ", ".join(sorted({COMPILER_NAMES[_runtime_of(d.symbol or "") or ""] for d in foreign}))
        diag = Diagnosis(
            "wrong-runtime",
            first,
            f"objects compiled by {names} are linked with {COMPILER_NAMES.get(facts.compiler, facts.compiler)}",
        )
        diag.facts.append(f"the missing symbols ({first.symbol}, ...) belong to the {names} runtime library.")
        diag.advice.append(
            "the object directory holds objects of another compiler (a previous build in another mode): "
            "`fobis clean` with this mode, or give each mode its own `obj_dir`/`mod_dir`, then rebuild"
        )
        diag.consequences = [d for d in linker if d is not first]
        diagnoses.append(diag)
        errors = [d for d in errors if d.tool != "linker"]
    for diagnostic in errors:
        if diagnostic.file and diagnostic.file in missing_in:
            missing_in[diagnostic.file].consequences.append(diagnostic)
            continue
        if diagnostic.severity == "ice":
            diagnoses.append(_ice(diagnostic))
            continue
        name = missing_module_name(diagnostic)
        if name:
            diag = _missing_module(diagnostic, name, facts)
            diagnoses.append(diag)
            if diagnostic.file:
                missing_in[diagnostic.file] = diag
        elif diagnostic.tool == "linker" and diagnostic.message.startswith("undefined"):
            diagnoses.append(_undefined(diagnostic, facts))
        elif diagnostic.tool == "linker":
            diagnoses.append(_multiple(diagnostic, facts))
        else:
            remaining.append(diagnostic)
    return diagnoses, remaining


def render_diagnoses(diagnoses: list[Diagnosis]) -> str:
    """The deterministic diagnoses as text."""
    lines: list[str] = []
    for diag in diagnoses:
        where = "link" if diag.diagnostic.tool == "linker" else diag.diagnostic.where
        lines.append(f"{where}: {diag.summary}")
        lines += [f"  - {fact}" for fact in diag.facts]
        lines += [f"  fix: {todo}" for todo in diag.advice]
        if diag.consequences:
            lines.append(f"  ({len(diag.consequences)} later error(s) follow from this one)")
        lines.append("")
    return "\n".join(lines).rstrip()


# ── grounded explanation ───────────────────────────────────────────────────────


def _code_span(lines: list[str], line: int, radius: int = 6) -> tuple[str, int, int]:
    first, last = max(1, line - radius), min(len(lines), line + radius)
    width = len(str(last))
    text = "\n".join(f"{n:<{width}} {'>' if n == line else '|'} {lines[n - 1]}" for n in range(first, last + 1))
    return text, first, last


def _clip(text: str, limit: int) -> str:
    """*text* cut at a line boundary before *limit* characters (small models have small contexts)."""
    if len(text) <= limit:
        return text
    cut = text.rfind("\n", 0, limit)
    return text[: cut if cut > 0 else limit].rstrip() + "\n[...]"


def _enclosing(units: FileUnits, line: int) -> Unit | None:
    best = None
    for unit in units.walk():
        if unit.kind in ("interface", "fragment") or not unit.end_line:
            continue
        if unit.line <= line <= unit.end_line and (best is None or unit.line >= best.line):
            best = unit
    return best


def _specification(unit: Unit, lines: list[str]) -> str:
    """Header, ``use`` statements and declarations of *unit*, as written."""
    numbers = sorted({u.line for u in unit.uses} | {d.line for d in unit.decls.values() if d.line})
    out = [unit.header.text.strip()] if unit.header is not None else []
    out += [lines[n - 1].strip() for n in numbers if 0 < n <= len(lines)]
    return "\n".join(out)


def build_bundle(
    diagnostic: Diagnostic,
    facts: BuildFacts,
    kb: KnowledgeBase | None = None,
    k: int = 2,
    max_facts: int = 5,
    max_chars: int = 1500,
    min_score: float = 10.0,
) -> ContextBundle:
    """What the model gets to explain *diagnostic*: message, build settings and the numbered sources.

    The project facts come first (code span, enclosing declarations, interfaces of the procedures named on the
    error line, at most *max_facts* sources); then up to *k* knowledge-pack sections found by lexical search on
    the message, each cut to *max_chars*. Sections scoring below *min_score* are left out: compiler messages
    share few words with the standard, and a small model is easily led by an unrelated section.
    """
    build = [f"compiler: {COMPILER_NAMES.get(facts.compiler, facts.compiler)} ({facts.compiler})"]
    if facts.mode:
        build.append(f"fobos mode: {facts.mode}")
    if facts.cflags.strip():
        build.append(f"compile flags: {facts.cflags.strip()}")
    sections = [("Compiler message", diagnostic.text or diagnostic.message), ("Build", "\n".join(build))]
    sources: list[Source] = []
    path = facts.find_file(diagnostic.file)
    error_line = ""
    if path and diagnostic.line:
        shown = _show(path)
        lines = read_source(path).splitlines()
        span, first, last = _code_span(lines, diagnostic.line)
        sources.append(Source(f"code:{shown}:{first}-{last}", f"{shown} lines {first}-{last}", span))
        error_line = lines[diagnostic.line - 1] if diagnostic.line <= len(lines) else ""
        unit = _enclosing(facts.files[path], diagnostic.line)
        if unit is not None and unit.name:
            sources.append(
                Source(
                    f"fact:{shown}#{unit.name}",
                    f"declarations of {unit.kind} {unit.name} ({shown}:{unit.line})",
                    _specification(unit, lines),
                )
            )
        procedures = facts.procedures()
        for name in dict.fromkeys(w.lower() for w in _IDENTIFIER.findall(error_line)):
            if len(sources) >= max_facts:
                break
            if unit is not None and name == unit.name:
                continue
            for proc_path, proc in procedures.get(name, [])[:1]:
                proc_shown = _show(proc_path)
                owner = _module_of(proc)
                title = f"interface of {proc.kind} {proc.name}" + (f" (module {owner})" if owner else "")
                sources.append(
                    Source(
                        f"fact:{proc_shown}#{proc.name}",
                        f"{title}, {proc_shown}:{proc.line}",
                        _specification(proc, read_source(proc_path).splitlines()),
                    )
                )
    if kb is not None:
        query = re.sub(r"\bat \(\d\)", " ", diagnostic.message)
        packs = route_packs(f"{query} {error_line}", kb.packs) or [
            p for p in ("fortran-std", "hpc-practice") if p in kb.packs
        ]
        for result in kb.search(query, k=k, packs=packs):
            if result.score < min_score:
                continue
            chunk = result.chunk
            where = kb.packs[chunk.pack].meta.get("title", chunk.pack)
            sources.append(Source(chunk.id, f"{chunk.heading} - {where}", _clip(chunk.text, max_chars)))
    return ContextBundle(sections=sections, sources=sources)


def explain(bundle: ContextBundle, provider: Provider, seed: int = 0) -> Grounded:
    """Ask *provider* for the cited cause and fix of the error in *bundle*."""
    completion = provider.chat(
        messages(bundle.render(), system=load_prompt("explain")),
        schema=claims_schema(bundle.labels, kinds=KINDS),
        temperature=0.0,
        seed=seed,
        max_tokens=ANSWER_TOKENS,
    )
    return check_claims(completion.text, bundle)
