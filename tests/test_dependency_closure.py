"""The complete dependency list of a parsed file (ParsedFile.create_pfile_dep_all, utils.dependency_closure)."""

from __future__ import annotations

import itertools
import random

import pytest

from fobis.ParsedFile import ParsedFile
from fobis.utils import dependency_closure, traverse_recursive, unique_seq


class _Node:
    """A stand-in for ParsedFile: the closure reads only pfile_dep."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.pfile_dep: list[_Node] = []

    def __repr__(self) -> str:
        return self.name


class _CountingNode(_Node):
    """A node counting the reads of its pfile_dep and refusing more than ``limit``: a walk enumerating paths instead
    of files fails at once instead of running for ever."""

    limit = 1

    def __init__(self, name: str) -> None:
        self._deps: list[_CountingNode] = []
        self.reads = 0
        super().__init__(name)

    @property
    def pfile_dep(self) -> list[_CountingNode]:
        self.reads += 1
        if self.reads > self.limit:
            raise AssertionError(f"{self.name}: pfile_dep read {self.reads} times, the walk revisits files")
        return self._deps

    @pfile_dep.setter
    def pfile_dep(self, deps: list[_CountingNode]) -> None:
        self._deps = deps


def _files(n: int, node=_Node) -> list:
    return [node(f"f{i:03d}") for i in range(n)]


def _path_walk(pfile) -> list:
    """The former create_pfile_dep_all: the ends of every path, duplicates dropped."""
    return unique_seq([path[-1] for path in traverse_recursive(pfile)])


def _closure_via_parsed_file(pfile) -> list:
    """The closure as the build computes it: ParsedFile.create_pfile_dep_all reads only pfile_dep, so a node works."""
    ParsedFile.create_pfile_dep_all(pfile)
    return pfile.pfile_dep_all


def test_diamond_order_and_uniqueness(tmp_path):
    """Through ParsedFile itself: the file first, then its dependencies in depth-first pre-order, each once."""
    names = "abcd"
    for n in names:
        (tmp_path / f"{n}.f90").write_text(f"module {n}\nend module {n}\n")
    a, b, c, d = (ParsedFile(name=str(tmp_path / f"{n}.f90"), module=True) for n in names)
    a.pfile_dep, b.pfile_dep, c.pfile_dep, d.pfile_dep = [b, c], [d], [d], []
    a.create_pfile_dep_all()
    assert a.pfile_dep_all == [a, b, d, c]
    assert a.pfile_dep_all == _path_walk(a)


@pytest.mark.parametrize("closure", [dependency_closure, _closure_via_parsed_file])
def test_same_order_as_the_path_walk_on_random_graphs(closure):
    """Acyclic graphs (as dependency_hiearchy ensures) plus what it lets through: a file depending on itself
    (dependency_cycles skips self-edges) and the same dependency listed twice."""
    rng = random.Random(20261107)
    for _ in range(300):
        files = _files(rng.randint(1, 14))
        for i, f in enumerate(files):  # edges only towards higher indices: no cycles
            later = files[i + 1 :]
            f.pfile_dep = rng.sample(later, rng.randint(0, min(4, len(later))))
            if rng.random() < 0.3:
                f.pfile_dep.insert(rng.randint(0, len(f.pfile_dep)), f)
            if f.pfile_dep and rng.random() < 0.3:
                f.pfile_dep.append(rng.choice(f.pfile_dep))
        for f in files:
            assert closure(f) == _path_walk(f)


def test_a_self_dependency_is_listed_once():
    a, b = _files(2)
    a.pfile_dep, b.pfile_dep = [a, b], [b]
    assert dependency_closure(a) == [a, b]


def test_a_cycle_terminates():
    a, b = _files(2)
    a.pfile_dep, b.pfile_dep = [b], [a]
    assert dependency_closure(a) == [a, b]


def test_shared_dependencies_are_visited_once():
    """A ladder of diamonds, 60 deep: 2**60 paths from the top. Through create_pfile_dep_all, so a return to the path
    walk at the call site fails here: each file's dependencies may be read once."""
    levels = 60
    top, *rest = _files(2 * levels + 1, node=_CountingNode)
    pairs = [rest[2 * k : 2 * k + 2] for k in range(levels)]
    top.pfile_dep = list(pairs[0])
    for upper, lower in itertools.pairwise(pairs):
        for f in upper:
            f.pfile_dep = list(lower)
    closure = _closure_via_parsed_file(top)
    assert closure[0] is top
    assert len(closure) == 2 * levels + 1
    assert len(set(closure)) == len(closure)
    assert all(f.reads == 1 for f in (top, *rest))
