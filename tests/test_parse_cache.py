"""FoBiS's own time (issue #218, phase 5): the parse cache and the cheaper parse give the same facts."""

from __future__ import annotations

import glob
import os
import shutil
import time

import pytest

from fobis import fobis as fobis_module
from fobis.FoBiSConfig import FoBiSConfig
from fobis.parsecache import CACHE_FILE
from fobis.ParsedFile import _preprocessor_changes

TESTS = os.path.dirname(os.path.abspath(__file__))


def _facts(pfiles):
    return {
        p.name: (
            p.program,
            p.module,
            p.submodule,
            p.include,
            p.nomodlib,
            tuple(p.module_names or []),
            tuple(p.submodule_names or []),
            p.submodule_ancestor,
            tuple((d.type, d.name, bool(d.located)) for d in p.dependencies or []),
            None if p.external_procedures is None else tuple(p.external_procedures.names),
        )
        for p in pfiles
    }


def _parse(*args):
    configuration = FoBiSConfig(fake_args=["build", *args])
    return _facts(fobis_module.parse_files(configuration=configuration, use_cache=True))


@pytest.mark.parametrize(
    "fixture", sorted(os.path.basename(d) for d in glob.glob(os.path.join(TESTS, "build-test*")) if os.path.isdir(d))
)
def test_cached_facts_equal_parsed_facts(tmp_path, monkeypatch, fixture):
    shutil.copytree(os.path.join(TESTS, fixture), tmp_path / fixture)
    monkeypatch.chdir(tmp_path / fixture)
    fresh = _parse("--no-parse-cache")
    first = _parse()
    cached = _parse()
    assert fresh == first == cached
    assert glob.glob(f"**/{CACHE_FILE}", recursive=True) or not fresh


def _project(root):
    src = root / "src"
    src.mkdir()
    (src / "inc").mkdir()
    (src / "a.f90").write_text("module a\nend module a\n")
    (src / "b.f90").write_text("module b\nend module b\n")
    (src / "inc" / "pick.h").write_text("#define USED a\n")
    (src / "p.F90").write_text('#include "inc/pick.h"\nprogram p\nuse USED\nend program p\n')
    return src


def _uses(facts, name):
    return [dep for kind, dep, _ in facts[name][8] if kind == "module"]


def test_an_edit_or_an_included_header_invalidates(tmp_path, monkeypatch):
    src = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert _uses(_parse("--src", "src"), "src/p.F90") == ["a"]
    time.sleep(0.02)
    (src / "inc" / "pick.h").write_text("#define USED b\n")  # only the header changes
    assert _uses(_parse("--src", "src"), "src/p.F90") == ["b"]
    time.sleep(0.02)
    (src / "a.f90").write_text("module a\nuse b\nend module a\n")
    assert _uses(_parse("--src", "src"), "src/a.f90") == ["b"]


def test_other_flags_invalidate(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.f90").write_text("module a\nend module a\n")
    (src / "b.f90").write_text("module b\nend module b\n")
    (src / "p.F90").write_text("program p\nuse WHICH\nend program p\n")
    monkeypatch.chdir(tmp_path)
    assert _uses(_parse("--src", "src", "--preproc", "-DWHICH=a"), "src/p.F90") == ["a"]
    assert _uses(_parse("--src", "src", "--preproc", "-DWHICH=b"), "src/p.F90") == ["b"]


@pytest.mark.parametrize(
    ("text", "preproc", "expected"),
    [
        ("module a\nend module\n", "", False),
        ("#ifdef X\nuse b\n#endif\n", "", True),
        ("  # include 'x'\n", "", True),
        ("use WHICH\n", "-DWHICH=a", True),
        ("use WHICHEVER\n", "-DWHICH=a", False),
        ("real :: linux\n", "", True),  # a name cpp defines itself
        ("x = a # b\n", "", False),
    ],
)
def test_when_the_preprocessor_can_change_a_file(text, preproc, expected):
    assert _preprocessor_changes(text, preproc) is expected
