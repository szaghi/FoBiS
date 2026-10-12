"""units.py — program units and their specification facts, from lexed statements.

Builds the tree of scoping units (module, submodule, program, subroutine, function, separate module procedure,
block data, interface block with its interface bodies) and records, per unit, the facts the rules need:
dummy arguments, declarations with attributes and initialisers, ``use`` statements, ``implicit`` statements,
the default accessibility statement and the unit's own statements.

Like the lexer it is tolerant: unknown statements are kept as plain statements, an unmatched ``end`` is ignored,
units left open at end of file are closed there.
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

import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from .lexer import SourceFile, Statement

PROCEDURE_KINDS = frozenset(("subroutine", "function", "module procedure"))

_TYPE_KEYWORD = r"(?:integer|real|complex|logical|character|double\s*precision|double\s*complex)"
_PREFIX_RE = re.compile(
    r"\s*(?:(?:pure|impure|elemental|recursive|non_recursive|module|simple)\b"
    r"|(?:type|class)\s*\((?:[^()]|\([^()]*\))*\)"
    rf"|{_TYPE_KEYWORD}\s*(?:\*\s*(?:\((?:[^()])*\)|\w+)|\((?:[^()]|\([^()]*\))*\))?)"
)
_SUBPROGRAM_RE = re.compile(r"\s*(function|subroutine)\s+(\w+)\s*")
_END_RE = re.compile(
    r"^end\s*(module|submodule|program|subroutine|function|block\s*data|interface|procedure)?\b\s*(\w*)\s*$"
)
_OTHER_END_RE = re.compile(
    r"^end\s*(do|if|select|associate|block(?!\s*data)|type|where|forall|critical|enum|team|enumeration|change)\b"
)
_MODULE_RE = re.compile(r"^module\s+(?!procedure\b|subroutine\b|function\b)(\w+)\s*$")
_SUBMODULE_RE = re.compile(r"^submodule\s*\(([^)]*)\)\s*(\w+)\s*$")
_PROGRAM_RE = re.compile(r"^program\s+(\w+)\s*$")
_BLOCK_DATA_RE = re.compile(r"^block\s*data\b\s*(\w*)\s*$")
_INTERFACE_RE = re.compile(r"^(abstract\s+)?interface\b\s*(.*)$")
_MODULE_PROCEDURE_RE = re.compile(r"^module\s+procedure\s+(\w+)\s*$")
_TYPE_DEF_RE = re.compile(r"^type\s*(?:,[^:]*)?::\s*\w+|^type\s+(?!is\b)\w+\s*(?:\(.*\))?\s*$")
_ENUM_RE = re.compile(r"^enum\b|^enumeration\s+type\b")
_IMPLICIT_RE = re.compile(r"^implicit\s+(.*)$")
_USE_RE = re.compile(r"^use\b\s*(?:,\s*(intrinsic|non_intrinsic)\s*)?(?:::)?\s*(\w+)\s*(?:,\s*(.*))?$")
_DECL_RE = re.compile(rf"^(?:{_TYPE_KEYWORD}|type\s*\(|class\s*\(|procedure\s*\()")
_ASSIGNMENT_RE = re.compile(r"^\w+\s*(?:\(.*\))?\s*(?:%\s*\w+\s*(?:\(.*\))?\s*)*=(?!=)")
_ATTR_STMT_RE = re.compile(
    r"^(intent\s*\([^)]*\)|(?:save|dimension|allocatable|pointer|target|optional|value|external|intrinsic"
    r"|protected|asynchronous|volatile|contiguous)\b)\s*(?:::)?\s*(.*)$"
)
_PARAMETER_STMT_RE = re.compile(r"^parameter\s*\((.*)\)\s*$")
# A declaration whose type is not recognised, typically a preprocessor macro: "VARTYPE(KKP), intent(in) :: q".
_MACRO_DECL_RE = re.compile(r"^([a-z_]\w*)\s*(?:\((?:[^()]|\([^()]*\))*\))?\s*(?:,[^:]*)?::")
_NOT_DECL_KEYWORDS = frozenset(
    [
        "use",
        "import",
        "public",
        "private",
        "protected",
        "generic",
        "procedure",
        "final",
        "enumerator",
        "namelist",
        "common",
        "equivalence",
        "data",
        "interface",
        "module",
        "submodule",
        "program",
        "type",
        "class",
        "bind",
    ]
)


def split_top(text: str, sep: str = ",") -> list[str]:
    """Split *text* on *sep* outside parentheses, brackets and character literals."""
    parts, depth, quote, current = [], 0, None, []
    for c in text:
        if quote:
            if c == quote:
                quote = None
        elif c in "'\"":
            quote = c
        elif c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        elif c == sep and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(c)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def balanced_end(text: str, start: int) -> int:
    """Index just past the parenthesis group opening at *text[start]* (len(text) when unbalanced)."""
    depth, quote = 0, None
    for i in range(start, len(text)):
        c = text[i]
        if quote:
            if c == quote:
                quote = None
        elif c in "'\"":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(text)


def _find_top(text: str, token: str) -> int:
    """Index of the first *token* outside parentheses and literals, -1 when absent."""
    depth, quote = 0, None
    for i, c in enumerate(text):
        if quote:
            if c == quote:
                quote = None
        elif c in "'\"":
            quote = c
        elif c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        elif depth == 0 and text.startswith(token, i):
            return i
    return -1


@dataclass
class Decl:
    """A declared entity.

    Attributes
    ----------
    name : str
        Lower-case name.
    type_spec : str
        Type specification as written (masked, e.g. ``real(rk)``); '' when declared only by attribute
        statements.
    attrs : dict
        Attribute name to argument ('' when none), e.g. ``{"intent": "in", "dimension": ":,:"}``.
    dims : str or None
        Array specification attached to the entity (``a(:,:)``), or from a ``dimension`` attribute.
    init : str or None
        Initialiser text after ``=`` or ``=>``.
    pointer_init : bool
        The initialiser uses ``=>``.
    line : int
        Line of the (first) declaring statement.
    """

    name: str
    type_spec: str = ""
    attrs: dict[str, str] = field(default_factory=dict)
    dims: str | None = None
    init: str | None = None
    pointer_init: bool = False
    line: int = 0


@dataclass(frozen=True)
class Use:
    """A ``use`` statement."""

    module: str
    nature: str  # "", "intrinsic" or "non_intrinsic"
    only: bool
    line: int
    statement: Statement


@dataclass
class Unit:
    """A scoping unit.

    Attributes
    ----------
    kind : str
        ``module``, ``submodule``, ``program``, ``subroutine``, ``function``, ``module procedure``,
        ``block data``, ``interface`` (the block; its bodies are children) or ``fragment`` (code outside any
        unit, e.g. an include file).
    name : str
        Lower-case name ('' when anonymous).
    header : Statement or None
        Opening statement.
    end_line : int
        Last line of the unit.
    parent : Unit or None
    children : list of Unit
    statements : list of Statement
        Statements of this unit, excluding those of child units (header and end statement excluded).
    args : list of str
        Dummy argument names (lower case, alternate returns excluded).
    result : str or None
        Function result name.
    prefixes : set of str
        Procedure prefixes (``pure``, ``elemental``, ``module`` ...).
    implicit_none : bool
        ``implicit none`` (or ``implicit none (type ...)``) appears in the unit.
    implicit_none_external : bool
        ``implicit none (external ...)`` appears in the unit.
    implicit_mappings : list of Statement
        Other ``implicit`` statements (type mappings).
    decls : dict
        Name to `Decl`.
    save_all : bool
        A bare ``save`` statement appears.
    uses : list of Use
    default_access : str or None
        ``private`` / ``public`` default accessibility statement.
    access_line : int
        Line of the default accessibility statement.
    contains_line : int
        Line of ``contains`` (0 when absent).
    abstract : bool
        Interface block is abstract.
    """

    kind: str
    name: str = ""
    header: Statement | None = None
    end_line: int = 0
    parent: Unit | None = None
    children: list[Unit] = field(default_factory=list)
    statements: list[Statement] = field(default_factory=list)
    args: list[str] = field(default_factory=list)
    result: str | None = None
    prefixes: set[str] = field(default_factory=set)
    implicit_none: bool = False
    implicit_none_external: bool = False
    implicit_mappings: list[Statement] = field(default_factory=list)
    decls: dict[str, Decl] = field(default_factory=dict)
    save_all: bool = False
    uses: list[Use] = field(default_factory=list)
    default_access: str | None = None
    access_line: int = 0
    contains_line: int = 0
    abstract: bool = False

    @property
    def line(self) -> int:
        """First line of the unit."""
        if self.header is not None:
            return self.header.line
        return self.statements[0].line if self.statements else 0

    @property
    def is_procedure(self) -> bool:
        return self.kind in PROCEDURE_KINDS

    @property
    def is_interface_body(self) -> bool:
        """A procedure declared inside an interface block."""
        return self.parent is not None and self.parent.kind == "interface"

    @property
    def is_external(self) -> bool:
        """A procedure defined outside any module, submodule, program or interface (an external procedure)."""
        return self.is_procedure and self.parent is None

    def walk(self) -> Iterator[Unit]:
        """This unit and all its descendants, depth first."""
        yield self
        for child in self.children:
            yield from child.walk()

    def decl(self, name: str) -> Decl:
        """The declaration of *name*, created empty when absent."""
        key = name.lower()
        if key not in self.decls:
            self.decls[key] = Decl(name=key)
        return self.decls[key]


@dataclass
class FileUnits:
    """The units of one source file."""

    source: SourceFile
    units: list[Unit]

    def walk(self) -> Iterator[Unit]:
        """Every unit of the file, depth first."""
        for unit in self.units:
            yield from unit.walk()


def _parse_header(masked: str) -> tuple[str, str, set[str], list[str], str | None] | None:
    """Recognise a subroutine/function statement: (kind, name, prefixes, args, result)."""
    pos, prefixes = 0, set()
    while True:
        match = _PREFIX_RE.match(masked, pos)
        if not match or match.end() == pos:
            break
        word = match.group(0).strip().split("(")[0].split("*")[0].strip()
        prefixes.add(re.sub(r"\s+", " ", word))
        pos = match.end()
    match = _SUBPROGRAM_RE.match(masked, pos)
    if not match:
        return None
    kind, name = match.group(1), match.group(2)
    rest = masked[match.end() :]
    args: list[str] = []
    if rest.startswith("("):
        end = balanced_end(rest, 0)
        args = [a for a in (x.strip() for x in rest[1 : end - 1].split(",")) if a and a != "*"]
        rest = rest[end:]
    if rest.strip() and not re.match(r"^\s*(result\s*\(|bind\s*\()", rest):
        return None  # e.g. "function f = 1" is not a header
    result = None
    res = re.search(r"\bresult\s*\(\s*(\w+)\s*\)", rest)
    if res:
        result = res.group(1)
    elif kind == "function":
        result = name
    return kind, name, prefixes, args, result


def _parse_attrs(text: str) -> dict[str, str]:
    attrs = {}
    for item in split_top(text):
        match = re.match(r"^(\w+)\s*(?:\((.*)\))?\s*$", item)
        if match:
            attrs[match.group(1)] = (match.group(2) or "").strip().replace(" ", "")
    return attrs


def _parse_entity(item: str) -> tuple[str, str | None, str | None, bool] | None:
    """Split an entity declaration ``name(dims)*len = init`` into (name, dims, init, pointer_init)."""
    match = re.match(r"^(\w+)\s*", item)
    if not match:
        return None
    name, pos, dims = match.group(1), match.end(), None
    if item[pos : pos + 1] == "(":
        end = balanced_end(item, pos)
        dims, pos = item[pos + 1 : end - 1].replace(" ", ""), end
    rest = item[pos:].lstrip()
    if rest.startswith("*"):  # character length
        rest = rest[1:].lstrip()
        rest = rest[balanced_end(rest, 0) :] if rest.startswith("(") else re.sub(r"^\w+", "", rest)
        rest = rest.lstrip()
    if rest.startswith("=>"):
        return name, dims, rest[2:].strip(), True
    if rest.startswith("="):
        return name, dims, rest[1:].strip(), False
    return name, dims, None, False


def _type_spec_end(masked: str) -> int:
    """Index just past the type specification at the start of a type-declaration statement."""
    match = re.match(rf"^(?:{_TYPE_KEYWORD}|type|class|procedure|[a-z_]\w*)\s*", masked)
    pos = match.end() if match else 0
    if masked[pos : pos + 1] == "(":
        return balanced_end(masked, pos)
    if masked[pos : pos + 1] == "*":
        pos = pos + 1
        while pos < len(masked) and masked[pos] == " ":
            pos += 1
        if masked[pos : pos + 1] == "(":
            return balanced_end(masked, pos)
        word = re.match(r"\w+", masked[pos:])
        return pos + (word.end() if word else 0)
    return pos


def _record_declaration(unit: Unit, stmt: Statement) -> None:
    masked = stmt.masked
    spec_end = _type_spec_end(masked)
    type_spec = re.sub(r"\s+", "", masked[:spec_end])
    rest = masked[spec_end:]
    sep = _find_top(rest, "::")
    if sep >= 0:
        attrs, entities = _parse_attrs(rest[:sep].lstrip().lstrip(",")), rest[sep + 2 :]
    else:
        attrs, entities = {}, rest.lstrip().lstrip(",")
    for item in split_top(entities):
        parsed = _parse_entity(item)
        if parsed is None:
            continue
        name, dims, init, pointer_init = parsed
        decl = unit.decl(name)
        decl.type_spec = type_spec
        decl.attrs.update(attrs)
        decl.dims = dims if dims is not None else attrs.get("dimension", decl.dims)
        if init is not None:
            decl.init, decl.pointer_init = init, pointer_init
        decl.line = decl.line or stmt.line


def _record_attribute_statement(unit: Unit, match: re.Match, stmt: Statement) -> None:
    attr_text, names = match.group(1), match.group(2)
    attr = re.match(r"\w+", attr_text).group(0)
    arg = ""
    if attr == "intent":
        arg = attr_text[attr_text.index("(") + 1 : attr_text.rindex(")")].replace(" ", "")
    if attr == "save" and not names.strip():
        unit.save_all = True
        return
    for item in split_top(names):
        if item.startswith("/"):
            continue  # common block name in save
        parsed = _parse_entity(item)
        if parsed is None:
            continue
        name, dims, _, _ = parsed
        decl = unit.decl(name)
        decl.attrs[attr] = arg
        if attr == "dimension" or (dims is not None and decl.dims is None):
            decl.dims = dims
        decl.line = decl.line or stmt.line


def _record_spec(unit: Unit, stmt: Statement) -> None:
    """Extract specification facts from a statement belonging to *unit*."""
    masked = stmt.masked.strip()
    match = _IMPLICIT_RE.match(masked)
    if match:
        spec = match.group(1).strip()
        none = re.match(r"^none\s*(?:\((.*)\))?\s*$", spec)
        if none:
            items = {i.strip() for i in (none.group(1) or "").split(",") if i.strip()}
            if not items or "type" in items:
                unit.implicit_none = True
            if "external" in items:
                unit.implicit_none_external = True
        else:
            unit.implicit_mappings.append(stmt)
        return
    match = _USE_RE.match(masked)
    if match:
        unit.uses.append(
            Use(
                module=match.group(2),
                nature=match.group(1) or "",
                only=bool(match.group(3) and re.match(r"^only\s*:", match.group(3).strip())),
                line=stmt.line,
                statement=stmt,
            )
        )
        return
    if masked in ("private", "public"):
        unit.default_access, unit.access_line = masked, stmt.line
        return
    if masked == "contains":
        unit.contains_line = stmt.line
        return
    if _DECL_RE.match(masked) and ("::" in masked or not _ASSIGNMENT_RE.match(masked)):
        _record_declaration(unit, stmt)
        return
    match = _PARAMETER_STMT_RE.match(masked)
    if match:
        for item in split_top(match.group(1)):
            name = item.split("=")[0].strip()
            if re.fullmatch(r"\w+", name):
                unit.decl(name).attrs["parameter"] = ""
        return
    match = _ATTR_STMT_RE.match(masked)
    if match and not _ASSIGNMENT_RE.match(masked):
        _record_attribute_statement(unit, match, stmt)
        return
    match = _MACRO_DECL_RE.match(masked)
    if match and match.group(1) not in _NOT_DECL_KEYWORDS:
        _record_declaration(unit, stmt)


def _closes(end_kind: str, unit_kind: str) -> bool:
    """Whether an ``end [end_kind]`` statement closes a unit of *unit_kind*."""
    if unit_kind == "fragment":
        return False
    if not end_kind:  # bare "end": any unit but an interface block
        return unit_kind != "interface"
    if end_kind == "procedure":
        return unit_kind == "module procedure"
    return end_kind == unit_kind


def build_units(source: SourceFile) -> FileUnits:
    """Build the unit tree of *source*."""
    roots: list[Unit] = []
    stack: list[Unit] = []
    skip_depth = 0  # inside a derived-type definition or an enum: statements are not specifications

    def current() -> Unit:
        if not stack:
            fragment = Unit(kind="fragment")
            roots.append(fragment)
            stack.append(fragment)
        return stack[-1]

    def open_unit(unit: Unit) -> None:
        if stack and stack[-1].kind == "fragment":
            stack.pop()
        if stack:
            unit.parent = stack[-1]
            stack[-1].children.append(unit)
        else:
            roots.append(unit)
        stack.append(unit)

    for stmt in source.statements:
        masked = stmt.masked.strip()
        if stmt.sentinel is not None:
            current().statements.append(stmt)
            continue
        if skip_depth:
            if re.match(r"^end\s*(type|enum|enumeration\s+type)\b", masked):
                skip_depth -= 1
            current().statements.append(stmt)
            continue
        end = _END_RE.match(masked)
        if end and not _OTHER_END_RE.match(masked):
            end_kind = re.sub(r"\s+", " ", end.group(1) or "")
            for idx in range(len(stack) - 1, -1, -1):
                if _closes(end_kind, stack[idx].kind):
                    for closed in stack[idx:]:
                        closed.end_line = stmt.end_line
                    del stack[idx:]
                    break
            continue
        if _TYPE_DEF_RE.match(masked) or _ENUM_RE.match(masked):
            skip_depth += 1
            current().statements.append(stmt)
            continue
        match = _MODULE_PROCEDURE_RE.match(masked)
        if match:
            if stack and stack[-1].kind == "interface":
                stack[-1].statements.append(stmt)
            else:
                open_unit(Unit(kind="module procedure", name=match.group(1), header=stmt, prefixes={"module"}))
            continue
        header = _parse_header(masked)
        if header:
            kind, name, prefixes, args, result = header
            open_unit(
                Unit(
                    kind=kind, name=name, header=stmt, prefixes=prefixes, args=[a.lower() for a in args], result=result
                )
            )
            continue
        opened = None
        for regex, kind in ((_MODULE_RE, "module"), (_PROGRAM_RE, "program"), (_BLOCK_DATA_RE, "block data")):
            match = regex.match(masked)
            if match:
                opened = Unit(kind=kind, name=match.group(1), header=stmt)
                break
        else:
            match = _SUBMODULE_RE.match(masked)
            if match:
                opened = Unit(kind="submodule", name=match.group(2), header=stmt)
            else:
                match = _INTERFACE_RE.match(masked)
                if match:
                    opened = Unit(
                        kind="interface", name=match.group(2).strip(), header=stmt, abstract=bool(match.group(1))
                    )
        if opened is not None:
            open_unit(opened)
            continue
        unit = current()
        unit.statements.append(stmt)
        _record_spec(unit, stmt)
    last = source.statements[-1].end_line if source.statements else 0
    for unit in stack:
        unit.end_line = unit.end_line or last
    return FileUnits(source=source, units=roots)
