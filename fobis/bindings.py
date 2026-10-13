"""bindings.py — C and Python bindings from the facts of the modules (phase V12 of PLAN-verification.md).

For every public procedure of the chosen modules whose arguments allow it, a ``bind(c)`` shim is generated in a
Fortran module (``<name>_c.f90``), with its C prototype (``<name>.h``) and a Python ``ctypes`` wrapper
(``<name>.py``). The shim converts every value explicitly on the way in and out (``int(x, K)``, ``real(x, K)``,
``logical(x, K)``) into temporaries declared with the procedure's own type spec, so the result is right whatever the
project's kind parameters are; the C type is chosen from the range or precision the kind resolves to (from the
source analysis: ``selected_int_kind``, ``selected_real_kind``, ``iso_fortran_env``, ``iso_c_binding``, literals);
default kinds are taken as C ``int``, ``float`` and ``double``, which is what gfortran, ifx and nvfortran use without
``-i8``/``-r8``.

Bound: scalars and arrays of integer, real and logical, by value or reference (``intent(out)``/``inout`` copied
back); explicit-shape arrays (literal extents, or extents that are other dummies), assumed-shape arrays (an extent
argument per dimension is added); functions returning a scalar, or an array of literal shape (returned through an
output argument); the specifics of public generic interfaces. Not bound, each with its reason: character, complex,
derived types, procedure arguments, optional/allocatable/pointer dummies, assumed rank or size, kinds that cannot be
resolved, and procedures already ``bind(c)``.
"""

from __future__ import annotations

import keyword
import re
from dataclasses import dataclass, field
from typing import Any

INT_C = {
    8: ("int8_t", "c_int8_t", "c_int8"),
    16: ("int16_t", "c_int16_t", "c_int16"),
    32: ("int32_t", "c_int32_t", "c_int32"),
    64: ("int64_t", "c_int64_t", "c_int64"),
}
REAL_C = {"float": ("float", "c_float", "c_float"), "double": ("double", "c_double", "c_double")}
BOOL_C = ("bool", "c_bool", "c_bool")
_TYPE = re.compile(r"^\s*(integer|real|logical|double\s*precision|complex|character|type|class|procedure)\b\s*(.*)$")
_INT_NAMES = {
    "int8": 8,
    "int16": 16,
    "int32": 32,
    "int64": 64,
    "c_int": 32,
    "c_short": 16,
    "c_long": 64,
    "c_long_long": 64,
    "c_signed_char": 8,
    "c_int8_t": 8,
    "c_int16_t": 16,
    "c_int32_t": 32,
    "c_int64_t": 64,
    "c_size_t": 64,
}
_INT_LITERAL = {"1": 8, "2": 16, "4": 32, "8": 64}
_NAME = re.compile(r"[a-z_]\w*")


class BindingsError(Exception):
    """No module to bind, or an output cannot be written."""


@dataclass
class CType:
    """The C side of a Fortran type: C name, iso_c_binding kind, ctypes name, Fortran base type."""

    c: str
    fortran_kind: str
    ctypes: str
    base: str  # integer, real, logical

    def fortran(self) -> str:
        return f"{self.base}({self.fortran_kind})"


def _int_bits(range_digits: int) -> int | None:
    for bits, limit in ((8, 2), (16, 4), (32, 9), (64, 18)):
        if range_digits <= limit:
            return bits
    return None


def _kind_text(type_spec: str) -> tuple[str, str]:
    """(base type, kind expression or '') of a type spec."""
    match = _TYPE.match(type_spec.strip().lower())
    if not match:
        return "", ""
    base, rest = match.group(1).replace(" ", ""), match.group(2).strip()
    if rest.startswith("("):
        return base, re.sub(r"^\(\s*(kind\s*=\s*)?", "", rest).rstrip(")").strip()
    if rest.startswith("*"):
        return base, rest[1:].strip()
    return base, ""


def resolve_type(type_spec: str, project: Any, local: dict[str, str] | None = None) -> tuple[CType | None, str]:
    """(the C type, '') of a declaration's type spec, or (None, why it is not bindable)."""
    base, kind = _kind_text(type_spec)
    if not base:
        return None, f"type {type_spec!r} not understood"
    if base == "doubleprecision":
        return CType(*REAL_C["double"], "real"), ""
    if base in ("character", "complex", "type", "class", "procedure"):
        return None, f"{base} arguments are not bound"
    if base == "logical":
        return CType(*BOOL_C, "logical"), ""
    if base == "integer":
        if not kind:
            return CType(*INT_C[32], "integer"), ""
        bits = _INT_NAMES.get(kind) or _INT_LITERAL.get(kind)
        if bits is None:
            init = ((local or {}).get(kind) or getattr(project, "kind_parameters", {}).get(kind, "")).replace(" ", "")
            found = re.fullmatch(r"selected_int_kind\((\d+)\)", init)
            bits = _int_bits(int(found.group(1))) if found else _INT_NAMES.get(init)
        if bits is None:
            return None, f"integer kind {kind!r} cannot be resolved to a C integer"
        return CType(*INT_C[bits], "integer"), ""
    if not kind:
        return CType(*REAL_C["float"], "real"), ""
    if kind in ("c_float", "c_double"):
        return CType(*REAL_C[kind[2:]], "real"), ""
    precision = project.real_precision(kind, local) if hasattr(project, "real_precision") else None
    if precision is None:
        return None, f"real kind {kind!r} cannot be resolved"
    if precision <= 6:
        return CType(*REAL_C["float"], "real"), ""
    if precision <= 15:
        return CType(*REAL_C["double"], "real"), ""
    return None, f"real kind {kind!r} ({precision} digits) has no portable C type"


@dataclass
class Argument:
    name: str
    ctype: CType
    type_spec: str  # the Fortran type spec of the procedure's dummy (temporaries are declared with it)
    intent: str  # in, out, inout
    value: bool
    dims: list[str] = field(default_factory=list)  # [] scalar; literal extents, dummy names, or ':' (assumed shape)


@dataclass
class Binding:
    module: str
    procedure: str  # the Fortran procedure called
    c_name: str
    kind: str  # subroutine or function
    arguments: list[Argument] = field(default_factory=list)
    result: Argument | None = None  # function result; dims set when an array result (returned through an argument)
    skipped: str = ""  # why not bound ('' when bound)
    call: str = ""  # the name the shim calls: the procedure, or its public generic when the specific is private

    def to_dict(self) -> dict:
        data = {"module": self.module, "procedure": self.procedure, "c_name": self.c_name, "kind": self.kind}
        if self.skipped:
            data["skipped"] = self.skipped
        return data


def _dims(text: str | None) -> list[str]:
    if not text:
        return []
    depth, parts, current = 0, [], ""
    for char in text:
        if char == "," and depth == 0:
            parts.append(current.strip())
            current = ""
            continue
        depth += char == "("
        depth -= char == ")"
        current += char
    parts.append(current.strip())
    return parts


def _header_type(unit: Any) -> str:
    """The type spec written before ``function`` in the header (``real(r8p) pure function f``), '' when none."""
    header = unit.header.masked if unit.header is not None else ""
    match = re.search(
        r"\b(integer|real|logical|complex|character|double\s+precision|type)\s*(\([^)]*\))?\s*(?=(?:\w+\s+)*function\b)",
        header,
    )
    return (match.group(1) + (match.group(2) or "")) if match else ""


def _argument(unit: Any, name: str, project: Any, local: dict[str, str]) -> tuple[Argument | None, str]:
    decl = unit.decls.get(name)
    if decl is None or not decl.type_spec:
        return None, f"argument {name} has no declared type"
    for bad in ("optional", "allocatable", "pointer"):
        if bad in decl.attrs:
            return None, f"argument {name} is {bad}"
    ctype, why = resolve_type(decl.type_spec, project, local)
    if ctype is None:
        return None, f"argument {name}: {why}"
    dims = _dims(decl.dims or decl.attrs.get("dimension"))
    for extent in dims:
        if extent in ("*", "..") or extent.endswith(":*"):
            return None, f"argument {name} is assumed-size or assumed-rank"
        if extent != ":" and ":" in extent:
            return None, f"argument {name} has bounds that are not literal extents"
        if extent != ":" and not re.fullmatch(r"\d+", extent):
            if not _NAME.fullmatch(extent):
                return None, f"argument {name}: extent {extent!r} is an expression"
            if extent not in unit.args:
                return None, f"argument {name}: extent {extent!r} is not a dummy argument"
    intent = decl.attrs.get("intent", "inout").replace(" ", "")
    return Argument(name, ctype, decl.type_spec, intent, "value" in decl.attrs, dims), ""


def plan(module: Any, project: Any, public: Any, specifics: dict[str, str]) -> list[Binding]:
    """The bindings of a module unit's public procedures and of the specifics of its public generics (*specifics*:
    specific -> generic); a private specific is called through its generic, which resolves to it because the shim's
    actual arguments have the specific's own types."""
    found = []
    local = {n: d.init for n, d in module.decls.items() if "parameter" in d.attrs and d.init}
    for unit in module.children:
        if unit.kind not in ("subroutine", "function") or not (public(module, unit.name) or unit.name in specifics):
            continue
        binding = Binding(module.name, unit.name, f"{module.name}_{unit.name}", unit.kind)
        binding.call = unit.name if public(module, unit.name) else specifics[unit.name]
        found.append(binding)
        header = unit.header.masked if unit.header is not None else ""
        if re.search(r"\bbind\s*\(\s*c\b", header):
            binding.skipped = "already bind(c): callable from C as it is"
            continue
        for name in unit.args:
            argument, reason = _argument(unit, name, project, local)
            if argument is None:
                binding.skipped = reason
                break
            binding.arguments.append(argument)
        if binding.skipped or unit.kind != "function":
            continue
        result = unit.result or unit.name
        decl = unit.decls.get(result)
        spec = decl.type_spec if decl is not None and decl.type_spec else _header_type(unit)
        ctype, why = resolve_type(spec, project, local) if spec else (None, "the result type is not declared")
        dims = _dims(decl.dims or decl.attrs.get("dimension")) if decl is not None else []
        if ctype is None:
            binding.skipped = f"result: {why}"
        elif dims and not all(re.fullmatch(r"\d+", d) for d in dims):
            binding.skipped = "the result is an array without a literal shape"
        elif decl is not None and ("allocatable" in decl.attrs or "pointer" in decl.attrs):
            binding.skipped = "the result is allocatable or a pointer"
        else:
            binding.result = Argument(result, ctype, spec, "out", False, dims)
    return found


# ── the shim module ────────────────────────────────────────────────────────────


def _convert(ctype: CType, expression: str, kind: str) -> str:
    return {"integer": "int", "real": "real", "logical": "logical"}[ctype.base] + f"({expression}, {kind})"


def _kind_of(type_spec: str) -> str:
    """The kind expression of a type spec, for conversions (a default kind written as ``kind(...)``)."""
    base, kind = _kind_text(type_spec)
    if base == "doubleprecision":
        return "kind(1.0d0)"
    return kind or {"integer": "kind(1)", "real": "kind(1.0)", "logical": "kind(.true.)"}[base]


def shim(bindings: list[Binding], name: str) -> str:
    """The Fortran module of the ``bind(c)`` shims."""
    bound = [b for b in bindings if not b.skipped]
    lines = [f"module {name}_c", "!< bind(c) shims generated by fobis bindings: do not edit, regenerate."]
    lines += ["use, intrinsic :: iso_c_binding", *(f"use {m}" for m in sorted({b.module for b in bound}))]
    lines += ["implicit none", "private", *(f"public :: {b.c_name}" for b in bound), "contains"]
    for binding in bound:
        lines += ["", *_shim_procedure(binding)]
    lines += ["", f"end module {name}_c"]
    return "\n".join(lines) + "\n"


def _shim_procedure(b: Binding) -> list[str]:
    extents, dummies, decls, before, after, actuals = [], [], [], [], [], []
    for arg in b.arguments:
        dims = list(arg.dims)
        for axis, extent in enumerate(dims):
            if extent == ":":
                dims[axis] = f"n_{arg.name}_{axis + 1}"
                extents.append(dims[axis])
        dummies.append(arg.name)
        shape = f"({', '.join(dims)})" if dims else ""
        intent = "in" if arg.value else arg.intent
        decls.append(f"  {arg.ctype.fortran()}, intent({intent}){', value' if arg.value else ''} :: {arg.name}{shape}")
        decls.append(f"  {arg.type_spec} :: {arg.name}_f{shape}")
        if arg.intent != "out" or arg.value:
            before.append(f"  {arg.name}_f = {_convert(arg.ctype, arg.name, _kind_of(arg.type_spec))}")
        if arg.intent in ("out", "inout") and not arg.value:
            after.append(f"  {arg.name} = {_convert(arg.ctype, arg.name + '_f', arg.ctype.fortran_kind)}")
        actuals.append(f"{arg.name}={arg.name}_f")
    call_args = ", ".join(actuals)
    extent_decls = [f"  integer(c_int32_t), intent(in), value :: {e}" for e in extents]
    if b.kind == "function" and b.result is not None and b.result.dims:
        dummies.append("result_")
        decls.append(f"  {b.result.ctype.fortran()}, intent(out) :: result_({', '.join(b.result.dims)})")
        call = f"  result_ = {_convert(b.result.ctype, f'{b.call or b.procedure}({call_args})', b.result.ctype.fortran_kind)}"
        kind = "subroutine"
    elif b.kind == "function":
        decls.append(f"  {b.result.ctype.fortran()} :: {b.c_name}")
        call = f"  {b.c_name} = {_convert(b.result.ctype, f'{b.call or b.procedure}({call_args})', b.result.ctype.fortran_kind)}"
        kind = "function"
    else:
        call = f"  call {b.call or b.procedure}({call_args})"
        kind = "subroutine"
    head = f'{kind} {b.c_name}({", ".join(dummies + extents)}) bind(c, name="{b.c_name}")'
    return [head, *extent_decls, *decls, *before, call, *after, f"end {kind} {b.c_name}"]


# ── the C header ───────────────────────────────────────────────────────────────


def _doc(b: Binding) -> str:
    def shape(arg: Argument) -> str:
        return f"({','.join(arg.dims)})" if arg.dims else ""

    args = ", ".join(f"{a.name}{shape(a)} intent({'in, value' if a.value else a.intent})" for a in b.arguments)
    result = f" -> {b.result.name}{shape(b.result)}" if b.result is not None else ""
    return f"{b.module}::{b.procedure}({args}){result}"


def header(bindings: list[Binding], name: str) -> str:
    guard = re.sub(r"\W", "_", name).upper() + "_H"
    lines = [
        f"/* C interface of {name}: generated by fobis bindings, do not edit. Link with the library built from the",
        f"   project's sources and {name}_c.f90. Arrays are Fortran arrays: contiguous, column-major. */",
        f"#ifndef {guard}",
        f"#define {guard}",
        "#include <stdbool.h>",
        "#include <stdint.h>",
        "",
        "#ifdef __cplusplus",
        'extern "C" {',
        "#endif",
        "",
    ]
    for b in (b for b in bindings if not b.skipped):
        params = []
        for arg in b.arguments:
            if arg.value:
                params.append(f"{arg.ctype.c} {arg.name}")
            else:
                params.append(f"{'const ' if arg.intent == 'in' else ''}{arg.ctype.c} *{arg.name}")
        if b.result is not None and b.result.dims:
            params.append(f"{b.result.ctype.c} *result_")
        params += [f"int32_t n_{a.name}_{i + 1}" for a in b.arguments for i, d in enumerate(a.dims) if d == ":"]
        returns = b.result.ctype.c if b.result is not None and not b.result.dims else "void"
        lines += [f"/* {_doc(b)} */", f"{returns} {b.c_name}({', '.join(params) or 'void'});", ""]
    lines += ["#ifdef __cplusplus", "}", "#endif", f"#endif /* {guard} */"]
    return "\n".join(lines) + "\n"


# ── the Python wrapper ─────────────────────────────────────────────────────────


def _py(name: str) -> str:
    return name + "_" if keyword.iskeyword(name) else name


def python(bindings: list[Binding], name: str) -> str:
    """A ctypes wrapper: one function per binding taking Python numbers and sequences, returning the function's
    result and the ``intent(out)``/``inout`` arguments."""
    lines = [
        f'"""Python interface of {name}: generated by fobis bindings, do not edit.',
        "",
        "Call load() with the shared library built from the project's sources and the shim module, then the functions",
        "with numbers and sequences; arrays are passed and returned as flat lists in Fortran (column-major) order.",
        '"""',
        "",
        "import ctypes",
        "",
        "_lib = None",
        "",
        "",
        "def load(path):",
        '    """Load the shared library and declare the functions."""',
        "    global _lib",
        "    _lib = ctypes.CDLL(path)",
    ]
    for b in (b for b in bindings if not b.skipped):
        argtypes = [
            f"ctypes.{a.ctype.ctypes}" if a.value else f"ctypes.POINTER(ctypes.{a.ctype.ctypes})" for a in b.arguments
        ]
        if b.result is not None and b.result.dims:
            argtypes.append(f"ctypes.POINTER(ctypes.{b.result.ctype.ctypes})")
        argtypes += ["ctypes.c_int32" for a in b.arguments for d in a.dims if d == ":"]
        restype = f"ctypes.{b.result.ctype.ctypes}" if b.result is not None and not b.result.dims else "None"
        lines += [f"    _lib.{b.c_name}.argtypes = [{', '.join(argtypes)}]", f"    _lib.{b.c_name}.restype = {restype}"]
    for b in (b for b in bindings if not b.skipped):
        lines += ["", "", *_python_function(b)]
    return "\n".join(lines) + "\n"


def _python_function(b: Binding) -> list[str]:
    params, body, call, outputs = [], [], [], []
    for arg in b.arguments:
        local, ctype, name = f"_{arg.name}", f"ctypes.{arg.ctype.ctypes}", _py(arg.name)
        if arg.value:
            params.append(name)
            call.append(name)
        elif arg.dims:
            params.append(name)  # an output array is passed too: its length sizes the buffer
            if arg.intent == "out":
                body.append(f"    {local} = ({ctype} * len({name}))()")
            else:
                body.append(f"    {local} = ({ctype} * len({name}))(*{name})")
            call.append(local)
            if arg.intent in ("out", "inout"):
                outputs.append(f"list({local})")
        else:
            if arg.intent != "out":
                params.append(name)
            body.append(f"    {local} = {ctype}({'' if arg.intent == 'out' else name})")
            call.append(f"ctypes.byref({local})")
            if arg.intent in ("out", "inout"):
                outputs.append(f"{local}.value")
    if b.result is not None and b.result.dims:
        size = " * ".join(b.result.dims)
        body.append(f"    _result = (ctypes.{b.result.ctype.ctypes} * {size})()")
        call.append("_result")
    call += [f"len({_py(a.name)})" for a in b.arguments for d in a.dims if d == ":"]
    invocation = f"_lib.{b.c_name}({', '.join(call)})"
    returned = []
    if b.result is not None and not b.result.dims:
        body.append(f"    _value = {invocation}")
        returned.append("_value")
    else:
        body.append(f"    {invocation}")
        if b.result is not None:
            returned.append("list(_result)")
    returned += outputs
    result = ", ".join(returned) if len(returned) > 1 else (returned[0] if returned else "None")
    return [f"def {_py(b.procedure)}({', '.join(params)}):", f'    """{_doc(b)}"""', *body, f"    return {result}"]


def report(bindings: list[Binding]) -> str:
    bound = [b for b in bindings if not b.skipped]
    lines = [f"{len(bound)} of {len(bindings)} procedure(s) bound"]
    lines += [f"  bound    {b.module}::{b.procedure} -> {b.c_name}" for b in bound]
    lines += [f"  skipped  {b.module}::{b.procedure}: {b.skipped}" for b in bindings if b.skipped]
    return "\n".join(lines)
