"""Tests for FoBiS.py build functionality."""

import shutil
import subprocess

import pytest

from tests.helpers import OPENCOARRAYS, PREFORM, run_build


@pytest.mark.parametrize("n", range(1, 33))
def test_build(monkeypatch, n):
    """Test build scenario n."""
    if n == 15 and not OPENCOARRAYS:
        pytest.skip("opencoarrays (caf) not available")
    if n == 5 and not PREFORM:
        pytest.skip("PreForM.py not available")
    assert run_build(monkeypatch, f"build-test{n}"), f"build-test{n} failed"


@pytest.mark.skipif(not all(shutil.which(tool) for tool in ("gfortran", "ar")), reason="tools")
def test_a_static_library_does_not_hold_other_libraries(tmp_path, monkeypatch, capsys):
    """libs in a static mode put the given .a inside the new archive, where the linker never looks."""
    from fobis.fobis import run_fobis

    ext = tmp_path / "ext"
    ext.mkdir()
    (ext / "ext.f90").write_text("module ext\ncontains\ninteger function two()\ntwo = 2\nend function\nend module\n")
    subprocess.run(["gfortran", "-c", "ext.f90"], cwd=ext, check=True)
    subprocess.run(["ar", "rcs", "libext.a", "ext.o"], cwd=ext, check=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "my.f90").write_text(
        "module my\nuse ext\ncontains\ninteger function four()\nfour = 2 * two()\nend function\nend module\n"
    )
    (tmp_path / "fobos").write_text(
        "[default]\ncompiler = gnu\ncflags = -c\nsrc = ./src/\nbuild_dir = ./build/\ninclude = ./ext/\n"
        "target = src/my.f90\nmklib = static\noutput = libmy.a\nlibs = ./ext/libext.a\n"
    )
    monkeypatch.chdir(tmp_path)
    run_fobis(fake_args=["build"])
    out = capsys.readouterr()
    assert "does not contain ./ext/libext.a: a program using it links them too" in out.out + out.err
    members = subprocess.run(["ar", "t", "build/libmy.a"], capture_output=True, text=True, check=True).stdout.split()
    assert members == ["my.o"]
    (tmp_path / "p.f90").write_text("program p\nuse my\nprint '(I0)', four()\nend program\n")
    subprocess.run(
        ["gfortran", "p.f90", "-Ibuild/mod", "-Iext", "build/libmy.a", "ext/libext.a", "-o", "p"],
        cwd=tmp_path,
        check=True,
    )
    assert subprocess.run(["./p"], cwd=tmp_path, capture_output=True, text=True).stdout.strip() == "4"
