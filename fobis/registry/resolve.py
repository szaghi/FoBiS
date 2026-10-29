"""
Minimal Version Selection (Go's algorithm) over the dependency graph.

Every requirement ``semver=C`` names a MINIMUM: the lowest version of the package that satisfies C. The version
selected for a package is the highest of the minimums required anywhere in the graph, then checked against every
requirement's range: one it falls outside of is a conflict naming both requirers. The answer depends only on the
fobos files, never on what was published since (no lock needed for reproducibility), and a newer dependency is taken
only when someone raises a minimum.

Pins: an exact pin of the project (``tag=``, ``branch=``, ``rev=``) always wins (it decides: a dependency's requirement
it violates is a warning); the project's ranges are minimums like any other. A ``tag=`` of a dependency is a minimum
equal to the tag; ``branch=``/``rev=`` are not versions: two different ones for the same package are a conflict.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ..SemVer import Version, parse_constraint, satisfies
from .index import normalise_source


class ResolutionError(Exception):
    """Requirements no version satisfies."""


@dataclass
class Requirement:
    name: str  # the dependency's name where it is required
    url: str
    constraint: str = ""  # semver range
    tag: str = ""
    ref: str = ""  # branch or rev (not a version)
    requirer: str = "(project)"


@dataclass
class Selection:
    name: str
    url: str
    tag: str = ""  # the selected version (a tag of the source), '' for a ref
    ref: str = ""
    required_by: list[str] = field(default_factory=list)
    root: bool = False


def _minimum(requirement: Requirement, tags: list[str]) -> str:
    """The lowest tag satisfying the requirement (its tag for a tag pin)."""
    if requirement.tag:
        return requirement.tag
    constraints = parse_constraint(requirement.constraint or "*")
    candidates = []
    for tag in tags:
        try:
            version = Version(tag)
        except ValueError:
            continue
        if satisfies(version, constraints):
            candidates.append((version, tag))
    if not candidates:
        raise ResolutionError(
            f"{requirement.requirer} requires {requirement.name} {requirement.constraint}: no version satisfies it"
        )
    return min(candidates)[1]


def _allows(requirement: Requirement, tag: str) -> bool:
    if requirement.ref:
        return False
    if requirement.tag:
        return Version(tag) >= Version(requirement.tag)  # a tag is a minimum
    return satisfies(Version(tag), parse_constraint(requirement.constraint or "*"))


def _is_version(tag: str) -> bool:
    try:
        Version(tag)
    except ValueError:
        return False
    return True


def _normalised(requirement: Requirement) -> Requirement:
    """A tag that is not a semantic version (``stable-2024``) is an exact ref: it cannot be compared."""
    if requirement.tag and not _is_version(requirement.tag):
        return Requirement(requirement.name, requirement.url, ref=requirement.tag, requirer=requirement.requirer)
    return requirement


def select(
    roots: list[Requirement],
    tags_of: Callable[[str], list[str]],
    requirements_of: Callable[[Selection], list[Requirement]],
    warn: Callable[[str], None] = lambda _: None,
    max_rounds: int = 50,
) -> dict[str, Selection]:
    """
    Resolve the graph from the project's requirements *roots*.

    Each round selects a version for every package REACHABLE from the project through the requirements of the
    versions selected so far (a package an older version required, and nothing requires now, drops out), then
    reads the requirements of the selections not read yet; it stops when nothing new is read.

    Parameters
    ----------
    roots : list[Requirement]
      the project's own dependencies (their exact pins win)
    tags_of : callable
      ``url -> tags`` of a source
    requirements_of : callable
      ``Selection -> requirements`` of the selected version of a package (its fobos ``[dependencies]``)
    warn : callable
      receives the warnings (a dependency's requirement a project pin violates)

    Returns
    -------
    dict[str, Selection]
      by normalised source URL

    Raises
    ------
    ResolutionError
      a requirement no selected version satisfies, two different branch/rev pins, no version satisfying a range
    """
    project = "(project)"
    edges: dict[str, list[Requirement]] = {project: [_normalised(r) for r in roots]}  # requirer key -> requirements
    read: dict[str, tuple[str, str]] = {}  # package key -> (tag, ref) whose requirements are in edges
    tags_cache: dict[str, list[str]] = {}
    for _ in range(max_rounds):
        selected: dict[str, Selection] = {}
        active = {project}
        previous: dict[str, tuple[str, str]] | None = None
        while True:  # the packages reachable from the project with the current selections, to a fixpoint
            requirements: dict[str, list[Requirement]] = {}
            for requirer in sorted(active, key=lambda k: (k != project, k)):  # a fixed order: reproducible
                for requirement in (
                    edges.get(requirer, [])
                    if read.get(requirer, ("", "")) == _version(selected.get(requirer)) or requirer == project
                    else []
                ):
                    requirements.setdefault(normalise_source(requirement.url), []).append(requirement)
            selected = {key: _select_one(key, reqs, tags_cache, tags_of, warn) for key, reqs in requirements.items()}
            versions = {key: _version(sel) for key, sel in selected.items()}
            if versions == previous:
                break
            previous = versions
            active = {project, *selected}
        pending = [key for key, s in selected.items() if read.get(key) != _version(s)]
        if not pending:
            return selected
        for key in pending:
            selection = selected[key]
            read[key] = _version(selection)
            edges[key] = [
                _normalised(Requirement(**{**r.__dict__, "requirer": selection.name}))
                for r in requirements_of(selection)
            ]
    raise ResolutionError("the dependency graph did not settle (a cycle of version changes)")


def _version(selection: Selection | None) -> tuple[str, str]:
    return (selection.tag, selection.ref) if selection is not None else ("", "")


def _select_one(key, reqs, tags_cache, tags_of, warn) -> Selection:
    root = [r for r in reqs if r.requirer == "(project)"]
    is_root = bool(root)
    pinned = [r for r in root if r.tag or r.ref]  # an exact pin of the project wins; its ranges are minimums
    deciding = pinned or reqs
    name = (root or reqs)[0].name
    url = (root or reqs)[0].url
    refs = {r.ref for r in deciding if r.ref}
    if refs:
        if len(refs) > 1:
            listed = ", ".join(f"{r.requirer} wants {r.ref}" for r in deciding if r.ref)
            raise ResolutionError(f"{name}: different branches/commits required ({listed})")
        ref = refs.pop()
        others = [r for r in reqs if r.requirer != "(project)" and r.ref != ref]
        for r in others if pinned else []:
            warn(f"{r.requirer} requires {name} {r.constraint or r.tag or r.ref}; the project follows {ref}")
        return Selection(name, url, ref=ref, required_by=sorted({r.requirer for r in reqs}), root=is_root)
    if url not in tags_cache:
        tags_cache[url] = tags_of(url)
    minimums = [_minimum(r, tags_cache[url]) for r in deciding]
    chosen = max(minimums, key=Version)
    for requirement in reqs:
        if _allows(requirement, chosen):
            continue
        if pinned and requirement.requirer != "(project)":
            warn(
                f"{requirement.requirer} requires {name} {requirement.constraint or requirement.tag or requirement.ref};"
                f" the project's pin selects {chosen}"
            )
            continue
        decided_by = next(r for r in deciding if _minimum(r, tags_cache[url]) == chosen)
        raise ResolutionError(
            f"{name}: {decided_by.requirer} needs at least {chosen}, but {requirement.requirer} requires "
            f"{requirement.constraint or requirement.tag or requirement.ref}"
        )
    return Selection(name, url, tag=chosen, required_by=sorted({r.requirer for r in reqs}), root=is_root)
