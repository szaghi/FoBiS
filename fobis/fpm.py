"""fpm.py — interoperability with the Fortran Package Manager (phase V12 of PLAN-verification.md).

``fobis fpm import`` writes a fobos from an ``fpm.toml``; ``fobis fpm export`` writes an ``fpm.toml`` from a fobos
and the facts of its sources. Each side keeps what the other can express and lists, as notes, what it cannot (fobos
modes, templates and rules; registry dependencies). Flags are not invented: an imported fobos holds fpm's own flags for
the chosen compiler and this OS — the manifest's features (``[feature:NAME]`` sections), fpm's built-in ``debug`` and
``release`` features where the manifest has none, the flags of its ``[fortran]`` table — and one mode per profile.

TOML is read with ``tomllib`` (Python 3.11+) and otherwise with `parse_toml`, a reader of the subset manifests use
(tables, arrays of tables, dotted keys, strings, numbers, booleans, arrays, inline tables): the zipapp stays
stdlib-only on Python 3.10.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any

METAPACKAGE_KEYS = {"mpi": "mpi", "openmp": "openmp"}  # fpm metapackage -> fobos mode key set to True


class FpmError(Exception):
    """An fpm manifest cannot be read, or a file would be overwritten."""


# ── TOML ───────────────────────────────────────────────────────────────────────


_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
_WORD = re.compile(r"[^\s,\]}#]+")
_INTEGER = re.compile(r"[+-]?(0x[0-9a-fA-F]+|0o[0-7]+|0b[01]+|\d+)")
_ESCAPES = {"b": "\b", "t": "\t", "n": "\n", "f": "\f", "r": "\r", '"': '"', "\\": "\\"}


class _Reader:
    """A cursor over TOML text: the value grammar shared by keys, arrays and inline tables."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0

    def error(self, message: str) -> FpmError:
        line = self.text.count("\n", 0, self.pos) + 1
        return FpmError(f"TOML line {line}: {message}")

    def peek(self) -> str:
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def skip(self, newlines: bool = False) -> None:
        """Spaces (and newlines and comments when *newlines*); a comment always ends the line."""
        while self.pos < len(self.text):
            char = self.text[self.pos]
            if char in " \t" or (newlines and char in "\r\n"):
                self.pos += 1
            elif char == "#":
                while self.pos < len(self.text) and self.text[self.pos] != "\n":
                    self.pos += 1
            else:
                break

    def key(self) -> list[str]:
        parts = []
        while True:
            self.skip()
            if self.peek() in ("'", '"'):
                parts.append(self.string())
            else:
                match = _BARE_KEY.match(self.text, self.pos)
                if not match:
                    raise self.error("a key is expected")
                parts.append(match.group(0))
                self.pos = match.end()
            self.skip()
            if self.peek() != ".":
                return parts
            self.pos += 1

    def string(self) -> str:
        quote = self.text[self.pos]
        if self.text.startswith(quote * 3, self.pos):
            end = self.text.find(quote * 3, self.pos + 3)
            if end < 0:
                raise self.error("unterminated multi-line string")
            body = self.text[self.pos + 3 : end]
            self.pos = end + 3
            body = body[1:] if body.startswith("\n") else body
            if quote == "'":
                return body
            return self._unescape(re.sub(r"\\[ \t]*\r?\n\s*", "", body))  # line-ending backslash joins lines
        end = self.pos + 1
        while end < len(self.text) and self.text[end] != quote:
            end += 2 if quote == '"' and self.text[end] == "\\" else 1
        if end >= len(self.text):
            raise self.error("unterminated string")
        body = self.text[self.pos + 1 : end]
        self.pos = end + 1
        return body if quote == "'" else self._unescape(body)

    @staticmethod
    def _unescape(body: str) -> str:
        out, i = [], 0
        while i < len(body):
            if body[i] == "\\" and i + 1 < len(body):
                code = body[i + 1]
                if code in "uU":
                    width = 4 if code == "u" else 8
                    out.append(chr(int(body[i + 2 : i + 2 + width], 16)))
                    i += 2 + width
                    continue
                out.append(_ESCAPES.get(code, code))
                i += 2
            else:
                out.append(body[i])
                i += 1
        return "".join(out)

    def array(self) -> list:
        self.pos += 1
        items = []
        while True:
            self.skip(newlines=True)
            if self.peek() == "]":
                self.pos += 1
                return items
            items.append(self.value())
            self.skip(newlines=True)
            if self.peek() == ",":
                self.pos += 1
            elif self.peek() != "]":
                raise self.error("',' or ']' expected in an array")

    def inline_table(self) -> dict:
        self.pos += 1
        table: dict[str, Any] = {}
        self.skip()
        if self.peek() == "}":
            self.pos += 1
            return table
        while True:
            keys = self.key()
            if self.peek() != "=":
                raise self.error("'=' expected in an inline table")
            self.pos += 1
            _assign(table, keys, self.value(), self)
            self.skip()
            if self.peek() == ",":
                self.pos += 1
            elif self.peek() == "}":
                self.pos += 1
                return table
            else:
                raise self.error("',' or '}' expected in an inline table")

    def value(self) -> Any:
        self.skip()
        char = self.peek()
        if char in ("'", '"'):
            return self.string()
        if char == "[":
            return self.array()
        if char == "{":
            return self.inline_table()
        match = _WORD.match(self.text, self.pos)
        if not match:
            raise self.error("a value is expected")
        self.pos = match.end()
        word = match.group(0)
        if word in ("true", "false"):
            return word == "true"
        number = word.replace("_", "")
        try:
            return int(number, 0) if _INTEGER.fullmatch(number) else float(number)
        except ValueError:
            return word  # a date or time: kept as written


def _assign(table: dict, keys: list[str], value: Any, reader: _Reader) -> None:
    for key in keys[:-1]:
        table = table.setdefault(key, {})
        if not isinstance(table, dict):
            raise reader.error(f"key {key!r} is not a table")
    if keys[-1] in table:
        raise reader.error(f"duplicate key {'.'.join(keys)!r}")
    table[keys[-1]] = value


def _descend(table: dict, keys: list[str]) -> dict:
    for key in keys:
        table = table.setdefault(key, {})
        table = table[-1] if isinstance(table, list) else table
    return table


def parse_toml(text: str) -> dict:
    """The TOML subset of package manifests (see the module docstring)."""
    reader = _Reader(text)
    root: dict[str, Any] = {}
    current = root
    while True:
        reader.skip(newlines=True)
        if reader.pos >= len(text):
            return root
        if text.startswith("[[", reader.pos):
            reader.pos += 2
            keys = reader.key()
            if not text.startswith("]]", reader.pos):
                raise reader.error("']]' expected")
            reader.pos += 2
            array = _descend(root, keys[:-1]).setdefault(keys[-1], [])
            if not isinstance(array, list):
                raise reader.error(f"{'.'.join(keys)!r} is not an array of tables")
            current = {}
            array.append(current)
        elif reader.peek() == "[":
            reader.pos += 1
            keys = reader.key()
            if reader.peek() != "]":
                raise reader.error("']' expected")
            reader.pos += 1
            current = _descend(root, keys)
        else:
            keys = reader.key()
            if reader.peek() != "=":
                raise reader.error("'=' expected")
            reader.pos += 1
            _assign(current, keys, reader.value(), reader)
        reader.skip()
        if reader.peek() not in ("", "\n", "\r"):
            raise reader.error("end of line expected")


def load_toml(text: str) -> dict:
    """``tomllib`` when available (Python 3.11+), else `parse_toml`."""
    try:
        import tomllib
    except ImportError:
        return parse_toml(text)
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise FpmError(f"TOML: {exc}") from exc


def _toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k} = {_toml_value(v)}" for k, v in value.items()) + " }"
    return _toml_string(str(value))


# ── fpm.toml -> fobos ──────────────────────────────────────────────────────────


@dataclass
class Translation:
    """A translated file and what could not be translated."""

    text: str
    notes: list[str] = field(default_factory=list)


def _source_path(path: str) -> str:
    norm = os.path.normpath(path).replace(os.sep, "/")
    return "./" if norm == "." else f"./{norm}/"


def _targets(manifest: dict, kind: str, default_dir: str, auto: bool, root: str) -> list[dict]:
    """The ``[[executable]]``/``[[test]]``/``[[example]]`` entries, or the auto-discovered default directory."""
    entries = manifest.get(kind, [])
    if entries:
        return [{"name": e.get("name", ""), "dir": e.get("source-dir", default_dir)} for e in entries]
    if auto and os.path.isdir(os.path.join(root, default_dir)):
        return [{"name": "", "dir": default_dir}]
    return []


def _module_file(root: str, source_dir: str, module: str) -> str:
    """The file of *source_dir* defining ``module <module>`` (case-insensitive), '' when none."""
    pattern = re.compile(rf"^\s*module\s+{re.escape(module)}\s*(!.*)?$", re.I | re.M)
    for folder, _, files in sorted(os.walk(os.path.join(root, source_dir))):
        for name in sorted(files):
            if os.path.splitext(name)[1].lower() in (".f90", ".f", ".f95", ".f03", ".f08"):
                path = os.path.join(folder, name)
                with open(path, encoding="utf-8", errors="replace") as handle:
                    if pattern.search(handle.read()):
                        return os.path.relpath(path, root).replace(os.sep, "/")
    return ""


# fpm's compiler keys, in the order fpm matches them (``match_compiler_type``: the name itself, or the name contained
# in the key, so ``amdflang`` is flang and ``gfortran-13`` is gfortran); the second item is fpm's compiler id
_FPM_COMPILER_NAMES = (
    ("gfortran", "gfortran"),
    ("f95", "f95"),
    ("caf", "caf"),
    ("ifort", "ifort"),
    ("ifx", "ifx"),
    ("nvfortran", "nvfortran"),
    ("pgfortran", "pgi"),
    ("pgf90", "pgi"),
    ("pgf95", "pgi"),
    ("nagfor", "nagfor"),
    ("flang-classic", "flang-classic"),
    ("flang-new", "flang"),
    ("flang", "flang"),
    ("amdflang", "flang"),
    ("f18", "f18"),
    ("xlf90", "xlf90"),
    ("crayftn", "crayftn"),
    ("lfc", "lfc"),
    ("lfortran", "lfortran"),
)
FPM_OS = ("linux", "macos", "windows", "cygwin", "solaris", "freebsd", "openbsd")
# the fpm compiler command of each FoBiS compiler family (g95 and custom have none)
FPM_COMPILER_OF = {
    "gnu": "gfortran",
    "opencoarrays-gnu": "caf",
    "intel": "ifort",
    "intel_nextgen": "ifx",
    "nvfortran": "nvfortran",
    "pgi": "pgfortran",
    "nag": "nagfor",
    "amd": "amdflang",
    "lfortran": "lfortran",
    "ibm": "xlf90",
}
# the FoBiS compiler family of an fpm compiler id, for the notes naming another compiler's flags
FOBIS_COMPILER_OF = {fpm: fobis for fobis, fpm in FPM_COMPILER_OF.items()} | {"flang": "amd", "pgi": "pgi"}
# FoBiS's implicit feature names (openmp, mpi, ...): an fpm feature named so is renamed fpm-NAME, or it would replace
# the implicit one, and ``default``, special in a fobos [features] section
_RESERVED_FEATURES = {
    "openmp",
    "omp",
    "mpi",
    "coarray",
    "coverage",
    "profile",
    "openmp_offload",
    "omp_offload",
    "default",
}
# fpm's built-in debug and release features, used when the manifest defines none of that name: (compiler id, OS or
# None, Fortran flags, C flags), as in fpm's feature_collection.f90 (fpm main 5fa4649, 2026-02-19)
_GNU_DEBUG = (
    "-Wall -Wextra -Wimplicit-interface -Wno-external-argument-mismatch -fPIC -fmax-errors=1 -g -fcheck=bounds "
    "-fcheck=array-temps"
)
_INTEL_DEBUG = "-warn all -check all -error-limit 1 -O0 -g -assume byterecl -traceback"
_INTEL_RELEASE = "-pc64 -align all -error-limit 1 -reentrancy threaded -nogen-interfaces -assume byterecl"
_INTEL_WINDOWS_RELEASE = "/fp:precise /align:all /error-limit:1 /reentrancy:threaded /nogen-interfaces /assume:byterecl"
FPM_DEFAULT_FEATURES = {
    "debug": (
        ("caf", None, _GNU_DEBUG + " -fbacktrace", "-fPIC"),
        ("gfortran", None, _GNU_DEBUG + " -fbacktrace -fcoarray=single", "-Wall -Wextra -fPIC -fmax-errors=1 -g"),
        ("f95", None, _GNU_DEBUG + " -Wno-maybe-uninitialized -Wno-uninitialized -fbacktrace", "-fPIC"),
        ("nvfortran", None, "-Minform=inform -Mbackslash -g -Mbounds -Mchkptr -Mchkstk -traceback", "-fPIC"),
        ("ifort", None, _INTEL_DEBUG, "-fPIC"),
        ("ifort-windows", "windows", "/warn:all /check:all /error-limit:1 /Od /Z7 /assume:byterecl /traceback", ""),
        ("ifx", None, _INTEL_DEBUG, "-fPIC"),
        ("ifx-windows", "windows", "/warn:all /check:all /error-limit:1 /Od /Z7 /assume:byterecl", ""),
        ("lfortran", None, "", "-fPIC"),
    ),
    "release": (
        ("caf", None, "-O3 -Wimplicit-interface -fPIC -fmax-errors=1 -funroll-loops", "-fPIC"),
        (
            "gfortran",
            None,
            "-O3 -Wimplicit-interface -fPIC -fmax-errors=1 -funroll-loops -fcoarray=single",
            "-O3 -fPIC -fmax-errors=1 -funroll-loops",
        ),
        ("f95", None, "-O3 -Wimplicit-interface -fPIC -fmax-errors=1 -ffast-math -funroll-loops", "-fPIC"),
        ("nvfortran", None, "-Mbackslash", "-fPIC"),
        ("ifort", "linux", "-fp-model precise " + _INTEL_RELEASE, "-fPIC"),
        ("ifort-windows", "windows", _INTEL_WINDOWS_RELEASE, ""),
        ("ifx", "linux", "-fp-model=precise " + _INTEL_RELEASE, "-fPIC"),
        ("ifx-windows", "windows", _INTEL_WINDOWS_RELEASE, ""),
        ("nagfor", None, "-O4 -coarray=single -PIC", "-fPIC"),
        ("lfortran", None, "--fast", "-fPIC"),
    ),
}
# the flags fpm adds to every Fortran compile for the [fortran] table (fpm_compiler.F90 get_feature_flag), by id
_GNU_FORM = {"no-implicit-typing": "-fimplicit-none", "no-implicit-external": "-Werror=implicit-interface"}
_GNU_FORM |= {"free": "-ffree-form", "fixed": "-ffixed-form"}
FPM_FORTRAN_FLAGS = {
    "gfortran": _GNU_FORM,
    "caf": _GNU_FORM,
    "f95": _GNU_FORM,
    "pgi": {"free": "-Mfree", "fixed": "-Mfixed"},
    "nvfortran": {"free": "-Mfree", "fixed": "-Mfixed"},
    "flang-classic": {"free": "-Mfree", "fixed": "-Mfixed"},
    "nagfor": {"free": "-free", "fixed": "-fixed", "no-implicit-typing": "-u"},
    "ifort": {"free": "-free", "fixed": "-fixed"},
    "ifort-macos": {"free": "-free", "fixed": "-fixed"},
    "ifx": {"free": "-free", "fixed": "-fixed"},
    "ifort-windows": {"free": "/free", "fixed": "/fixed"},
    "ifx-windows": {"free": "/free", "fixed": "/fixed"},
    "crayftn": {"no-implicit-typing": "-dl", "implicit-typing": "-el", "free": "-ffree", "fixed": "-ffixed"},
    "lfortran": {"implicit-typing": "--implicit-typing", "implicit-external": "--implicit-interface"}
    | {"fixed": "--fixed-form"},
    "flang": {"free": "-ffree-form", "fixed": "-ffixed-form", "no-implicit-typing": "-fimplicit-none"},
}


# fpm's preprocessor flag, added to every Fortran compile when the manifest uses cpp (fpm.f90 has_cpp)
FPM_CPP_FLAG = {"gfortran": "-cpp", "caf": "-cpp", "f95": "-cpp", "nvfortran": "-cpp", "flang": "-cpp"}
FPM_CPP_FLAG |= {"ifort": "-fpp", "ifort-macos": "-fpp", "ifx": "-fpp", "nagfor": "-fpp", "lfortran": "--cpp"}
FPM_CPP_FLAG |= {"ifort-windows": "/fpp", "ifx-windows": "/fpp"}


def _uses_cpp(manifest: dict) -> bool:
    """fpm preprocesses every Fortran file when ``[preprocess] cpp`` is set, or a feature (any variant) sets it."""

    def walk(node: Any) -> bool:
        if not isinstance(node, dict):
            return False
        if isinstance(node.get("preprocess"), dict) and "cpp" in node["preprocess"]:
            return True
        return any(walk(value) for value in node.values())

    return "cpp" in (manifest.get("preprocess") or {}) or walk(manifest.get("features") or {})


def current_os() -> str:
    """fpm's name of this operating system (the OS-specific feature variants that apply)."""
    platform = sys.platform
    for prefix, name in (("linux", "linux"), ("darwin", "macos"), ("win32", "windows"), ("cygwin", "cygwin")):
        if platform.startswith(prefix):
            return name
    for name in ("freebsd", "openbsd"):
        if platform.startswith(name):
            return name
    return "solaris" if platform.startswith("sunos") else platform


def fpm_compiler(name: str, os_name: str) -> str | None:
    """fpm's compiler id of a manifest key or compiler command (``all`` for all, None when it names none); Intel's ids
    depend on the OS, as in fpm."""
    key = name.lower()
    if key == "all":
        return "all"
    for expected, ident in _FPM_COMPILER_NAMES:
        if key == expected or expected in os.path.basename(key):
            if ident in ("ifort", "ifx") and os_name in ("windows", "cygwin"):
                return ident + "-windows"
            return "ifort-macos" if ident == "ifort" and os_name == "macos" else ident
    return None


@dataclass
class _Variant:
    compiler: str | None  # fpm compiler id, None for all
    os: str | None  # None for all
    data: dict


def _variants(table: dict, os_name: str) -> list[_Variant]:
    """A feature's variants: ``name.flags`` (all), ``name.<compiler>.flags``, ``name.<os>.flags`` and both nested; the
    one for all platforms first, the others in the manifest's order (fpm merges them so)."""
    found: list[_Variant] = []

    def walk(node: dict, compiler: str | None, osn: str | None) -> None:
        data = {}
        for key, value in node.items():
            low = key.lower()
            if low in FPM_OS or low == "all":
                if not isinstance(value, dict):
                    raise FpmError(f"{key} must be a table")
                walk(value, compiler, osn if low == "all" else low)
            elif fpm_compiler(key, os_name) and isinstance(value, dict):
                ident = fpm_compiler(key, os_name)
                walk(value, compiler if ident == "all" else ident, osn)
            else:
                data[key] = value
        if data:
            found.append(_Variant(compiler, osn, data))

    walk(table, None, None)
    return sorted(found, key=lambda v: v.compiler is not None or v.os is not None)


@dataclass
class _Feature:
    """A feature resolved for one compiler and OS."""

    flags: list[str] = field(default_factory=list)
    c_flags: list[str] = field(default_factory=list)
    link_flags: list[str] = field(default_factory=list)
    macros: list[str] = field(default_factory=list)
    metapackages: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    untranslated: list[str] = field(default_factory=list)
    other_compilers: set[str] = field(default_factory=set)
    other_os: set[str] = field(default_factory=set)


def _as_list(value: Any) -> list[str]:
    return [value] if isinstance(value, str) else [str(v) for v in value or []]


def _resolve(variants: list[_Variant], compiler: str, os_name: str) -> _Feature:
    feature = _Feature()
    for variant in variants:
        if variant.compiler not in (None, compiler):
            feature.other_compilers.add(variant.compiler)
            continue
        if variant.os not in (None, os_name):
            feature.other_os.add(variant.os)
            continue
        for key, value in variant.data.items():
            if key == "flags":
                feature.flags.append(str(value))
            elif key == "c-flags":
                feature.c_flags.append(str(value))
            elif key == "link-time-flags":
                feature.link_flags.append(str(value))
            elif key == "requires":
                feature.requires += _as_list(value)
            elif key == "description":
                continue
            elif key == "preprocess" and set(value) <= {"cpp"} and set(value.get("cpp", {})) <= {"macros"}:
                feature.macros += _as_list(value.get("cpp", {}).get("macros"))
            elif key == "dependencies" and all(
                isinstance(spec, str) and dep in METAPACKAGE_KEYS for dep, spec in value.items()
            ):
                feature.metapackages += list(value)
            else:
                feature.untranslated.append(key)
    return feature


def _macro(macro: str, version: str) -> str:
    """fpm's ``NAME={version}`` expansion (fpm_compiler.F90 get_macros): a value in braces naming ``version`` becomes
    the package's version; anything else is passed as written."""
    name, _, value = macro.partition("=")
    if value.startswith("{") and value.endswith("}") and "version" in value:
        return f"{name}={version}"
    return macro


def _feature_flags(feature: _Feature) -> str:
    words = [*feature.flags, *(f"-D{m}" for m in feature.macros), *(f"@{m}" for m in feature.metapackages)]
    return " ".join(w for w in words if w.strip())


def _features_and_profiles(manifest: dict, compiler: str, os_name: str, notes: list[str]):
    """The manifest's features resolved for *compiler* on *os_name* ({fobos name: _Feature}, fpm's built-in debug and
    release ones for those it lacks) and its profiles ({name: [fobos feature names]}, debug and release always, the
    ``default`` profile's features first in both)."""
    features: dict[str, _Feature] = {}
    names: dict[str, str] = {}  # fpm feature -> fobos feature
    for name, table in (manifest.get("features") or {}).items():
        if not isinstance(table, dict):
            notes.append(f"[features] {name} = {table!r}: a feature must be a table (flags, preprocess, ...)")
            continue
        fobos_name = f"fpm-{name}" if name in _RESERVED_FEATURES else name
        if fobos_name != name:
            notes.append(f"feature {name} is named {fobos_name} in the fobos: {name} is a FoBiS feature already")
        names[name] = fobos_name
        features[fobos_name] = _resolve(_variants(table, os_name), compiler, os_name)
    builtin = set()
    for name, rows in FPM_DEFAULT_FEATURES.items():
        if name not in names:
            builtin.add(name)
            variants = [_Variant(c, o, {"flags": f, "c-flags": cf}) for c, o, f, cf in rows]
            names[name] = name
            features[name] = _resolve(variants, compiler, os_name)
            features[name].other_compilers.clear()  # fpm's own table: nothing to tell
            features[name].other_os.clear()
    elsewhere: dict[str, list[str]] = {}  # another compiler -> the features with flags for it
    for name, feature in features.items():
        if feature.untranslated:
            notes.append(f"feature {name}: {', '.join(sorted(set(feature.untranslated)))} not translated")
        feature.requires = [names.get(r, r) for r in feature.requires]
        for other in sorted(feature.other_compilers):
            elsewhere.setdefault(other, []).append(name)
        if feature.other_os:
            notes.append(f"feature {name} has flags for {', '.join(sorted(feature.other_os))}, not for {os_name}")
    for other, members in elsewhere.items():
        family = FOBIS_COMPILER_OF.get(other.split("-")[0] if other.startswith(("ifort", "ifx")) else other)
        how = f"import again with --compiler {family}" if family else "FoBiS has no such compiler family"
        notes.append(f"features {', '.join(members)} have flags for {other} too: {how}")
    profiles: dict[str, list[str]] = {"debug": ["debug"], "release": ["release"]}
    for name, members in (manifest.get("profiles") or {}).items():
        if not isinstance(members, list):
            notes.append(f"[profiles] {name}: not a list of features (an older fpm syntax), not translated")
            continue
        profiles[name] = [str(m) for m in members]
    default = profiles.pop("default", [])
    result: dict[str, list[str]] = {}
    for name, members in profiles.items():
        listed = (default if name in ("debug", "release") else []) + members
        unknown = [m for m in listed if m not in names]
        if unknown:
            notes.append(f"profile {name}: no feature {', '.join(unknown)}")
        result[name] = list(dict.fromkeys(names[m] for m in listed if m in names))
    used = {m for members in result.values() for m in members}
    features = {n: f for n, f in features.items() if n in used or n not in builtin}  # fpm's own: only when used
    return features, result


def _dependencies(manifest: dict, root: str, notes: list[str]) -> tuple[list[str], dict]:
    """fobos ``[dependencies]`` lines and mode keys (metapackages) of the manifest's dependencies; dev-dependencies
    get ``:: dev``, path dependencies are ``path=`` the dependency's library directory, and the dependencies of a path
    dependency (its own ``fpm.toml``) are followed, as fpm does: a fobos path dependency's own are not."""
    lines: dict[str, str] = {}  # dependency name -> fobos line
    mode_keys: dict[str, str] = {}
    seen: set[str] = set()  # the path dependencies' directories, relative to the root

    def add(package: dict, base: str, dev: str, owner: str) -> None:
        for table in ("dependencies", "dev-dependencies"):
            if owner and table == "dev-dependencies":
                continue  # a dependency's test-only dependencies are its own
            marker = " :: dev" if dev or table == "dev-dependencies" else ""
            where = f"{table} of {owner}" if owner else table
            for dep, spec in sorted((package.get(table) or {}).items()):
                if isinstance(spec, str):
                    if dep in METAPACKAGE_KEYS:
                        mode_keys[METAPACKAGE_KEYS[dep]] = "True"
                    else:
                        notes.append(f"{where} {dep} = {spec!r}: a registry version or metapackage, not translated")
                elif "git" in spec:
                    pin = next((f" :: {k}={spec[k]}" for k in ("tag", "branch", "rev") if k in spec), "")
                    lines.setdefault(dep, f"{dep} = {spec['git']}{pin}{marker}")
                elif "path" in spec:
                    directory = os.path.normpath(os.path.join(base, spec["path"])).replace(os.sep, "/")
                    if directory in seen:
                        continue
                    seen.add(directory)
                    sub = {}
                    manifest_path = os.path.join(root, directory, "fpm.toml")
                    if os.path.isfile(manifest_path):
                        with open(manifest_path, encoding="utf-8") as handle:
                            sub = load_toml(handle.read())
                    # the library directory only: the whole package would bring its programs and tests
                    library = sub.get("library", {}).get("source-dir", "src")
                    path = os.path.normpath(os.path.join(directory, library)).replace(os.sep, "/")
                    lines.setdefault(dep, f"{dep} = path={path}{marker}")
                    add(sub, directory, marker, dep)
                else:
                    notes.append(f"{where} {dep} = {spec!r}: not translated")

    add(manifest, ".", "", "")
    return list(lines.values()), mode_keys


def _same_names(root: str, directories: list[str]) -> list[str]:
    """Source file names found in more than one directory: FoBiS names an object after its file, so they collide."""
    found: dict[str, set[str]] = {}
    for directory in directories:
        for folder, _, files in os.walk(os.path.join(root, directory)):
            for name in files:
                if os.path.splitext(name)[1].lower() in (".f90", ".f", ".f95", ".f03", ".f08", ".c"):
                    found.setdefault(name, set()).add(os.path.relpath(folder, root))
    return sorted(name for name, folders in found.items() if len(folders) > 1)


def _has_c_sources(root: str, sources: list[str]) -> bool:
    return any(
        name.endswith(".c")
        for source in sources
        for _, _, files in os.walk(os.path.join(root, source))
        for name in files
    )


def _fortran_flags(fortran: dict, compiler: str, notes: list[str]) -> list[str]:
    """The flags fpm adds to every Fortran compile for the [fortran] table, defaults included (no implicit typing, no
    implicit externals, free form)."""
    table = FPM_FORTRAN_FLAGS.get(compiler, {})
    typing = "implicit-typing" if fortran.get("implicit-typing", False) else "no-implicit-typing"
    external = "implicit-external" if fortran.get("implicit-external", False) else "no-implicit-external"
    form = fortran.get("source-form", "free")
    if form not in ("free", "fixed", "default"):
        notes.append(f"[fortran] source-form = {form!r}: not translated")
    return [table[k] for k in (typing, external, form) if k in table]


def fobos_from_fpm(manifest: dict, root: str = ".", compiler: str = "gnu") -> Translation:
    """A fobos for the package of *manifest* (its ``fpm.toml`` read), the project at *root*, for the FoBiS compiler
    *compiler*: fpm's features become ``[feature:NAME]`` sections (resolved for that compiler and this OS), its profiles
    ``<compiler>-<profile>`` modes, its library types ``lib-static``/``lib-shared`` modes."""
    notes: list[str] = []
    os_name = current_os()
    fpm_id = fpm_compiler(FPM_COMPILER_OF.get(compiler, ""), os_name) if compiler in FPM_COMPILER_OF else None
    if fpm_id is None:
        notes.append(f"compiler {compiler} has no fpm counterpart: only fpm's flags for all compilers are translated")
    name = str(manifest.get("name", "")) or os.path.basename(os.path.abspath(root))
    build = manifest.get("build", {})
    library = manifest.get("library", {})
    lib_dir = library.get("source-dir", "src")
    has_library = os.path.isdir(os.path.join(root, lib_dir))
    sources = [lib_dir] if has_library else []
    executables = _targets(manifest, "executable", "app", build.get("auto-executables", True), root)
    tests = _targets(manifest, "test", "test", build.get("auto-tests", True), root)
    examples = _targets(manifest, "example", "example", build.get("auto-examples", True), root)
    for entry in executables + tests + examples:
        if entry["dir"] not in sources and os.path.isdir(os.path.join(root, entry["dir"])):
            sources.append(entry["dir"])
    deps_lines, mode_keys = _dependencies(manifest, root, notes)
    link = build.get("link", [])
    ext_libs = [link] if isinstance(link, str) else list(link)
    if build.get("external-modules"):
        notes.append(f"external-modules {build['external-modules']}: provided outside the sources (no fobos key)")
    version = str(manifest.get("version", ""))
    macros = [_macro(m, version) for m in _as_list(manifest.get("preprocess", {}).get("cpp", {}).get("macros"))]
    fortran_flags = _fortran_flags(manifest.get("fortran", {}), fpm_id or "", notes)
    if _uses_cpp(manifest) and FPM_CPP_FLAG.get(fpm_id or ""):
        fortran_flags.insert(0, FPM_CPP_FLAG[fpm_id])
    if fpm_id in ("ifort", "ifort-macos", "ifx"):  # fpm.f90 new_compiler_flags: Intel always -fPIC (but on Windows)
        fortran_flags.append("-fPIC")
    features, profiles = _features_and_profiles(manifest, fpm_id or "", os_name, notes)
    for feature in features.values():
        feature.macros = [_macro(m, version) for m in feature.macros]
    has_c = _has_c_sources(root, sources)
    path_dirs = [line.split("path=", 1)[1].split(" ::")[0] for line in deps_lines if " = path=" in line]
    same = _same_names(root, sources + path_dirs)
    if same:
        notes.append(
            f"files named alike in several directories ({', '.join(same)}): FoBiS names objects after the file, so "
            "they collide; rename them"
        )
    kinds = _as_list(library.get("type", "monolithic"))
    lib_kinds = list(dict.fromkeys("shared" if k == "shared" else "static" for k in kinds))

    module = _module_file(root, lib_dir, name.lower().replace("-", "_")) if has_library else ""
    modes = [f"{compiler}-{p}" for p in profiles] + ([f"lib-{k}" for k in lib_kinds] if module else [])
    where = f"{FPM_COMPILER_OF.get(compiler, compiler)} on {os_name}"
    out = ["# generated by fobis fpm import from fpm.toml", f"# fpm's flags for {where}", ""]
    out += ["[project]", f"name = {name}"]
    for key, fobos_key in (("version", "version"), ("description", "summary"), ("homepage", "repository")):
        if manifest.get(key):
            out.append(f"{fobos_key} = {manifest[key]}")
    authors = manifest.get("author")
    if authors:
        out.append(f"authors = {authors if isinstance(authors, str) else ', '.join(authors)}")
    out += ["", "[modes]", f"modes = {' '.join(modes)}", "", "[template-common]", f"compiler = {compiler}"]
    out += [
        "src = " + " ".join(_source_path(s) for s in sources),
        "mod_dir = ./mod/",
        "obj_dir = ./obj/",
        "cflags = " + " ".join(["-c", *fortran_flags]),
    ]
    include_dirs = _as_list(library.get("include-dir"))
    if include_dirs:
        out.append("include = " + " ".join(_source_path(d) for d in include_dirs))
    if macros:
        out.append("preproc = " + " ".join(f"-D{m}" for m in macros))
    if ext_libs:
        out.append(f"ext_libs = {' '.join(ext_libs)}")
    out += [f"{key} = {value}" for key, value in mode_keys.items()]

    def mode(section: str, members: list[str], build_dir: str, extra: list[str], pic: bool = False) -> list[str]:
        lines = ["", f"[{section}]", "template = template-common", f"features = {' '.join(members)}"]
        lines.append(f"build_dir = {build_dir}")
        if pic:
            lines.append("cflags = " + " ".join(["-c", *fortran_flags, "-fPIC"]))
        c_flags = [f for m in members for f in features[m].c_flags if f.strip()]
        if has_c and (c_flags or pic):
            pic_flag = ["-fPIC"] if pic and "-fPIC" not in " ".join(c_flags).split() else []
            lines.append("c_cflags = " + " ".join(["-c", *c_flags, *pic_flag]))
        c_macros = macros + [d for m in members for d in features[m].macros]  # fpm gives C the macros too
        if has_c and c_macros:
            lines.append("c_preproc = " + " ".join(f"-D{d}" for d in c_macros))
        link_flags = [f for m in members for f in features[m].link_flags if f.strip()]
        if link_flags:
            lines.append("lflags = " + " ".join(link_flags))
        return lines + extra

    for profile, members in profiles.items():
        out += mode(f"{compiler}-{profile}", members, f"./build/{profile}/", [])
    if module:
        for kind in lib_kinds:
            suffix = "a" if kind == "static" else "so"
            target = [f"target = {module}", f"output = lib{name.lower()}.{suffix}", f"mklib = {kind}"]
            build_dir = "./build/lib/" if kind == "static" else "./build/lib-shared/"
            out += mode(f"lib-{kind}", profiles["release"], build_dir, target, pic=kind == "shared")
    elif has_library:
        notes.append(
            f"no module named {name.lower()!r} in {lib_dir}: no library mode (FoBiS builds a library from one target "
            "module: add a mode with target = the module that uses the others, mklib = static)"
        )
    for feature_name, feature in features.items():
        out += ["", f"[feature:{feature_name}]", f"flags = {_feature_flags(feature)}".rstrip()]
        if feature.requires:
            out.append(f"requires = {' '.join(feature.requires)}")
    if tests:
        test_dirs = sorted({t["dir"] for t in tests})
        out += ["", "[test]", f"test_dir = {test_dirs[0]}"]
        if len(test_dirs) > 1:
            notes.append(f"tests in several directories {test_dirs}: fobis test runs those of {test_dirs[0]}")
    if deps_lines:
        out += ["", "[dependencies]", *deps_lines]
    return Translation("\n".join(out) + "\n", notes)


# ── fobos -> fpm.toml ──────────────────────────────────────────────────────────


def _common_dir(paths: list[str]) -> str:
    if not paths:
        return ""
    return os.path.commonpath([os.path.dirname(p) or "." for p in paths]).replace(os.sep, "/") or "."


def fpm_from_fobos(
    project: dict,
    dependencies: dict[str, str],
    units: dict,
    root: str,
    test_dir: str,
    mode_keys: dict[str, bool],
    defines: list[str],
) -> Translation:
    """An ``fpm.toml`` for the project: *project* (fobos ``[project]``, version resolved), its *dependencies*
    (fobos specs), the analysed *units* of a mode's sources (display path -> FileUnits), the tests directory, the
    mode's ``mpi``/``openmp`` keys and ``-D`` macros."""
    from .Fetcher import Fetcher

    notes = ["fobos modes, templates, flags and rules are not exported: fpm uses its own profiles (debug, release)"]
    module_files, programs = [], []
    for path, file_units in sorted(units.items()):
        rel = os.path.relpath(os.path.abspath(path), os.path.abspath(root)).replace(os.sep, "/")
        program = next((u.name for u in file_units.units if u.kind == "program"), None)
        if program is not None:
            programs.append((rel, program))
        elif any(u.kind in ("module", "submodule") for u in file_units.units):
            module_files.append(rel)
    lib_dir = _common_dir(module_files)
    if lib_dir:
        inside = [p for p, _ in programs if lib_dir == "." or p.startswith(lib_dir + "/")]
        if inside:
            notes.append(
                f"the library directory {lib_dir} also holds {len(inside)} program(s) (e.g. {inside[0]}): fpm "
                "compiles every file of source-dir into the library; keep programs out of it"
            )
    out = [f"name = {_toml_string(project.get('name') or os.path.basename(os.path.abspath(root)))}"]
    if project.get("version"):
        out.append(f"version = {_toml_string(project['version'])}")
    if project.get("authors"):
        out.append(f"author = {_toml_string(', '.join(project['authors']))}")
    for key, fpm_key in (("summary", "description"), ("repository", "homepage")):
        if project.get(key):
            out.append(f"{fpm_key} = {_toml_string(project[key])}")
    if module_files:
        out += ["", "[library]", f"source-dir = {_toml_string(lib_dir)}"]
    out += ["", "[build]", "auto-executables = false", "auto-tests = false", "auto-examples = false"]
    if defines:
        out += ["", "[preprocess]", "[preprocess.cpp]", f"macros = {_toml_value([d[2:] for d in defines])}"]
    metapackages = [key for key, enabled in mode_keys.items() if enabled]
    if dependencies or metapackages:
        out += ["", "[dependencies]", *(f'{key} = "*"' for key in metapackages)]
        fetcher = Fetcher(deps_dir=".fobis_deps")  # only its spec parser is used
        for dep, spec in sorted(dependencies.items()):
            parsed = fetcher.parse_dep_spec(spec)
            if "path" in parsed:  # a local directory: fpm's path dependency
                out.append(f"{dep} = {_toml_value({'path': parsed['path']})}")
                continue
            entry = {"git": parsed["url"]}
            entry.update({pin: parsed[pin] for pin in ("tag", "branch", "rev") if parsed.get(pin)})
            if parsed.get("semver"):
                notes.append(f"dependency {dep}: semver {parsed['semver']} has no fpm git equivalent (not exported)")
            out.append(f"{dep} = {_toml_value(entry)}")

    def is_test(path: str) -> bool:
        if test_dir:
            return path.startswith(test_dir.rstrip("/") + "/")
        return bool({"test", "tests"} & set(path.split("/")[:-1]))

    tests = [(p, n) for p, n in programs if is_test(p)]
    executables = [(p, n) for p, n in programs if (p, n) not in tests]
    counts: dict[str, int] = {}
    for _, program in programs:
        counts[program] = counts.get(program, 0) + 1
    for table, items in (("executable", executables), ("test", tests)):
        for path, program in items:  # fpm names must be unique: the program's name, else its file's stem
            name = program if counts[program] == 1 else os.path.splitext(os.path.basename(path))[0]
            out += ["", f"[[{table}]]", f"name = {_toml_string(name)}"]
            out.append(f"source-dir = {_toml_string(os.path.dirname(path) or '.')}")
            out.append(f"main = {_toml_string(os.path.basename(path))}")
    return Translation("\n".join(out) + "\n", notes)
