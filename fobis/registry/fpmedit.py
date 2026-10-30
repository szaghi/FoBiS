"""
Line-based edits of the ``[dependencies]`` and ``[dev-dependencies]`` tables of an fpm.toml.

As for the fobos (`fobosedit`), an entry is added, replaced or removed by editing its own line only: the comments and
layout of the manifest are kept. An entry is one line, ``NAME = { git = "...", tag = "..." }``; an entry written in
another form (a ``[dependencies.NAME]`` table, a value spanning several lines, dotted keys) is left to the user.
"""

from __future__ import annotations

import re
import tempfile

from .fobosedit import _read, _write

TABLES = ("dependencies", "dev-dependencies")


class FpmEditError(Exception):
    """An fpm.toml entry that cannot be edited line by line."""


def _key(name: str) -> str:
    return name if re.match(r"^[A-Za-z0-9_-]+$", name) else '"' + name + '"'


def _section(lines: list[str], table: str) -> tuple[int | None, int]:
    """(header index or None, index after the table's last line)."""
    header = next((i for i, line in enumerate(lines) if line.strip() == f"[{table}]"), None)
    if header is None:
        return None, len(lines)
    end = next((i for i in range(header + 1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))
    return header, end


def _line_key(line: str) -> str | None:
    match = re.match(r'^\s*(?:"([^"]+)"|([A-Za-z0-9_.\-]+))\s*=', line)
    return (match.group(1) or match.group(2)) if match else None


def find(path: str, name: str, table: str) -> tuple[str, int] | None:
    """
    The entry *name* of *table*, compared without regard to case: (its name as written, its line), or None.

    Raises
    ------
    FpmEditError
      the entry is written in a form other than one line
    """
    lines = _read(path)
    if any(line.strip().lower() == f"[{table}.{name}]".lower() for line in lines):
        raise FpmEditError(f"{name} is a [{table}.{name}] table in {path}: edit it by hand")
    header, end = _section(lines, table)
    if header is None:
        return None
    for i in range(header + 1, end):
        key = _line_key(lines[i])
        if key is None:
            continue
        if key.split(".")[0].lower() == name.lower():
            if "." in key or lines[i].count("{") != lines[i].count("}"):
                raise FpmEditError(f"{name} spans several lines or keys in {path}: edit it by hand")
            return key, i
    return None


def set_entry(path: str, name: str, value: str, table: str = "dependencies", comment: str = "") -> bool:
    """
    Add or replace ``name = value`` in *table*; *comment* goes on the line above a NEW entry. The table is created at
    the end of the file when missing. Returns True when an existing entry was replaced.
    """
    found = find(path, name, table)
    lines = _read(path)
    new = f"{_key(name)} = {value}"
    if found is not None:
        lines[found[1]] = new
        _write(path, lines)
        return True
    header, end = _section(lines, table)
    if header is None:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += ([""] if lines else []) + [f"[{table}]"] + ([f"# {comment}"] if comment else []) + [new]
    else:
        last = max([header] + [i for i in range(header + 1, end) if lines[i].strip()])
        lines[last + 1 : last + 1] = ([f"# {comment}"] if comment else []) + [new]
    _write(path, lines)
    return False


def remove_entry(path: str, name: str) -> tuple[str, str, str] | None:
    """
    Remove dependency *name* from ``[dependencies]`` or ``[dev-dependencies]`` (with the comment line ``fobis add``
    wrote above it): (table, name as written, its value), or None when absent.
    """
    for table in TABLES:
        found = find(path, name, table)
        if found is None:
            continue
        lines = _read(path)
        key, i = found
        value = lines[i].split("=", 1)[1].strip()
        start = i - 1 if i > 0 and lines[i - 1].startswith("# added by fobis add") else i
        del lines[start : i + 1]
        _write(path, lines)
        return table, key, value
    return None


def fpm_manifest_at(url: str, ref: str) -> str | None:
    """
    The fpm.toml of the source *url* at *ref* (a tag, a branch, a commit, or "" for the default branch), read from a
    one-commit fetch into a temporary repository: its text, or None when that version has none.

    Raises
    ------
    OSError
      the source cannot be read at that ref
    """
    from .index import run_git

    with tempfile.TemporaryDirectory(prefix="fobis-fpm-manifest-") as scratch:
        run_git("init", "-q", scratch)
        target = f"refs/tags/{ref}" if ref and not re.fullmatch(r"[0-9a-f]{7,40}", ref) else (ref or "HEAD")
        fetched = run_git("-C", scratch, "fetch", "-q", "--depth", "1", "--", url, target)
        if fetched.returncode != 0 and target.startswith("refs/tags/"):  # not a tag: a branch
            fetched = run_git("-C", scratch, "fetch", "-q", "--depth", "1", "--", url, ref)
        if fetched.returncode != 0:
            raise OSError(fetched.stderr.strip().splitlines()[-1] if fetched.stderr.strip() else f"cannot fetch {ref}")
        shown = run_git("-C", scratch, "show", "FETCH_HEAD:fpm.toml")
        return shown.stdout if shown.returncode == 0 else None
