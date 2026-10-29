"""
Line-based edits of a fobos ``[dependencies]`` section.

configparser would drop every comment and reorder the file when writing it back, so an entry is added, replaced or
removed by editing the lines of its key only (and its continuation lines); the rest of the file is left as it is.
The file is replaced atomically.
"""

from __future__ import annotations

import os
import re
import tempfile

SECTION = "dependencies"
_KEY = re.compile(r"^([A-Za-z0-9_.\-]+)\s*[=:]")


def _read(path: str) -> list[str]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return fh.read().splitlines()


def _write(path: str, lines: list[str]) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".fobos-", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    if os.path.exists(path):
        os.chmod(tmp, os.stat(path).st_mode & 0o7777)
    os.replace(tmp, path)


def _section(lines: list[str], section: str) -> tuple[int | None, int]:
    """(header index or None, index after the section's last line)."""
    header = next((i for i, line in enumerate(lines) if line.strip().lower() == f"[{section}]"), None)
    if header is None:
        return None, len(lines)
    end = next((i for i in range(header + 1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))
    return header, end


def _entry(lines: list[str], header: int, end: int, name: str) -> tuple[int, int] | None:
    """(first line, line after the last continuation line) of key *name* in the section, or None."""
    for i in range(header + 1, end):
        match = _KEY.match(lines[i])
        if match and match.group(1).lower() == name.lower():
            stop = i + 1
            while stop < end and lines[stop].strip() and lines[stop][:1] in " \t":
                stop += 1
            return i, stop
    return None


def has_entry(path: str, name: str) -> bool:
    """Whether the fobos at *path* has dependency *name*."""
    lines = _read(path)
    header, end = _section(lines, SECTION)
    return header is not None and _entry(lines, header, end, name) is not None


def set_entry(path: str, name: str, spec: str, comment: str = "") -> bool:
    """
    Add or replace dependency *name* = *spec*; *comment* (one line) is written on the line above a NEW entry. The
    section, or the file, is created when missing; a new entry goes after the section's last key.

    Returns
    -------
    bool
      True when an existing entry was replaced
    """
    lines = _read(path)
    header, end = _section(lines, SECTION)
    new = [f"{name} = {spec}"]
    if header is None:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += ([""] if lines else []) + [f"[{SECTION}]"] + ([f"# {comment}"] if comment else []) + new
        _write(path, lines)
        return False
    found = _entry(lines, header, end, name)
    if found is not None:
        lines[found[0] : found[1]] = new
        _write(path, lines)
        return True
    last = header
    for i in range(header + 1, end):  # after the last non-blank line of the section (its trailing comments too)
        if lines[i].strip():
            last = i
    lines[last + 1 : last + 1] = ([f"# {comment}"] if comment else []) + new
    _write(path, lines)
    return False


def remove_entry(path: str, name: str) -> bool:
    """Remove dependency *name* (and the comment line just above it written by `set_entry`); True when found."""
    lines = _read(path)
    header, end = _section(lines, SECTION)
    found = None if header is None else _entry(lines, header, end, name)
    if found is None:
        return False
    start = found[0]
    if start - 1 > header and lines[start - 1].startswith("# added by fobis add"):
        start -= 1
    del lines[start : found[1]]
    _write(path, lines)
    return True
