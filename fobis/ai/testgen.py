"""testgen.py — ``fobis testgen``: a test program for a module's public API, kept only if it compiles and runs.

Deterministic first. The public API of the module (`fobis.ai.impact.module_api`) gives the procedures to test;
for each one (a generic is tested through its name, once per specific procedure) a **skeleton** test subroutine
declares local variables mirroring the dummy arguments (intent/optional/value dropped, assumed shapes and
lengths made allocatable, ``class(t)`` declared as ``type(t)``) and calls the procedure with keyword arguments.
The skeleton is built with FoBiS in a **scratch copy** of the project (the user's tree, build directory and test
directory are never written); a case whose declarations do not compile is dropped, with the reason. Without a
model, the compiling skeleton is the result (``--skeleton``).

The model then fills the skeleton: inputs, expected values computed from the procedure bodies, checks. Its
program is built and run in the same scratch copy; build errors, a crash or a failing check are sent back, up to
``retries`` times. A program is **kept only when** it builds, runs with exit status 0 within the timeout, uses the
module, calls at least one of its public procedures and contains at least one check that can fail (``error
stop``, a non-zero ``stop``, or an increment of a failure counter) inside a test procedure. ``--apply`` writes it
to the project's test directory (fobos ``[test] test_dir``), never over an existing file.
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

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..analysis import FileUnits, Unit, read_source
from ..analysis.units import Decl
from ..lint.engine import analyse
from ..llm.provider import bounded, messages
from .diagnostics import parse_diagnostics
from .grounding import ContextBundle, Source, load_prompt
from .impact import Entity, module_api

if TYPE_CHECKING:
    from ..llm.provider import Provider

MAX_RETRIES = 3
BODY_LINES = 80  # lines of a procedure body sent to the model
TAIL_LINES = 30  # lines of a failing run's output sent back
FIXED_LENGTH = 256  # length of a local passed to an allocatable/pointer character(*) dummy

_MODULE_RE = re.compile(r"^\s*module\s+(?!procedure\b|subroutine\b|function\b)(\w+)\s*(?:!.*)?$", re.I | re.M)
_KEEP_ATTRS = ("allocatable", "pointer", "target")
_CHECK_RE = re.compile(r"^(?:if\s*\(.*\)\s*)?(?:error\s+stop\b|stop\s+[1-9]|(\w*(?:fail|err)\w*)\s*=\s*\1\s*\+)")
_FENCE_RE = re.compile(r"```(?:fortran|f90)?\s*\n(.*?)```", re.S | re.I)
_ERROR_LINE = re.compile(r"line (\d+): (.*)")
_PROGRAM_RE = re.compile(r"^\s*program\s+\w+", re.I | re.M)
_BUILD_LINE = re.compile(r"^\W*Building ")
NOT_A_PROGRAM = (
    "The `fortran_source_code` field must hold the WHOLE Fortran program, from `program {name}` to `end program {name}`: start "
    "from the skeleton and complete it. Return the JSON object again."
)
_PREFIX_WORDS = ("pure", "impure", "elemental", "recursive", "non_recursive", "module", "simple")


# ── the module ─────────────────────────────────────────────────────────────────


@dataclass
class Target:
    """The module under test: where it is, its analysed units and its public API."""

    name: str
    path: str
    units: FileUnits
    module: Unit
    lines: list[str]

    @property
    def api(self) -> dict[str, Entity]:
        return module_api(self.units).get(self.name, {})


def find_module(name: str, files: list[str], defines: dict[str, str] | None = None) -> Target | None:
    """The module *name* among *files* (a regex finds the file, then only that file is analysed)."""
    name = name.lower()
    for path in files:
        text = read_source(path)
        if not any(m.group(1).lower() == name for m in _MODULE_RE.finditer(text)):
            continue
        units = analyse(text, path, defines=defines)
        module = next((u for u in units.units if u.kind == "module" and u.name == name), None)
        if module is not None:
            return Target(name, path, units, module, text.splitlines())
    return None


# ── skeleton ───────────────────────────────────────────────────────────────────


def _split_top(text: str) -> list[str]:
    """*text* split at the commas outside parentheses."""
    parts, depth, current = [], 0, ""
    for c in text:
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        if c == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += c
    parts.append(current.strip())
    return [p for p in parts if p]


def _character_spec(type_spec: str, movable: bool = False) -> tuple[str, bool]:
    """A local character type for a dummy's: (spec, deferred length). A length that is not a literal is deferred,
    except the assumed or computed length (``*``, ``len(s)``) of an allocatable or pointer (*movable*) dummy: its
    actual argument must have a length that is not deferred, so it gets a fixed one."""
    match = re.match(r"character\s*(?:\*\s*(\(\s*\*\s*\)|\d+))?\s*(?:\((?P<sel>.*)\))?\s*$", type_spec, re.I)
    if not match:
        return type_spec, False
    star = match.group(1)
    length, kind = (star.strip("() ") if star else None), None
    for i, part in enumerate(_split_top(match.group("sel") or "")):
        key, _, value = part.partition("=")
        if value and key.strip().lower() == "kind":
            kind = value.strip()
        elif value and key.strip().lower() == "len":
            length = value.strip()
        elif i == 0:
            length = part
        else:
            kind = part
    if movable and length is not None and length != ":" and not length.isdigit():
        length = str(FIXED_LENGTH)
    deferred = length is not None and not length.isdigit()
    selector = [f"len={':' if deferred else length}"] if length is not None else []
    selector += [f"kind={kind}"] if kind else []
    return (f"character({', '.join(selector)})" if selector else "character"), deferred


def local_declaration(decl: Decl | None, local: str) -> tuple[str | None, str]:
    """The declaration of a local variable *local* that can be passed where *decl* (a dummy argument) is expected.

    Returns (declaration, '') or (None, reason) when no local variable can stand for it.
    """
    name = decl.name if decl is not None else local
    if decl is None or not decl.type_spec:
        return None, f"{name} is implicitly typed"
    spec = " ".join(decl.type_spec.split())
    low = spec.lower()
    if low.startswith("procedure") or "external" in decl.attrs:
        return None, f"{name} is a procedure argument"
    if re.match(r"(class|type)\s*\(\s*\*\s*\)", low):
        return None, f"{name} is unlimited polymorphic"
    attrs = [a for a in _KEEP_ATTRS if a in decl.attrs]
    if low.startswith("class") and not {"allocatable", "pointer"} & set(attrs):
        spec = "type" + spec[5:]
    deferred = False
    if low.startswith("character"):
        spec, deferred = _character_spec(spec, movable=bool({"allocatable", "pointer"} & set(attrs)))
    dims = decl.dims
    if dims:
        if dims.strip() == "..":
            return None, f"{name} is assumed-rank"
        bounds = _split_top(dims)
        movable = deferred or {"allocatable", "pointer"} & set(attrs)
        if movable or not all(re.fullmatch(r"\d+(\s*:\s*\d+)?", b) for b in bounds):
            dims = ",".join(":" for _ in bounds)  # an allocatable (or pointer) array has a deferred shape
            deferred = True
    if deferred and not {"allocatable", "pointer"} & set(attrs):
        attrs.append("allocatable")
    head = ", ".join([spec, *attrs])
    return f"{head} :: {local}{f'({dims})' if dims else ''}", ""


def _function_type(unit: Unit) -> str | None:
    """The type given in a function's prefix (``real(rk) pure function f(x)``)."""
    if unit.header is None:
        return None
    words = re.split(r"\bfunction\b", unit.header.text, maxsplit=1, flags=re.I)[0]
    for word in _PREFIX_WORDS:
        words = re.sub(rf"\b{word}\b", " ", words, flags=re.I)
    words = " ".join(words.split())
    return words or None


def wrap(statement: str, width: int = 100) -> list[str]:
    """*statement* as free-form lines of at most about *width* characters, continued with ``&`` after commas outside
    character literals (the default line length of gfortran is 132, a hard error with ``-Werror``)."""
    if len(statement) <= width:
        return [statement]
    lines, current, quote = [], "", None
    for i, c in enumerate(statement):
        current += c
        if quote:
            quote = None if c == quote else quote
        elif c in "'\"":
            quote = c
        elif c == "," and len(current) > width * 0.6 and i + 1 < len(statement):
            lines.append(current + " &")
            current = ""
    lines.append(current)
    return [lines[0], *(f"  {line.strip()}" for line in lines[1:])]


@dataclass
class Case:
    """One test procedure of the skeleton: the public name called and the specific procedure it resolves to.

    A type-bound procedure is called on an object of its *owner* type, the object being the *passed* dummy
    argument ('' with ``nopass``).
    """

    name: str
    specific: Unit
    via: str = ""  # the specific procedure's name when called through a generic or a binding
    owner: str = ""  # the derived type of a type-bound procedure
    passed: str | None = None  # the passed-object dummy argument of a type-bound procedure ('' for nopass)
    lines: list[str] = field(default_factory=list)
    skipped: str = ""  # why no test procedure is written

    @property
    def label(self) -> str:
        name = f"{self.owner}%{self.name}" if self.owner else self.name
        return f"{name} ({self.via})" if self.via and self.via != self.name else name

    @property
    def subroutine(self) -> str:
        return ("test_" + (f"{self.owner}_" if self.owner else "") + (self.via or self.name))[:63]


def _case_lines(case: Case, taken: set[str]) -> None:
    unit = case.specific
    decls, actuals = [], []
    obj = ""
    if case.owner and not case.passed:  # nopass: any object of the type will do
        obj = "obj_"
        decls.append(f"type({case.owner}) :: {obj}")
    for arg in unit.args:
        local = arg + "_" if arg in taken else arg
        text, reason = local_declaration(unit.decls.get(arg), local)
        if text is None:
            case.skipped = reason
            return
        decls.append(text)
        if case.owner and arg == case.passed:
            obj = local
        else:
            actuals.append(f"{arg}={local}")
    call = f"{f'{obj}%' if obj else ''}{case.name}({', '.join(actuals)})"
    if unit.kind == "function":
        result = unit.result or unit.name
        local = "res_" if "res" in unit.args else "res"
        decl = unit.decls.get(result)
        if decl is None and (prefix := _function_type(unit)) is not None:
            decl = Decl(result, prefix)
        text, reason = local_declaration(decl, local)
        if text is None:
            case.skipped = f"the function result: {reason}"
            return
        decls.append(text)
        statement = f"{local} = {call}"
    else:
        statement = f"call {call}"
    case.lines = [
        f"subroutine {case.subroutine}()",
        *(f"  {line}" for d in decls for line in wrap(d)),
        "  ! TODO: give the inputs values, then check the outputs against expected values",
        *(f"  {line}" for line in wrap(statement)),
        f"end subroutine {case.subroutine}",
    ]


_BINDING_RE = re.compile(r"^(procedure|generic)\s*(?:\([^)]*\))?\s*(?P<attrs>(?:,[^:]*)?)::\s*(?P<rest>.*)$")
_PASS_RE = re.compile(r"\bpass\s*\(\s*(\w+)\s*\)")


@dataclass(frozen=True)
class Binding:
    """A type-bound procedure: its name, the specific procedure, how the object is passed, its access."""

    name: str
    specific: str
    passed: str | None  # the dummy argument name given by pass(arg); None = the first one; '' = nopass
    public: bool


def type_bindings(body: str) -> tuple[dict[str, Binding], dict[str, tuple[list[str], bool]]]:
    """The bindings of a derived type definition (`fobis.ai.impact._types` body): procedure bindings by name,
    and generic bindings: name -> (binding names, public). Deferred bindings are left out."""
    bindings: dict[str, Binding] = {}
    generics: dict[str, tuple[list[str], bool]] = {}
    lines = body.splitlines()
    if "contains" not in lines:
        return bindings, generics
    default_public = True
    for line in lines[lines.index("contains") + 1 :]:
        if line in ("private", "public"):
            default_public = line == "public"
            continue
        match = _BINDING_RE.match(line)
        if not match:
            continue
        attrs = match.group("attrs")
        if re.search(r"\bdeferred\b", attrs):
            continue
        public = "public" in attrs or (default_public and "private" not in attrs)
        rest = match.group("rest")
        if match.group(1) == "generic":
            name, _, targets = rest.partition("=>")
            if re.fullmatch(r"\w+", name.strip()):
                names = [t for t in (x.strip() for x in _split_top(targets)) if re.fullmatch(r"\w+", t)]
                generics[name.strip()] = (names, public)
            continue
        pass_match = _PASS_RE.search(attrs)
        passed = "" if re.search(r"\bnopass\b", attrs) else (pass_match.group(1) if pass_match else None)
        for item in _split_top(rest):
            name, _, specific = item.partition("=>")
            name, specific = name.strip(), (specific.strip() or name.strip())
            if re.fullmatch(r"\w+", name) and re.fullmatch(r"\w+", specific):
                bindings[name] = Binding(name, specific, passed, public)
    return bindings, generics


def _binding_cases(target: Target, by_name: dict[str, Unit], wanted: set[str] | None) -> list[Case]:
    """A case per public binding of each public, non-abstract type (generic bindings through their name)."""
    from .impact import _types

    api = target.api
    cases: list[Case] = []
    for type_name, (body, attrs, _) in sorted(_types(target.module).items()):
        if type_name not in api or "abstract" in attrs:
            continue
        bindings, generics = type_bindings(body)

        def case(called: str, binding: Binding, type_name: str = type_name) -> Case | None:
            unit = by_name.get(binding.specific)
            if unit is None:
                return None
            passed = binding.passed
            if passed is None:
                passed = unit.args[0] if unit.args else ""
            return Case(called, unit, via=binding.specific, owner=type_name, passed=passed)

        through_generic: set[str] = set()
        for name, (names, public) in sorted(generics.items()):
            if not public or (wanted and not {name, f"{type_name}%{name}"} & wanted):
                continue
            for binding_name in names:
                if binding_name in bindings and (found := case(name, bindings[binding_name])):
                    cases.append(found)
                    through_generic.add(binding_name)
        for name, binding in sorted(bindings.items()):
            if binding.public and name not in through_generic:
                if wanted and not {name, f"{type_name}%{name}"} & wanted:
                    continue
                if found := case(name, binding):
                    cases.append(found)
    return cases


def plan_cases(target: Target, procedures: list[str] | None = None, limit: int | None = None) -> list[Case]:
    """The cases to test: public procedures, each specific procedure of a public generic (through the generic),
    and the public type-bound procedures of the public types (called on an object).

    *procedures* restricts them to these public names (procedure, generic or binding names, or ``type%binding``);
    beyond *limit* cases the rest are skipped (a model's context is small).
    """
    api = target.api
    by_name = {c.name: c for c in target.module.children if c.is_procedure and c.name}
    wanted = {p.lower() for p in procedures} if procedures else None
    cases: list[Case] = []
    through_generic: set[str] = set()
    for name, entity in sorted(api.items()):
        if entity.kind != "generic" or not re.fullmatch(r"\w+", name) or (wanted and name not in wanted):
            continue
        for specific in entity.signature.removeprefix("generic: ").split(", "):
            if specific in by_name:
                cases.append(Case(name, by_name[specific], via=specific))
                through_generic.add(specific)
    for name, entity in sorted(api.items()):
        if entity.kind == "procedure" and name not in through_generic and (not wanted or name in wanted):
            cases.append(Case(name, by_name[name]))
    cases += _binding_cases(target, by_name, wanted)
    taken = set(api) | {target.name, "failures", "obj_"}
    for case in cases:
        _case_lines(case, taken)
    if limit is not None:
        for case in [c for c in cases if not c.skipped][limit:]:
            case.skipped = f"over the limit of {limit} (--max, --procedure)"
    return cases


@dataclass
class Skeleton:
    """A test program: its text, and the line spans of each case (its call in the main program and its procedure)."""

    program: str
    text: str
    cases: list[Case]
    spans: dict[str, list[tuple[int, int]]]

    @property
    def active(self) -> list[Case]:
        return [c for c in self.cases if not c.skipped]


def program_name(module: str) -> str:
    return f"test_{module}"[:63]


def skeleton(target: Target, cases: list[Case]) -> Skeleton:
    """The test program calling every case that could be declared.

    The module's own ``use`` statements are repeated: they give the kinds and types of the dummy arguments.
    """
    program = program_name(target.name)
    active = [c for c in cases if not c.skipped]
    lines = [
        f"! Test of module {target.name}: generated by fobis testgen; review it before committing.",
        f"program {program}",
        f"  use {target.name}",
        *(f"  {line}" for u in target.module.uses for line in wrap(" ".join(u.statement.text.split()))),
        "  implicit none",
        "  integer :: failures = 0",
        "",
    ]
    spans: dict[str, list[tuple[int, int]]] = {}
    for case in active:
        lines.append(f"  call {case.subroutine}()")
        spans.setdefault(case.subroutine, []).append((len(lines), len(lines)))
    lines += [f"  ! not tested: {c.label}: {c.skipped}" for c in cases if c.skipped]
    lines += [
        "  if (failures > 0) then",
        "    print '(a,i0,a)', 'FAILED: ', failures, ' check(s)'",
        "    error stop 1",
        "  end if",
        f"  print '(a)', '{program}: all checks passed'",
        "contains",
    ]
    for case in active:
        lines.append("")
        first = len(lines) + 1
        lines += [f"  {line}" for line in case.lines]
        spans.setdefault(case.subroutine, []).append((first, len(lines)))
    lines.append(f"end program {program}")
    return Skeleton(program, "\n".join(lines) + "\n", cases, spans)


# ── scratch build ──────────────────────────────────────────────────────────────


@dataclass
class Attempt:
    """The outcome of building and running a test program."""

    stage: str  # "build", "run" or "ok"
    output: str = ""
    errors: list[str] = field(default_factory=list)  # build: "line N: message" of the test program
    exit_code: int | None = None
    project_errors: bool = False  # the build failed outside the test program

    @property
    def ok(self) -> bool:
        return self.stage == "ok"

    def error_lines(self) -> dict[int, str]:
        """Line of the test program -> first compiler message on it."""
        found: dict[int, str] = {}
        for error in self.errors:
            if match := _ERROR_LINE.match(error):
                found.setdefault(int(match.group(1)), match.group(2))
        return found


class Sandbox:
    """A scratch copy of the project in which test programs are built and run with FoBiS.

    The working copy is copied (tracked and untracked files, ignored ones excluded, see
    `fobis.Ecosystem.copy_working_copy`), then the fetched dependencies (without their ``.git``): building them
    never touches the user's copies. Objects stay
    in the copy between attempts, so only the test program is recompiled. A program is written in *source_dir*
    (relative to the root), which the build must scan.
    """

    def __init__(
        self,
        root: str,
        source_dir: str = ".",
        build_args: list[str] | None = None,
        deps_dir: str = ".fobis_deps",
        timeout: float = 60.0,
        run=subprocess.run,
    ):
        self.root = os.path.abspath(root)
        self.source_dir = source_dir
        self.build_args = build_args or []
        self.deps_dir = deps_dir
        self.timeout = timeout
        self.run = run
        self._tmp: tempfile.TemporaryDirectory | None = None
        self.stage = ""

    def __enter__(self) -> Sandbox:
        from ..Ecosystem import copy_working_copy

        self._tmp = tempfile.TemporaryDirectory(prefix="fobis-testgen-")
        self.stage = os.path.join(self._tmp.name, "project")
        copy_working_copy(self.root, self.stage)
        deps = os.path.join(self.root, self.deps_dir)
        if os.path.isdir(deps):  # copied, not linked: the source scan does not follow symbolic links
            shutil.copytree(
                deps,
                os.path.join(self.stage, self.deps_dir),
                symlinks=True,
                ignore=shutil.ignore_patterns(".git"),
                dirs_exist_ok=True,  # partly tracked, e.g. src/third_party/CMakeLists.txt
            )
        return self

    def __exit__(self, *exc) -> None:
        if self._tmp is not None:
            self._tmp.cleanup()

    def attempt(self, name: str, text: str, run: bool = True) -> Attempt:
        """Build the program *text* as ``<source_dir>/<name>.f90`` with ``fobis build --target`` and run it.

        *source_dir* must be scanned by the build: a target outside the mode's sources is not built. Without
        *run* the program is only built (stage ``ok`` when it builds).
        """
        from ..mcp_server import fobis_command

        source = os.path.normpath(os.path.join(self.source_dir, f"{name}.f90"))
        path = os.path.join(self.stage, source)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        binary = os.path.join(self._tmp.name, "bin", name)
        os.makedirs(os.path.dirname(binary), exist_ok=True)
        if os.path.exists(binary):
            os.remove(binary)
        command = [*fobis_command(), "build", "--target", source, "--output", binary, *self.build_args]
        try:
            done = self.run(command, cwd=self.stage, capture_output=True, text=True, timeout=1800)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return Attempt("build", f"fobis build could not run: {exc}", project_errors=True)
        output = done.stdout + done.stderr
        if done.returncode != 0 or not os.path.isfile(binary):
            errors, elsewhere = [], False
            for d in parse_diagnostics(output):
                if not d.is_error:
                    continue
                if d.file and os.path.basename(d.file) == os.path.basename(source):
                    error = f"line {d.line}: {d.message}" if d.line else d.message
                    if error not in errors:
                        errors.append(error)
                elif d.tool != "linker":
                    elsewhere = True
            if not errors and not elsewhere:  # nothing parsed: give the tail of the build, not FoBiS's banner
                lines = output.strip().splitlines()
                start = next((i for i, line in enumerate(lines) if _BUILD_LINE.match(line)), 0)
                errors = lines[start:][-TAIL_LINES:]
            return Attempt("build", output, errors, project_errors=elsewhere and not errors)
        if not run:
            return Attempt("ok", output)
        try:
            ran = self.run([binary], cwd=self.stage, capture_output=True, text=True, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            return Attempt("run", f"TIMEOUT after {self.timeout:g} s")
        except OSError as exc:
            return Attempt("run", str(exc))
        output = (ran.stdout + ran.stderr).strip()
        return Attempt("ok" if ran.returncode == 0 else "run", output, exit_code=ran.returncode)


def checked_skeleton(target: Target, cases: list[Case], sandbox: Sandbox, rounds: int = 3) -> tuple[Skeleton, Attempt]:
    """The skeleton, built (not run: its inputs have no values) in *sandbox*. A case whose declarations or call do not compile is dropped, with the
    compiler's message as the reason, and the rest is built again."""
    skel = skeleton(target, cases)
    attempt = sandbox.attempt(skel.program, skel.text, run=False)
    for _ in range(rounds):
        errors = attempt.error_lines() if attempt.stage == "build" and not attempt.project_errors else {}
        dropped = False
        for case in skel.active:
            hits = [errors[n] for a, b in skel.spans[case.subroutine] for n in sorted(errors) if a <= n <= b]
            if hits:
                case.skipped, dropped = f"the generated call does not compile: {hits[0]}", True
        if not dropped:
            break
        skel = skeleton(target, cases)
        attempt = sandbox.attempt(skel.program, skel.text, run=False)
    return skel, attempt


# ── acceptance ─────────────────────────────────────────────────────────────────


@dataclass
class Coverage:
    """What a test program exercises: whether it uses the module, the public names it calls, the checks found."""

    uses_module: bool
    called: list[str]
    checks: int

    @property
    def problems(self) -> list[str]:
        found = []
        if not self.uses_module:
            found.append("the program does not use the module under test")
        if not self.called:
            found.append("the program calls none of the module's public procedures")
        if not self.checks:
            found.append(
                "the program checks nothing: no 'error stop', non-zero 'stop' or failure counter increment "
                "inside a test procedure"
            )
        return found


def coverage(program: str, module: str, public: set[str]) -> Coverage:
    """Inspect the test *program*: does it use *module*, which *public* names does it call, how many checks."""
    units = analyse(program, "test.f90")
    uses = any(u.module == module for unit in units.walk() for u in unit.uses)
    called: set[str] = set()
    checks = 0
    for unit in units.walk():
        for stmt in unit.statements:
            words = re.findall(r"\b(\w+)\s*\(", stmt.masked) + re.findall(r"%\s*(\w+)", stmt.masked)
            words += re.findall(r"^call\s+(\w+)\s*$", stmt.masked)
            called |= {w for w in words if w in public}
            if unit.kind != "program" and _CHECK_RE.match(" ".join(stmt.masked.split())):
                checks += 1
    return Coverage(uses, sorted(called), checks)


# ── the model ──────────────────────────────────────────────────────────────────


TESTGEN_SCHEMA = bounded(
    {
        "type": "object",
        "properties": {
            "fortran_source_code": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": ["fortran_source_code", "notes"],
        "additionalProperties": False,
    },
    free=("fortran_source_code",),
)
"""The field is not called ``program``: measured with coder-0.5b on the same bundle, ``program`` and ``source``
got the program's NAME back, ``fortran_source_code`` the program."""
PROGRAM_TOKENS = 6144  # cap of an answer: the program is code, unbounded by the schema


def _body(target: Target, unit: Unit) -> str:
    first, last = unit.line, unit.end_line or unit.line
    lines = target.lines[first - 1 : last]
    if len(lines) > BODY_LINES:
        lines = [*lines[:BODY_LINES], f"... ({len(lines) - BODY_LINES} more lines)"]
    return "\n".join(f"{first + i:5d} | {line}" for i, line in enumerate(lines))


def example_test(test_dir: str, module: str, limit: int = 60) -> tuple[str, str] | None:
    """An existing test program of the project, preferably a short one using *module*: (path, text clipped)."""
    from ..TestRunner import discover_tests

    found = []
    for test in discover_tests(test_dir):
        text = read_source(test["source"])
        uses = bool(re.search(rf"^\s*use\s+{re.escape(module)}\b", text, re.I | re.M))
        found.append((not uses, len(text), test["source"], text))
    if not found:
        return None
    _, _, path, text = min(found)
    lines = text.splitlines()
    clipped = lines[:limit] + ([f"... ({len(lines) - limit} more lines)"] if len(lines) > limit else [])
    return path, "\n".join(clipped)


def build_bundle(target: Target, skel: Skeleton, example: tuple[str, str] | None = None) -> ContextBundle:
    """The model's input: the skeleton to complete, the module's public API (the tested procedures and generics,
    the types, variables and constants), the tested procedures' code and an existing test of the project."""
    api = target.api
    where = os.path.relpath(target.path)
    bundle = ContextBundle()
    bundle.sections.append(("Module under test", f"module {target.name} ({where})"))
    bundle.sections.append(("Skeleton to complete (it compiles as it is)", skel.text))
    tested = {c.name for c in skel.active} | {c.via for c in skel.active} | {c.owner for c in skel.active}
    listed = "\n\n".join(
        f"{e.kind} {name}:\n{e.signature}"
        for name, e in sorted(api.items())
        if name in tested or e.kind in ("type", "parameter", "variable")
    )
    bundle.sources.append(Source(f"api:{target.name}", f"public API of module {target.name}", listed or "(empty)"))
    seen = set()
    for case in skel.active:
        unit = case.specific
        if unit.name not in seen:
            seen.add(unit.name)
            bundle.sources.append(Source(f"code:{where}:{unit.line}", f"{unit.kind} {unit.name}", _body(target, unit)))
    if example is not None:
        path, text = example
        bundle.sources.append(Source(f"test:{os.path.relpath(path)}", "an existing test of the project", text))
    return bundle


def parse_program(raw: str) -> tuple[str | None, str]:
    """The program and the notes of a model answer (JSON; a fenced code block is accepted as a fallback)."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        data = None
    code = data.get("fortran_source_code", data.get("program")) if isinstance(data, dict) else None
    if isinstance(code, str):
        program, notes = code, str(data.get("notes", ""))
    else:
        match = _FENCE_RE.search(raw or "")
        if not match:
            return None, ""
        program, notes = match.group(1), ""
    fenced = _FENCE_RE.search(program)
    program = (fenced.group(1) if fenced else program).strip("\n") + "\n"
    return (program if program.strip() else None), notes


def feedback(attempt: Attempt, problems: list[str] | None = None) -> str:
    """What to tell the model about a rejected program."""
    if problems:
        return "The program builds and runs but is not a test yet:\n- " + "\n- ".join(problems)
    if attempt.stage == "build":
        return "The program does not compile:\n" + "\n".join(attempt.errors[:20])
    tail = "\n".join(attempt.output.splitlines()[-TAIL_LINES:])
    if attempt.exit_code is None:
        return f"The program did not finish:\n{tail}"
    return (
        f"The program stopped with exit status {attempt.exit_code}. Output:\n{tail}\n\n"
        "If a check failed, recompute its expected value from the procedure's code: change the expectation only "
        "when it is wrong, never remove a check to make the program pass. A crash means an input is invalid "
        "(an unallocated array, an index out of range)."
    )


def _reason(attempt: Attempt, problems: list[str]) -> str:
    if problems:
        return problems[0]
    if attempt.stage == "build":
        return "it does not compile: " + (attempt.errors[0] if attempt.errors else "see the build output")
    if attempt.exit_code is None:
        return "it did not finish: " + (attempt.output.splitlines() or [""])[-1]
    return f"it stopped with exit status {attempt.exit_code}"


@dataclass
class Generated:
    """The result of the generation loop."""

    program: str | None  # the accepted program; None when nothing was accepted
    attempts: int = 0
    notes: str = ""
    last: str | None = None  # the last program the model wrote
    reason: str = ""  # why the last program was rejected
    coverage: Coverage | None = None
    output: str = ""  # the last run's output (or the build output)


def generate(
    target: Target,
    skel: Skeleton,
    sandbox: Sandbox,
    provider: Provider,
    bundle: ContextBundle,
    retries: int = MAX_RETRIES,
    on_status=None,
    seed: int = 0,
) -> Generated:
    """Ask the model to complete *skel*; build, run and inspect its program, and send the failure back, at most
    *retries* times. The conversation is kept, so the model sees its previous attempts."""
    public = set(target.api) | {c.name for c in skel.cases}
    chat = messages(bundle.render(), system=load_prompt("testgen"))
    result = Generated(None)
    for number in range(retries + 1):
        if on_status:
            on_status(f"[llm] {target.name}: attempt {number + 1}/{retries + 1}")
        answer = provider.chat(list(chat), schema=TESTGEN_SCHEMA, temperature=0.0, seed=seed, max_tokens=PROGRAM_TOKENS)
        result.attempts = number + 1
        chat.append({"role": "assistant", "content": answer.text})
        program, notes = parse_program(answer.text)
        if program is None:
            result.reason = "the answer holds no program"
            chat.append({"role": "user", "content": "Answer with the JSON object holding the whole program."})
            continue
        result.last, result.notes = program, notes
        if not _PROGRAM_RE.search(program):  # FoBiS treats such a file as a library and hides its errors
            result.reason = "the answer is not a program (no program statement)"
            chat.append({"role": "user", "content": NOT_A_PROGRAM.format(name=skel.program)})
            continue
        attempt = sandbox.attempt(skel.program, program)
        result.output = attempt.output
        if attempt.project_errors:
            result.reason = "the project itself does not build in the scratch copy"
            return result
        found = coverage(program, target.name, public)
        problems = found.problems if attempt.ok else []
        if attempt.ok and not problems:
            result.program, result.reason, result.coverage = program, "", found
            return result
        result.reason = _reason(attempt, problems)
        chat.append(
            {"role": "user", "content": feedback(attempt, problems) + "\n\nReturn the whole corrected program."}
        )
    return result


# ── report ─────────────────────────────────────────────────────────────────────


def render_cases(skel: Skeleton) -> list[str]:
    """One line per case: tested, or skipped with the reason."""
    lines = [f"  test {c.label}" for c in skel.active]
    lines += [f"  skipped {c.label}: {c.skipped}" for c in skel.cases if c.skipped]
    return lines
