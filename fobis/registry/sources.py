"""
Package sources: what a source URL holds (versions, build system, modules, licence).

The source is the authority on its versions: for a git repository they are its tags (``git ls-remote``), for a static
web directory the releases of its ``fortran-releases.toml`` manifest (see `manifest`). `probe` reads one source and
returns a `SourceInfo`; `inspect_tree` reads the facts of a source tree already on disk.
"""

from __future__ import annotations

import configparser
import os
import re
import tempfile
from dataclasses import dataclass, field
from typing import Any

from ..SemVer import Version
from .index import RegistryError, run_git

FORTRAN_SUFFIXES = (".f", ".for", ".fpp", ".f77", ".f90", ".f95", ".f03", ".f08", ".f18", ".f23", ".ftn")
_MODULE = re.compile(r"^\s*module\s+(?!procedure\b|function\b|subroutine\b)([a-z_]\w*)\s*(?:!.*)?$", re.I | re.M)
_SKIP_DIRS = {".git", ".fobis_deps", ".fobis", "build", "node_modules", "_build"}
# modules under these directories are not what a package provides: tests, examples, vendored copies of other packages
NOT_PROVIDED_DIRS = {
    "test", "tests", "example", "examples", "third_party", "thirdparty", "vendor", "external", "externals", "extern",
    "contrib", "deps", "subprojects",
}  # fmt: skip


class SourceError(RegistryError):
    """A source cannot be read."""


@dataclass
class SourceInfo:
    """What a source holds."""

    url: str
    provider: str  # git, manifest
    versions: list[str] = field(default_factory=list)  # semver versions as written (tags), newest first
    latest: str = ""  # the newest version ('' when none)
    name: str = ""
    backend: str = ""  # fobis, fpm, cmake, make ('' when unknown)
    modules: list[str] = field(default_factory=list)
    license: str = ""
    description: str = ""
    other_tags: list[str] = field(default_factory=list)  # tags that are not versions

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "provider": self.provider,
            "versions": self.versions,
            "latest": self.latest,
            "name": self.name,
            "backend": self.backend,
            "modules": self.modules,
            "license": self.license,
            "description": self.description,
        }


def sort_versions(tags: list[str]) -> tuple[list[str], list[str]]:
    """Split tags into semantic versions (newest first) and the rest."""
    versions, others = [], []
    for tag in tags:
        try:
            versions.append((Version(tag), tag))
        except ValueError:
            others.append(tag)
    versions.sort(key=lambda pair: pair[0], reverse=True)
    return [tag for _, tag in versions], sorted(others)


def git_tags(url: str, anonymous: bool = False) -> list[str]:
    """The tags of a git remote (no clone); SourceError when it cannot be read."""
    result = run_git("ls-remote", "--tags", url, timeout=120, anonymous=anonymous)
    if result.returncode != 0:
        lines = result.stderr.strip().splitlines()
        raise SourceError(f"{url}: not a readable git repository ({lines[-1] if lines else 'git ls-remote failed'})")
    tags = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].startswith("refs/tags/") and not parts[1].endswith("^{}"):
            tags.append(parts[1][len("refs/tags/") :])
    return tags


def git_checkout(url: str, dest: str, ref: str = "", anonymous: bool = False) -> None:
    """Shallow clone of *url* at *ref* (a tag or branch; the default branch when empty) into *dest*."""
    args = ["clone", "--depth", "1", "--quiet"] + (["--branch", ref] if ref else []) + [url, dest]
    result = run_git(*args, anonymous=anonymous)
    if result.returncode != 0:
        lines = result.stderr.strip().splitlines()
        raise SourceError(f"{url}: clone failed ({lines[-1] if lines else 'git clone failed'})")


def tree_hash(checkout: str) -> str:
    """The git tree hash of HEAD in a checkout (the content identity, as Julia's ``git-tree-sha1``)."""
    result = run_git("rev-parse", "HEAD^{tree}", cwd=checkout)
    return result.stdout.strip() if result.returncode == 0 else ""


def scan_modules(root: str, provided: bool = True) -> list[str]:
    """
    Names (lower-case, sorted) of the modules defined by the Fortran sources under *root*; with *provided*, the
    directories of tests, examples and vendored packages (`NOT_PROVIDED_DIRS`) are skipped.
    """
    modules: set[str] = set()
    skip = _SKIP_DIRS | (NOT_PROVIDED_DIRS if provided else set())
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d.lower() not in skip and not d.startswith("."))
        for filename in filenames:
            if not filename.lower().endswith(FORTRAN_SUFFIXES):
                continue
            try:
                with open(os.path.join(dirpath, filename), encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            modules.update(m.lower() for m in _MODULE.findall(text))
    return sorted(modules)


def detect_backend(root: str) -> str:
    """The build system of a source tree: fobis, fpm, cmake, make, or '' when none is recognised."""
    checks = (
        ("fobis", ("fobos",)),
        ("fpm", ("fpm.toml",)),
        ("cmake", ("CMakeLists.txt",)),
        ("make", ("GNUmakefile", "Makefile", "makefile", "configure")),
    )
    for backend, files in checks:
        if any(os.path.isfile(os.path.join(root, f)) for f in files):
            return backend
    return ""


_LICENSES = (
    ("MIT", ("MIT License", "Permission is hereby granted, free of charge")),
    ("Apache-2.0", ("Apache License", "Version 2.0")),
    ("GPL-3.0", ("GNU GENERAL PUBLIC LICENSE", "Version 3")),
    ("GPL-2.0", ("GNU GENERAL PUBLIC LICENSE", "Version 2")),
    ("LGPL-3.0", ("GNU LESSER GENERAL PUBLIC LICENSE", "Version 3")),
    ("BSD-3-Clause", ("Redistribution and use", "Neither the name")),
    ("BSD-2-Clause", ("Redistribution and use", "THIS SOFTWARE IS PROVIDED")),
)


def detect_license(root: str) -> str:
    """An SPDX identifier guessed from the licence file ('' when none matches): the manifest's value wins."""
    for name in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        if not re.match(r"^(LICEN[CS]E|COPYING)(\.\w+)?$", name, re.I):
            continue
        try:
            with open(os.path.join(root, name), encoding="utf-8", errors="replace") as fh:
                text = fh.read(20000)
        except OSError:
            continue
        for spdx, markers in _LICENSES:
            if all(marker.lower() in text.lower() for marker in markers):
                return spdx
    return ""


def _readme_description(root: str) -> str:
    """The first prose line of the README (no heading, badge, HTML or blank line), at most 160 characters."""
    for name in ("README.md", "README.rst", "README", "README.txt"):
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                text = line.strip()
                if not text or text.startswith(("#", "[!", "![", "<", "=", "-", "|", ">", "[![", "```")):
                    continue
                return text[:160]
    return ""


def read_manifests(root: str) -> dict[str, str]:
    """name, description, license, version from the source's own manifest (fobos ``[project]``, else fpm.toml)."""
    facts = {"name": "", "description": "", "license": "", "version": ""}
    fobos = os.path.join(root, "fobos")
    if os.path.isfile(fobos):
        config = configparser.RawConfigParser(strict=False)
        try:
            config.read(fobos, encoding="utf-8")
        except configparser.Error:
            config = None
        if config is not None and config.has_section("project"):
            facts["name"] = config.get("project", "name", fallback="").strip()
            facts["description"] = config.get("project", "summary", fallback="").strip()
            facts["license"] = config.get("project", "license", fallback="").strip()
    fpm = os.path.join(root, "fpm.toml")
    if os.path.isfile(fpm):
        from ..fpm import FpmError, load_toml

        try:
            with open(fpm, encoding="utf-8") as fh:
                manifest = load_toml(fh.read())
        except (OSError, FpmError, ValueError):
            manifest = {}
        for key in ("name", "description", "license", "version"):
            value = manifest.get(key)
            if isinstance(value, str) and not facts[key]:
                facts[key] = value.strip()
    return facts


def inspect_tree(root: str, info: SourceInfo) -> SourceInfo:
    """Fill *info* with the facts of the source tree at *root*."""
    facts = read_manifests(root)
    info.name = info.name or facts["name"]
    info.description = info.description or facts["description"] or _readme_description(root)
    info.license = info.license or facts["license"] or detect_license(root)
    info.backend = detect_backend(root)
    info.modules = scan_modules(root)
    return info


def probe(url: str, inspect: bool = True, anonymous: bool = False) -> SourceInfo:
    """
    Read a source: its versions and, with *inspect*, the facts of its newest version (a shallow clone in a temporary
    directory, removed afterwards). *anonymous*: read it without the user's credentials.

    Raises
    ------
    SourceError
      the URL is not a readable source
    """
    versions, others = sort_versions(git_tags(url, anonymous=anonymous))
    info = SourceInfo(url=url, provider="git", versions=versions, latest=versions[0] if versions else "")
    info.other_tags = others
    if inspect:
        with tempfile.TemporaryDirectory(prefix="fobis-probe-") as scratch:
            checkout = os.path.join(scratch, "src")
            git_checkout(url, checkout, info.latest, anonymous=anonymous)
            inspect_tree(checkout, info)
    if not info.name:
        info.name = default_name(url)
    return info


def public_url(url: str) -> str:
    """The URL others can clone: ``git@host:owner/repo.git`` -> ``https://host/owner/repo`` (other URLs unchanged)."""
    match = re.match(r"^(?:ssh://)?git@([^:/]+)[:/](.+?)(?:\.git)?/?$", url.strip())
    return f"https://{match.group(1)}/{match.group(2)}" if match else url.strip()


def default_name(url: str) -> str:
    """The package name a URL suggests: its last path component without ``.git``."""
    name = url.rstrip("/").split("/")[-1].split(":")[-1]
    return name[:-4] if name.endswith(".git") else name
