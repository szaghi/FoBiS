"""
Security and correctness advisories, published by each package itself.

There is no central advisory database (the weakest point of a design with no centre, and said so): a package's
maintainers publish ``fortran-advisories.toml`` at the root of its default branch (or next to its release manifest)::

    schema = 1
    [[advisory]]
    id       = "PENF-2026-001"
    affected = "<2.0.2"                    # a semver range of the affected versions
    severity = "high"                      # low, medium, high, critical
    summary  = "str() overflows its buffer for 128-bit integers"
    url      = "https://github.com/szaghi/PENF/issues/99"

``fobis audit`` reads the advisories of every fetched dependency from its source (the newest file, not the copy in the
fetched version) and reports those whose range contains the locked version.
"""

from __future__ import annotations

import os
import tempfile
import urllib.parse
from dataclasses import dataclass

from ..SemVer import Version, parse_constraint, satisfies
from .index import RegistryError, http_get, run_git

ADVISORIES = "fortran-advisories.toml"
SEVERITIES = ("low", "medium", "high", "critical")


@dataclass
class Advisory:
    id: str
    affected: str
    severity: str
    summary: str
    url: str = ""

    def affects(self, version: str) -> bool:
        try:
            return satisfies(Version(version), parse_constraint(self.affected))
        except ValueError:
            return False

    def to_dict(self) -> dict[str, str]:
        return dict(self.__dict__)


def parse_advisories(text: str, origin: str = "") -> list[Advisory]:
    from ..fpm import FpmError, load_toml

    where = f"{origin}: " if origin else ""
    try:
        data = load_toml(text)
    except (FpmError, ValueError) as error:
        raise RegistryError(f"{where}not valid TOML: {error}") from error
    found = []
    for i, entry in enumerate(data.get("advisory", [])):
        missing = [k for k in ("id", "affected", "severity", "summary") if not isinstance(entry.get(k), str)]
        if missing:
            raise RegistryError(f"{where}advisory {i + 1}: missing {', '.join(missing)}")
        if entry["severity"] not in SEVERITIES:
            raise RegistryError(f"{where}advisory {entry['id']}: severity must be one of {', '.join(SEVERITIES)}")
        try:
            parse_constraint(entry["affected"])
        except ValueError as error:
            raise RegistryError(f"{where}advisory {entry['id']}: affected: {error}") from error
        found.append(
            Advisory(entry["id"], entry["affected"], entry["severity"], entry["summary"], str(entry.get("url", "")))
        )
    return found


def read_advisories(url: str, provider: str = "git") -> list[Advisory]:
    """The advisories a source publishes (empty when it publishes none)."""
    if provider == "manifest":
        base = url if url.endswith("/") else url.rsplit("/", 1)[0] + "/"
        if "://" not in base:
            base = "file://" + urllib.parse.quote(os.path.abspath(base)) + "/"
        try:
            text = http_get(urllib.parse.urljoin(base, ADVISORIES)).decode("utf-8")
        except RegistryError:
            return []
        return parse_advisories(text, origin=url)
    with tempfile.TemporaryDirectory(prefix="fobis-audit-") as scratch:
        checkout = os.path.join(scratch, "src")
        result = run_git("clone", "--depth", "1", "--quiet", "--no-checkout", url, checkout)
        if result.returncode != 0:
            raise RegistryError(f"{url}: cannot read its advisories ({result.stderr.strip().splitlines()[-1:]})")
        shown = run_git("show", f"HEAD:{ADVISORIES}", cwd=checkout)
        if shown.returncode != 0:
            return []
        return parse_advisories(shown.stdout, origin=url)


def tag_commits(url: str) -> dict[str, str]:
    """``tag -> commit`` of a git remote (annotated tags peeled), from ``git ls-remote``."""
    result = run_git("ls-remote", "--tags", url, timeout=120)
    if result.returncode != 0:
        raise RegistryError(f"{url}: not readable")
    commits: dict[str, str] = {}
    for line in result.stdout.splitlines():
        sha, _, ref = line.partition("\t")
        if not ref.startswith("refs/tags/"):
            continue
        tag = ref[len("refs/tags/") :]
        if tag.endswith("^{}"):
            commits[tag[:-3]] = sha  # the peeled commit wins over the tag object
        else:
            commits.setdefault(tag, sha)
    return commits
