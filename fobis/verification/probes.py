"""probes.py — extract named quantities (numbers, arrays) from what a run produced.

A probe is declared in a fobos case as ``name : kind arguments...``:

- ``regex SOURCE PATTERN [first|last|all]``: the first group of PATTERN (Python syntax) in SOURCE, ``stdout``,
  ``stderr`` or a file of the run directory; ``all`` (default) collects every match;
- ``column PATH N [first|last|all|ROW]``: the N-th (1-based) whitespace-separated column of a text file, lines
  that do not hold a number there (headers, comments) skipped;
- ``json PATH KEYPATH``: a value of a JSON file, ``$.a.b[0]`` or ``a.b.0``;
- ``hdf5 PATH DATASET``: an HDF5 dataset, through h5py when importable, else the ``h5dump`` tool;
- ``binary PATH KIND [SHAPE] [record N|stream]``: values of KIND (``real32``, ``real64``, ``int32``, ``int64``)
  from a Fortran unformatted sequential file (record N, default 1, with 4-byte record markers as written by
  gfortran, ifx and nvfortran by default) or a stream/raw file; SHAPE ``[nx,ny]`` is recorded, column-major;
- ``exit``: the exit status of the program.

The short form ``quantities = stdout`` collects every ``name = number`` (or ``name: number``) line of stdout.

Numbers are parsed the Fortran way too: ``1.5D+03``, ``NaN``, ``Infinity``, and fields glued by a missing space
(``1.0E+00-2.5E-01``) are split.
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
import math
import os
import re
import shlex
import shutil
import struct
import subprocess
from dataclasses import dataclass, field

KINDS = ("regex", "column", "json", "hdf5", "binary", "exit")
BINARY_KINDS = {"real32": ("f", 4), "real64": ("d", 8), "int32": ("i", 4), "int64": ("q", 8)}
_NUMBER = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eEdD][-+]?\d+)?|[-+]?(?<![A-Za-z])(?:nan|infinity|inf)(?![A-Za-z])"
_NUMBER_RE = re.compile(_NUMBER, re.IGNORECASE)
_STDOUT_LINE = re.compile(rf"^\s*([A-Za-z_][\w.%-]*)\s*[=:]\s*({_NUMBER})\s*$", re.IGNORECASE)
_SHAPE = re.compile(r"^\[([\w\s,]+)\]$")


class ProbeError(Exception):
    """A quantity could not be extracted (missing file, no match, bad declaration)."""


def to_float(text: str) -> float:
    """A number as Fortran prints it (``1.5D+03``, ``NaN``, ``-Infinity``)."""
    value = text.strip().lower().replace("d", "e")
    if value.lstrip("+-") in ("nan", "inf", "infinity"):
        return float(value.replace("infinity", "inf"))
    return float(value)


def numbers(text: str) -> list[float]:
    """Every number in *text*, glued Fortran fields included (``1.0E+00-2.5E-01`` -> two numbers)."""
    return [to_float(m.group(0)) for m in _NUMBER_RE.finditer(text)]


@dataclass
class Quantity:
    """A named value or array; ``shape`` is None for a scalar or a plain list."""

    name: str
    values: list[float]
    shape: list[int] | None = None

    def to_dict(self) -> dict:
        data: dict = {"values": [json_number(v) for v in self.values]}
        if self.shape:
            data["shape"] = self.shape
        return data


def json_number(value: float) -> float | str:
    """JSON has no NaN/Infinity: they are written as the strings ``nan``, ``inf``, ``-inf``."""
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    return value


def from_json_number(value: float | str) -> float:
    return float(value) if isinstance(value, str) else value


@dataclass(frozen=True)
class Probe:
    """A declared quantity: its name, kind and arguments."""

    name: str
    kind: str
    args: tuple[str, ...] = field(default_factory=tuple)

    @property
    def text(self) -> str:
        return f"{self.name} : {self.kind} {' '.join(shlex.quote(a) for a in self.args)}".strip()


def parse_probes(spec: str) -> list[Probe]:
    """The probes of a ``quantities`` value: one per line ``name : kind args``, or ``stdout`` alone.

    Raises
    ------
    ProbeError
        A line is malformed or names an unknown kind.
    """
    probes = []
    for raw in spec.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line == "stdout":
            probes.append(Probe("*", "stdout"))
            continue
        name, sep, rest = line.partition(":")
        if not sep or not name.strip():
            raise ProbeError(f"quantity '{line}': expected 'name : kind arguments'")
        try:
            words = shlex.split(rest)
        except ValueError as exc:
            raise ProbeError(f"quantity '{line}': {exc}") from exc
        if not words or words[0] not in KINDS:
            raise ProbeError(f"quantity '{line}': kind must be one of {', '.join(KINDS)}")
        probes.append(Probe(name.strip(), words[0], tuple(words[1:])))
    return probes


@dataclass
class RunOutput:
    """What a run left: its directory, stdout, stderr and exit status."""

    rundir: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None


def _path(output: RunOutput, path: str) -> str:
    full = path if os.path.isabs(path) else os.path.join(output.rundir, path)
    if not os.path.isfile(full):
        raise ProbeError(f"file {path} not found in the run directory")
    return full


def _read(output: RunOutput, source: str) -> str:
    if source == "stdout":
        return output.stdout
    if source == "stderr":
        return output.stderr
    with open(_path(output, source), encoding="utf-8", errors="replace") as handle:
        return handle.read()


def _select(values: list[float], selector: str, what: str) -> list[float]:
    if not values:
        raise ProbeError(f"{what}: no value found")
    if selector == "all":
        return values
    if selector == "first":
        return values[:1]
    if selector == "last":
        return values[-1:]
    if selector.lstrip("-").isdigit():
        index = int(selector)
        index = index - 1 if index > 0 else index
        try:
            return [values[index]]
        except IndexError:
            raise ProbeError(f"{what}: row {selector} out of range ({len(values)} rows)") from None
    raise ProbeError(f"{what}: selector must be first, last, all or a row number")


def _regex(probe: Probe, output: RunOutput) -> Quantity:
    if len(probe.args) < 2:
        raise ProbeError(f"{probe.name}: regex SOURCE PATTERN [first|last|all]")
    source, pattern = probe.args[0], probe.args[1]
    selector = probe.args[2] if len(probe.args) > 2 else "all"
    try:
        compiled = re.compile(pattern, re.MULTILINE)
    except re.error as exc:
        raise ProbeError(f"{probe.name}: bad pattern: {exc}") from exc
    found = []
    for match in compiled.finditer(_read(output, source)):
        text = match.group(1) if compiled.groups else match.group(0)
        found += numbers(text)
    return Quantity(probe.name, _select(found, selector, probe.name))


def _column(probe: Probe, output: RunOutput) -> Quantity:
    if len(probe.args) < 2 or not probe.args[1].isdigit():
        raise ProbeError(f"{probe.name}: column PATH N [first|last|all|ROW]")
    column = int(probe.args[1]) - 1
    selector = probe.args[2] if len(probe.args) > 2 else "all"
    found = []
    for line in _read(output, probe.args[0]).splitlines():
        if line.lstrip().startswith(("#", "!", "%")):
            continue
        fields = line.split()
        if len(fields) > column:
            try:
                found.append(to_float(fields[column]))
            except ValueError:
                continue
    return Quantity(probe.name, _select(found, selector, f"{probe.name} (column {column + 1})"))


def _json_value(data, keypath: str):
    keys = [k for k in re.split(r"[.\[\]]+", keypath.removeprefix("$")) if k]
    for key in keys:
        if isinstance(data, list):
            if not key.lstrip("-").isdigit():
                raise ProbeError(f"key {key!r} applied to a list")
            data = data[int(key)]
        elif isinstance(data, dict):
            if key not in data:
                raise ProbeError(f"key {key!r} not found")
            data = data[key]
        else:
            raise ProbeError(f"key {key!r} applied to a value")
    return data


def _flatten(data) -> tuple[list[float], list[int] | None]:
    if isinstance(data, bool) or data is None:
        raise ProbeError(f"not a number: {data!r}")
    if isinstance(data, int | float):
        return [float(data)], None
    if isinstance(data, str):
        return [to_float(data)], None
    if isinstance(data, list):
        values, shapes = [], []
        for item in data:
            inner, shape = _flatten(item)
            values += inner
            shapes.append(shape)
        shape = [len(data), *(shapes[0] or [])] if shapes and all(s == shapes[0] for s in shapes) else [len(values)]
        return values, shape
    raise ProbeError(f"not a number or an array: {type(data).__name__}")


def _json(probe: Probe, output: RunOutput) -> Quantity:
    if len(probe.args) != 2:
        raise ProbeError(f"{probe.name}: json PATH KEYPATH")
    try:
        data = json.loads(_read(output, probe.args[0]))
        values, shape = _flatten(_json_value(data, probe.args[1]))
    except (ValueError, IndexError) as exc:
        raise ProbeError(f"{probe.name}: {exc}") from exc
    except ProbeError as exc:
        raise ProbeError(f"{probe.name}: {exc}") from exc
    return Quantity(probe.name, values, shape)


def _hdf5(probe: Probe, output: RunOutput) -> Quantity:
    if len(probe.args) != 2:
        raise ProbeError(f"{probe.name}: hdf5 PATH DATASET")
    path, dataset = _path(output, probe.args[0]), probe.args[1]
    try:
        import h5py  # optional: not in the standalone archive
    except ImportError:
        h5py = None
    if h5py is not None:
        with h5py.File(path, "r") as handle:
            if dataset not in handle:
                raise ProbeError(f"{probe.name}: dataset {dataset} not in {probe.args[0]}")
            data = handle[dataset][()]
        shape = list(getattr(data, "shape", ())) or None
        flat = data.reshape(-1).tolist() if shape else [data.item() if hasattr(data, "item") else data]
        return Quantity(probe.name, [float(v) for v in flat], shape)
    tool = shutil.which("h5dump")
    if tool is None:
        raise ProbeError(f"{probe.name}: reading HDF5 needs h5py or the h5dump tool")
    done = subprocess.run(
        [tool, "-d", dataset, "-y", "-w", "0", "-m", "%.17g", path], capture_output=True, text=True, timeout=300
    )
    if done.returncode != 0:
        raise ProbeError(f"{probe.name}: h5dump: {(done.stderr or done.stdout).strip()[:300]}")
    return parse_h5dump(probe.name, done.stdout)


def parse_h5dump(name: str, text: str) -> Quantity:
    """The values of ``h5dump -d DATASET -y -w 0`` output (shape from its DATASPACE line, row-major as stored)."""
    shape = None
    space = re.search(r"DATASPACE\s+SIMPLE\s*\{\s*\(\s*([\d,\s]+)\)", text)
    if space:
        shape = [int(v) for v in space.group(1).split(",")]
    data = text.split("DATA {", 1)
    if len(data) < 2:
        raise ProbeError(f"{name}: no DATA in the h5dump output")
    body = data[1].rsplit("}", 2)[0]
    return Quantity(name, numbers(body), shape)


def _binary(probe: Probe, output: RunOutput) -> Quantity:
    if len(probe.args) < 2 or probe.args[1] not in BINARY_KINDS:
        raise ProbeError(f"{probe.name}: binary PATH {'|'.join(BINARY_KINDS)} [[shape]] [record N|stream]")
    code, size = BINARY_KINDS[probe.args[1]]
    rest = list(probe.args[2:])
    shape = None
    if rest and (match := _SHAPE.match(rest[0])):
        try:
            shape = [int(v) for v in match.group(1).replace(" ", "").split(",")]
        except ValueError:
            raise ProbeError(f"{probe.name}: shape must be integers, e.g. [10,20]") from None
        rest = rest[1:]
    with open(_path(output, probe.args[0]), "rb") as handle:
        raw = handle.read()
    if rest[:1] == ["stream"]:
        payload = raw
    else:
        record = int(rest[1]) if rest[:1] == ["record"] and len(rest) > 1 and rest[1].isdigit() else 1
        payload = _record(raw, record, probe.name)
    if len(payload) % size:
        raise ProbeError(f"{probe.name}: {len(payload)} bytes is not a whole number of {probe.args[1]} values")
    values = [float(v) for v in struct.unpack(f"<{len(payload) // size}{code}", payload)]
    if shape and math.prod(shape) != len(values):
        raise ProbeError(f"{probe.name}: shape {shape} holds {math.prod(shape)} values, the data {len(values)}")
    return Quantity(probe.name, values, shape)


def _record(raw: bytes, number: int, name: str) -> bytes:
    """Record *number* (1-based) of a Fortran unformatted sequential file (little-endian 4-byte markers)."""
    position, current = 0, 0
    while position + 4 <= len(raw):
        (length,) = struct.unpack("<i", raw[position : position + 4])
        if length < 0 or position + 8 + length > len(raw):
            raise ProbeError(f"{name}: not a Fortran sequential unformatted file (or a subrecord marker)")
        current += 1
        if current == number:
            return raw[position + 4 : position + 4 + length]
        position += 8 + length
    raise ProbeError(f"{name}: record {number} not found ({current} records)")


def _stdout_lines(output: RunOutput) -> list[Quantity]:
    found: dict[str, list[float]] = {}
    for line in output.stdout.splitlines():
        if match := _STDOUT_LINE.match(line):
            found.setdefault(match.group(1), []).append(to_float(match.group(2)))
    return [Quantity(name, values) for name, values in found.items()]


def extract(probes: list[Probe], output: RunOutput) -> tuple[list[Quantity], dict[str, str]]:
    """Every quantity the *probes* find in *output*, and the errors of those that failed (name -> reason)."""
    handlers = {"regex": _regex, "column": _column, "json": _json, "hdf5": _hdf5, "binary": _binary}
    quantities: list[Quantity] = []
    errors: dict[str, str] = {}
    for probe in probes:
        try:
            if probe.kind == "stdout":
                quantities += _stdout_lines(output)
            elif probe.kind == "exit":
                if output.exit_code is None:
                    raise ProbeError(f"{probe.name}: the program did not finish")
                quantities.append(Quantity(probe.name, [float(output.exit_code)]))
            else:
                quantities.append(handlers[probe.kind](probe, output))
        except ProbeError as exc:
            errors[probe.name] = str(exc)
        except OSError as exc:
            errors[probe.name] = f"{probe.name}: {exc}"
    return quantities, errors
