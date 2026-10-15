"""fpm.py — interoperability with the Fortran Package Manager (phase V12 of PLAN-verification.md).

``fobis fpm import`` writes a fobos from an ``fpm.toml``; ``fobis fpm export`` writes an ``fpm.toml`` from a fobos
and the facts of its sources. Each side keeps what the other can express and lists, as notes, what it cannot (fobos
modes, templates and rules; fpm profiles and registry dependencies). Flags are not invented: an imported fobos uses
FoBiS's own ``debug``/``release`` build profiles.

TOML is read with ``tomllib`` (Python 3.11+) and otherwise with `parse_toml`, a reader of the subset manifests use
(tables, arrays of tables, dotted keys, strings, numbers, booleans, arrays, inline tables): the zipapp stays
stdlib-only on Python 3.10.
"""

from __future__ import annotations

import os
import re
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


def _dependencies(manifest: dict, root: str, sources: list[str], notes: list[str]) -> tuple[list[str], dict]:
    """fobos ``[dependencies]`` lines and mode keys (metapackages) of the manifest's dependencies."""
    lines, mode_keys = [], {}
    all_deps = {**manifest.get("dependencies", {}), **manifest.get("dev-dependencies", {})}
    if manifest.get("dev-dependencies"):
        notes.append("dev-dependencies are fetched like dependencies (fobos does not tell them apart)")
    for dep, spec in sorted(all_deps.items()):
        if isinstance(spec, str):
            if dep in METAPACKAGE_KEYS:
                mode_keys[METAPACKAGE_KEYS[dep]] = "True"
            else:
                notes.append(f"dependency {dep} = {spec!r}: a registry version or metapackage, not translated")
        elif "git" in spec:
            pin = next((f" :: {k}={spec[k]}" for k in ("tag", "branch", "rev") if k in spec), "")
            lines.append(f"{dep} = {spec['git']}{pin}")
        elif "path" in spec:
            sub_dir = "src"
            manifest_path = os.path.join(root, spec["path"], "fpm.toml")
            if os.path.isfile(manifest_path):
                with open(manifest_path, encoding="utf-8") as handle:
                    sub_dir = load_toml(handle.read()).get("library", {}).get("source-dir", "src")
            sources.append(os.path.join(spec["path"], sub_dir))
            notes.append(f"path dependency {dep} ({spec['path']}): its library sources are compiled with the project")
        else:
            notes.append(f"dependency {dep} = {spec!r}: not translated")
    return lines, mode_keys


def fobos_from_fpm(manifest: dict, root: str = ".", compiler: str = "gnu") -> Translation:
    """A fobos for the package of *manifest* (its ``fpm.toml`` read), the project at *root*."""
    notes: list[str] = []
    name = str(manifest.get("name", "")) or os.path.basename(os.path.abspath(root))
    build = manifest.get("build", {})
    lib_dir = manifest.get("library", {}).get("source-dir", "src")
    has_library = os.path.isdir(os.path.join(root, lib_dir))
    sources = [lib_dir] if has_library else []
    executables = _targets(manifest, "executable", "app", build.get("auto-executables", True), root)
    tests = _targets(manifest, "test", "test", build.get("auto-tests", True), root)
    examples = _targets(manifest, "example", "example", build.get("auto-examples", True), root)
    for entry in executables + tests + examples:
        if entry["dir"] not in sources and os.path.isdir(os.path.join(root, entry["dir"])):
            sources.append(entry["dir"])
    deps_lines, mode_keys = _dependencies(manifest, root, sources, notes)
    link = build.get("link", [])
    ext_libs = [link] if isinstance(link, str) else list(link)
    if build.get("external-modules"):
        notes.append(f"external-modules {build['external-modules']}: provided outside the sources (no fobos key)")
    macros = manifest.get("preprocess", {}).get("cpp", {}).get("macros", [])
    fortran = manifest.get("fortran", {})
    for key in ("implicit-typing", "implicit-external"):
        if fortran.get(key) is False:
            notes.append(f"[fortran] {key} = false: fpm adds the compiler's flag for it; add it to the cflags")
    if fortran.get("source-form"):
        notes.append(f"[fortran] source-form = {fortran['source-form']!r}: not translated")
    for table in ("features", "profiles"):
        if manifest.get(table):
            notes.append(f"[{table}] ({', '.join(sorted(manifest[table]))}): fpm's own flag sets, not translated")

    module = _module_file(root, lib_dir, name.lower().replace("-", "_")) if has_library else ""
    modes = [f"{compiler}-debug", f"{compiler}-release"] + ([f"lib-{compiler}"] if module else [])
    out = ["# generated by fobis fpm import from fpm.toml", "", "[project]", f"name = {name}"]
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
        "cflags = -c",
    ]
    if macros:
        out.append("preproc = " + " ".join(f"-D{m}" for m in macros))
    if ext_libs:
        out.append(f"ext_libs = {' '.join(ext_libs)}")
    out += [f"{key} = {value}" for key, value in mode_keys.items()]
    for profile in ("debug", "release"):
        out += ["", f"[{compiler}-{profile}]", "template = template-common", f"build_profile = {profile}"]
        out.append(f"build_dir = ./build/{profile}/")
    if module:
        out += ["", f"[lib-{compiler}]", "template = template-common", "build_profile = release"]
        out += ["build_dir = ./build/lib/", f"target = {module}", f"output = lib{name.lower()}.a", "mklib = static"]
    elif has_library:
        notes.append(
            f"no module named {name.lower()!r} in {lib_dir}: no library mode (FoBiS builds a library from one target "
            "module: add a mode with target = the module that uses the others, mklib = static)"
        )
    if tests:
        test_dirs = sorted({t["dir"] for t in tests})
        out += ["", "[test]", f"test_dir = {test_dirs[0]}"]
        if len(test_dirs) > 1:
            notes.append(f"tests in several directories {test_dirs}: fobis test runs those of {test_dirs[0]}")
    if deps_lines:
        out += ["", "[dependencies]", *deps_lines]
    notes.append("fpm profiles become FoBiS build profiles (debug/release flags of the compiler); fpm's flags differ")
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
