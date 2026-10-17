"""Tests for verified modernisation (phase V12c of PLAN-verification.md): the new automatic fixes (OBS005 specific
intrinsics -> generic, OBS008 ``character*n`` -> ``character(len=n)``, OBS011 labelled DO -> ``do ... end do``, in
free and fixed form, case kept; a referenced label or a shared terminal left alone; ``end do`` at the column of its
``do``, never in the label field or on column 6), duplicate test program names, and ``fobis modernize`` for real with
gfortran: fixes verified by tests and cases then applied, a fix that changes results caught and reported per rule,
build-only evidence refused without --unverified, a file changed since the analysis left alone."""

from __future__ import annotations

import json
import os
import subprocess

import pytest

from fobis.fobis import run_fobis
from fobis.lint import apply_fixes, lint_text, select_rules
from fobis.TestRunner import discover_tests

GIT = ["git", "-c", "user.name=T", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]


def _fixed(text: str, path: str, rules: str) -> str:
    findings = lint_text(text, path, select_rules(rules.split(","), []))
    return apply_fixes(text, [f for f in findings if f.fixes])[0]


def test_free_form_fixes():
    text = (
        "subroutine s(n, a, name)\n  integer n, i, j\n  double precision a(n)\n  character*8 name\n"
        "  character*(*), parameter :: t = 'x'\n  do 10 i = 1, n\n    a(i) = dsqrt(dabs(a(i))) + float(i)\n"
        "10 continue\n  do 20, j = 1, n\n    if (a(j) > 1d0) go to 20\n    a(j) = amax0(1, 2)\n20 continue\n"
        "end subroutine s\n"
    )
    fixed = _fixed(text, "s.f90", "OBS005,OBS008,OBS011")
    assert "character(len=8) name" in fixed and "character(len=*), parameter" in fixed
    assert "  do i = 1, n\n    a(i) = sqrt(abs(a(i))) + real(i)\n  end do\n" in fixed
    assert "do 20, j = 1, n" in fixed and "20 continue" in fixed  # the label is a go to target: left
    assert "amax0(1, 2)" in fixed  # converts the result type: no mechanical fix


def test_fixed_form_fixes():
    text = (
        "      SUBROUTINE T(N,X)\n      DIMENSION X(1)\n      CHARACTER*8 S\n  103 DO 104 I=1,N\n"
        "      X(I) = SNGL(DSQRT(1.D0))\n  104 CONTINUE\n      DO 105 I=1,N\n      DO 105 J=1,N\n  105 CONTINUE\n"
        "      IF (N .GT. 1) GO TO 103\n      END\n"
    )
    fixed = _fixed(text, "t.f", "OBS005,OBS008,OBS011")
    lines = fixed.splitlines()
    assert lines[3] == "  103 DO I=1,N" and lines[5] == "      END DO"  # column 7, not 3 (the label's)
    assert lines[2] == "      CHARACTER(LEN=8) S" and "REAL(SQRT(1.D0))" in lines[4]
    assert "DO 105 I=1,N" in fixed and "DO 105 J=1,N" in fixed  # a shared terminal: left


def test_duplicate_test_names(tmp_path):
    for name in ("a", "b"):
        (tmp_path / f"t_{name}.f90").write_text("program tester\nend program tester\n")
    (tmp_path / "t_c.f90").write_text("program unique\nend program unique\n")
    assert sorted(t["name"] for t in discover_tests(str(tmp_path))) == ["t_a", "t_b", "unique"]


# ── the command, for real ──────────────────────────────────────────────────────

LEGACY = """\
      SUBROUTINE SCALE(N, X, F)
      INTEGER N, I
      DOUBLE PRECISION X(N), F
      DO 10 I = 1, N
         X(I) = DSQRT(X(I)) * F
   10 CONTINUE
      IF (N .EQ. 0) RETURN
      END
"""
PROGRAM = """\
program app
implicit none
double precision :: x(3)
x = [1.d0, 4.d0, 9.d0]
call scale(3, x, 2.d0)
print '(a,es24.16)', 'x1 = ', x(1)
print '(a,es24.16)', 'x3 = ', x(3)
end program app
"""
TEST = """\
program t_scale
implicit none
double precision :: x(2)
x = [4.d0, 16.d0]
call scale(2, x, 1.d0)
if (any(abs(x - [2.d0, 4.d0]) > 1.d-12)) error stop 1
end program t_scale
"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    for path, text in {"src/legacy.f": LEGACY, "src/app.f90": PROGRAM, "test/t_scale.f90": TEST}.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)
    (root / "fobos").write_text(
        "[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\nsrc = ./src/ ./test/\nbuild_dir = ./build/\ncflags = -c -O1\n\n"
        "[case:app]\ntarget = src/app.f90\nquantities = stdout\n"
    )
    (root / ".gitignore").write_text("build/\n.fobis/\n")
    monkeypatch.chdir(root)
    subprocess.run([*GIT, "init", "-q"], check=True)
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    return root


def _run(args, capsys):
    try:
        run_fobis(fake_args=args)
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_modernize_verified_and_applied(project, capsys, tmp_path):
    code, out, _ = _run(["modernize", "--json"], capsys)
    data = json.loads(out)
    assert code == 0 and data["status"] == "verified" and data["verified"] == ["MDN021", "OBS005", "OBS011"]
    assert data["checks"][0]["evidence"] == "tests+cases" and data["checks"][0]["cases"] == "equivalent"
    assert (project / "src" / "legacy.f").read_text() == LEGACY  # nothing written without --apply
    assert not [p for p in os.listdir(tmp_path) if p.startswith("fobis-modernize-")]  # scratch removed
    code, out, _ = _run(["modernize", "--apply", "--json"], capsys)
    assert code == 0 and json.loads(out)["applied"] == ["src/legacy.f"]
    modern = (project / "src" / "legacy.f").read_text()
    assert "DO I = 1, N" in modern and "END DO" in modern and "SQRT(X(I))" in modern and "N == 0" in modern
    code, out, _ = _run(["modernize"], capsys)
    assert code == 0 and "nothing to modernise" in out
    code, out, err = _run(["modernize", "--select", "COR010"], capsys)  # a rule with no fix: it was exit 0
    assert code == 2 and "COR010 has no automatic fix" in out + err


def test_modernize_catches_a_change(project, capsys, monkeypatch):
    """A fix that changes results (here OBS005's map pointed at a wrong function) is caught; the others pass."""
    from fobis.lint.rules import obsolescent

    monkeypatch.setitem(obsolescent.GENERIC_OF, "dsqrt", "exp")
    code, out, _ = _run(["modernize", "--json"], capsys)
    data = json.loads(out)
    assert code == 1 and data["status"] == "partial" and data["verified"] == ["MDN021", "OBS011"]
    failed = next(c for c in data["checks"] if c["rules"] == ["OBS005"])
    assert failed["tests"] == "stopped passing: t_scale" and failed["cases"].startswith("app: differs")


def test_modernize_build_only_and_concurrent_edit(project, capsys, monkeypatch):
    (project / "fobos").write_text((project / "fobos").read_text().split("[case:app]")[0])
    os.remove(project / "test" / "t_scale.f90")
    code, out, _ = _run(["modernize", "--apply", "--json"], capsys)
    data = json.loads(out)
    assert code == 1 and data["checks"][0]["evidence"] == "build" and data["applied"] == []  # refused: it was exit 0
    assert "--unverified" in data["notes"][0]
    from fobis.verification import modernize as mz

    original = mz.fixed_texts

    def edited_meanwhile(plan, rules, read):  # the user edits the file while the copies are checked
        (project / "src" / "legacy.f").write_text(LEGACY + "C edited\n")
        return original(plan, rules, read)

    monkeypatch.setattr(mz, "fixed_texts", edited_meanwhile)
    code, out, _ = _run(["modernize", "--apply", "--unverified", "--json"], capsys)
    data = json.loads(out)
    assert code == 1 and data["applied"] == [] and "changed since the analysis" in data["notes"][0]
