"""preprocessor.py — evaluation of C-preprocessor conditionals in Fortran sources.

Only the directives that decide *which lines are compiled* are interpreted (``#if``, ``#ifdef``,
``#ifndef``, ``#elif``, ``#else``, ``#endif``, ``#define``, ``#undef``); macro expansion inside Fortran code is
not performed. The defines come from the build mode (``-D``/``-U`` flags), so the analysed code is the code
the compiler sees.
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
import shlex
from dataclasses import dataclass, field

_DIRECTIVE_RE = re.compile(r"^\s*#\s*(\w+)\s*(.*?)\s*$")
_TOKEN_RE = re.compile(r"\s*(?:(\d+)[uUlL]*|(\w+)|(&&|\|\||==|!=|<=|>=|<<|>>|[-+*/%<>!()~]))")
_INCLUDE_RE = re.compile(r"""^["<]([^">]+)[">]""")


def parse_defines(flags: str) -> dict[str, str]:
    """Macro definitions from compiler flags: ``-DNAME``, ``-DNAME=VALUE``, ``-D NAME``; ``-UNAME`` removes.

    Parameters
    ----------
    flags : str
        Flags as passed to the compiler or preprocessor.

    Returns
    -------
    dict
        ``{name: value}``; a define without value has value ``"1"`` (cpp semantics).
    """
    defines: dict[str, str] = {}
    try:
        tokens = shlex.split(flags)
    except ValueError:
        tokens = flags.split()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in ("-D", "-U") and i + 1 < len(tokens):
            tok = tok + tokens[i + 1]
            i += 1
        if tok.startswith("-D") and len(tok) > 2:
            name, _, value = tok[2:].partition("=")
            defines[name] = value if value else "1"
        elif tok.startswith("-U") and len(tok) > 2:
            defines.pop(tok[2:], None)
        i += 1
    return defines


class _ExprError(ValueError):
    """A ``#if`` expression cannot be evaluated."""


class _Evaluator:
    """Recursive-descent evaluator of cpp integer constant expressions."""

    _BINARY = {
        "||": (1, lambda a, b: int(bool(a) or bool(b))),
        "&&": (2, lambda a, b: int(bool(a) and bool(b))),
        "==": (3, lambda a, b: int(a == b)),
        "!=": (3, lambda a, b: int(a != b)),
        "<": (4, lambda a, b: int(a < b)),
        ">": (4, lambda a, b: int(a > b)),
        "<=": (4, lambda a, b: int(a <= b)),
        ">=": (4, lambda a, b: int(a >= b)),
        "<<": (5, lambda a, b: a << b),
        ">>": (5, lambda a, b: a >> b),
        "+": (6, lambda a, b: a + b),
        "-": (6, lambda a, b: a - b),
        "*": (7, lambda a, b: a * b),
        "/": (7, lambda a, b: int(a / b) if b else 0),
        "%": (7, lambda a, b: a % b if b else 0),
    }

    def __init__(self, expr: str, defines: dict[str, str]) -> None:
        self.defines = defines
        self.tokens = self._tokenize(self._expand(self._resolve_defined(expr), depth=0))
        self.pos = 0

    def _resolve_defined(self, expr: str) -> str:
        def repl(match: re.Match) -> str:
            return "1" if match.group(1) in self.defines else "0"

        expr = re.sub(r"\bdefined\s*\(\s*(\w+)\s*\)", repl, expr)
        return re.sub(r"\bdefined\s+(\w+)", repl, expr)

    def _expand(self, expr: str, depth: int) -> str:
        """Replace macro names by their values (recursively); undefined identifiers become 0."""
        if depth > 16:
            raise _ExprError("macro expansion too deep")

        def repl(match: re.Match) -> str:
            name = match.group(0)
            if name in self.defines:
                return f"({self._expand(self._resolve_defined(self.defines[name]), depth + 1)})"
            return "0"

        return re.sub(r"\b[A-Za-z_]\w*\b", repl, expr)

    @staticmethod
    def _tokenize(expr: str) -> list[str]:
        tokens, pos, expr = [], 0, expr.rstrip()
        while pos < len(expr):
            match = _TOKEN_RE.match(expr, pos)
            if not match or match.end() == pos:
                raise _ExprError(f"unexpected text {expr[pos:]!r}")
            tokens.append(next(group for group in match.groups() if group is not None))
            pos = match.end()
        return tokens

    def evaluate(self) -> int:
        value = self._binary(1)
        if self.pos != len(self.tokens):
            raise _ExprError(f"trailing tokens {self.tokens[self.pos :]}")
        return value

    def _peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _binary(self, min_prec: int) -> int:
        left = self._unary()
        while (op := self._peek()) in self._BINARY and self._BINARY[op][0] >= min_prec:
            prec, func = self._BINARY[op]
            self.pos += 1
            left = func(left, self._binary(prec + 1))
        return left

    def _unary(self) -> int:
        tok = self._peek()
        if tok is None:
            raise _ExprError("unexpected end of expression")
        self.pos += 1
        if tok == "!":
            return int(not self._unary())
        if tok == "-":
            return -self._unary()
        if tok == "+":
            return self._unary()
        if tok == "~":
            return ~self._unary()
        if tok == "(":
            value = self._binary(1)
            if self._peek() != ")":
                raise _ExprError("missing ')'")
            self.pos += 1
            return value
        if tok.isdigit():
            return int(tok)
        raise _ExprError(f"unexpected token {tok!r}")


def evaluate(expr: str, defines: dict[str, str]) -> bool:
    """Truth value of the ``#if`` expression *expr* under *defines*.

    Raises
    ------
    ValueError
        The expression is malformed or uses unsupported syntax.
    """
    return bool(_Evaluator(expr, defines).evaluate())


@dataclass
class PreprocessResult:
    """Outcome of `preprocess`.

    Attributes
    ----------
    active : list of bool
        Per physical line (0-based): True when the line is compiled. Directive lines are never active.
    includes : list of (int, str)
        ``#include`` directives in active regions, as (1-based line, file name).
    warnings : list of (int, str)
        Problems met (1-based line, message): unevaluable conditions (taken as true), unbalanced
        directives.
    """

    active: list[bool]
    includes: list[tuple[int, str]] = field(default_factory=list)
    warnings: list[tuple[int, str]] = field(default_factory=list)


def preprocess(lines: list[str], defines: dict[str, str] | None = None) -> PreprocessResult:
    """Decide which of *lines* are compiled under *defines*.

    A continued directive (trailing backslash) spans several lines; all of them are inactive.
    """
    defines = dict(defines or {})
    active = [False] * len(lines)
    result = PreprocessResult(active=active)
    # stack entries: [parent_active, this_branch_active, some_branch_taken]
    stack: list[list[bool]] = []
    current = True
    i = 0
    while i < len(lines):
        line = lines[i]
        match = _DIRECTIVE_RE.match(line) if line.lstrip().startswith("#") else None
        if match is None:
            active[i] = current
            i += 1
            continue
        start = i
        text = line.rstrip()
        while text.endswith("\\") and i + 1 < len(lines):
            i += 1
            text = text[:-1] + " " + lines[i].rstrip()
        i += 1
        match = _DIRECTIVE_RE.match(text)
        name, arg = match.group(1), re.sub(r"/\*.*?\*/|//.*$", "", match.group(2)).strip()
        lineno = start + 1

        def cond(expr: str, lineno: int = lineno) -> bool:
            try:
                return evaluate(expr, defines)
            except ValueError as exc:
                result.warnings.append((lineno, f"cannot evaluate '#if {expr}' ({exc}); assumed true"))
                return True

        if name in ("if", "ifdef", "ifndef"):
            if name == "ifdef":
                taken = arg.split()[0] in defines if arg else False
            elif name == "ifndef":
                taken = arg.split()[0] not in defines if arg else True
            else:
                taken = cond(arg) if current else False
            stack.append([current, current and taken, current and taken])
            current = current and taken
        elif name == "elif":
            if not stack:
                result.warnings.append((lineno, "#elif without #if"))
                continue
            parent, _, done = stack[-1]
            taken = parent and not done and cond(arg)
            stack[-1] = [parent, taken, done or taken]
            current = taken
        elif name == "else":
            if not stack:
                result.warnings.append((lineno, "#else without #if"))
                continue
            parent, _, done = stack[-1]
            stack[-1] = [parent, parent and not done, True]
            current = parent and not done
        elif name == "endif":
            if not stack:
                result.warnings.append((lineno, "#endif without #if"))
                continue
            current = stack.pop()[0]
        elif not current:
            continue
        elif name == "define":
            parts = arg.split(None, 1)
            if parts and "(" not in parts[0]:
                defines[parts[0]] = parts[1] if len(parts) > 1 else "1"
        elif name == "undef":
            if arg:
                defines.pop(arg.split()[0], None)
        elif name == "include":
            inc = _INCLUDE_RE.match(arg)
            if inc:
                result.includes.append((lineno, inc.group(1)))
    if stack:
        result.warnings.append((len(lines), f"{len(stack)} unterminated #if block(s)"))
    return result
