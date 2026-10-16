"""Qualified mode keys, ``key.QUALIFIER`` (issue #206 step 9): a key applies when its qualifier is the mode's compiler
or the operating system; flag keys are appended (base, compiler, system, then the command line), the others replaced;
unknown qualifiers and two replacing keys are declaration errors (exit 2); templates; introspect; a real gfortran build
where ``cflags.intel = -xHost`` (which gfortran rejects) is ignored; the docs checker."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from fobis.fobis import run_fobis

pytestmark = pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran")

PROGRAM = "program p\n#ifdef GNU_ONLY\nprint '(A)', 'gnu'\n#endif\n#ifdef ON_LINUX\nprint '(A)', 'linux'\n#endif\nend program\n"
FOBOS = """[modes]
modes = release

[template-common]
compiler       = gnu
cflags.linux   = -DON_LINUX

[release]
template         = template-common
cflags           = -c -O1
cflags.gnu       = -DGNU_ONLY
cflags.intel     = -xHost
cflags.windows   = -static
ext_libs.windows = ws2_32
jobs.gnu         = 2
"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "p.F90").write_text(PROGRAM)
    (tmp_path / "fobos").write_text(FOBOS)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("fobis.Fobos.current_system", lambda: "linux")
    return tmp_path


def _fobis(capsys, *args):
    try:
        run_fobis(fake_args=list(args))
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _introspect(capsys, *extra):
    code, out, _ = _fobis(capsys, "introspect", "--compiler", "--buildoptions", *extra)
    assert code == 0, out
    return json.loads(out)


def test_flags_append_in_order_and_other_keys_replace(project, capsys):
    data = _introspect(capsys)
    assert data["compiler"]["cflags"] == "-c -O1 -DGNU_ONLY -DON_LINUX"  # base, compiler, system (from the template)
    assert data["buildoptions"]["jobs"] == 2
    keys = {q["key"]: q for q in data["buildoptions"]["qualified_keys"]}
    assert keys["cflags.gnu"]["applied"] and keys["cflags.gnu"]["how"] == "appended"
    assert keys["jobs.gnu"]["how"] == "replaced" and keys["jobs.gnu"]["result"] == 2
    assert not keys["cflags.intel"]["applied"] and not keys["ext_libs.windows"]["applied"]
    assert keys["cflags.linux"]["kind"] == "system"


def test_the_system_qualifier(project, capsys, monkeypatch):
    monkeypatch.setattr("fobis.Fobos.current_system", lambda: "windows")
    data = _introspect(capsys)
    assert data["compiler"]["cflags"] == "-c -O1 -DGNU_ONLY -static"
    keys = {q["key"]: q for q in data["buildoptions"]["qualified_keys"]}
    assert keys["ext_libs.windows"]["applied"] and keys["ext_libs.windows"]["result"] == ["ws2_32"]


def test_a_real_build_ignores_the_other_compiler(project, capsys):
    code, out, _ = _fobis(capsys, "build", "--verbose", "--cflags", "-DFROM_CLI")
    assert code == 0, out
    assert "gfortran -c -O1 -DGNU_ONLY -DON_LINUX -DFROM_CLI" in out and "-xHost" not in out
    run = subprocess.run([str(project / "p")], capture_output=True, text=True, check=True)
    assert run.stdout.split() == ["gnu", "linux"]


def test_a_mode_without_base_flags_keeps_the_compile_switch(project, capsys):
    (project / "fobos").write_text("[default]\ncompiler = gnu\ncflags.gnu = -O2\n")
    assert _introspect(capsys)["compiler"]["cflags"] == "-c -O2"  # not "-O2": the files would be linked one by one


def test_declaration_errors(project, capsys):
    (project / "fobos").write_text("[default]\ncompiler = gnu\ncflags.gfortran = -O3\n")
    code, out, err = _fobis(capsys, "build")
    assert code == 2 and "cflags.gfortran: unknown qualifier 'gfortran'" in out + err
    (project / "fobos").write_text("[default]\ncompiler = gnu\nmklib.gnu = static\nmklib.linux = shared\n")
    code, out, err = _fobis(capsys, "build")
    assert code == 2 and "mklib.gnu and mklib.linux both apply and replace mklib" in out + err
    (project / "fobos").write_text("[default]\ncompiler = gnu\ncflags = -c\nlflags.gnu = -g\nlflags.linux = -O1\n")
    assert _introspect(capsys)["compiler"]["lflags"] == "-g -O1"  # flags: both apply, appended


def test_the_docs_checker_knows_the_syntax(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "docs" / "scripts"))
    from check_doc_commands import problems

    (tmp_path / "page.md").write_text(
        "```ini\n[release]\ncflags.gnu = -O2\nlflags.windows = -static\ncflags.gfortran = -O3\nnokey.gnu = 1\n```\n"
    )
    found = {(p.command, p.message) for p in problems(tmp_path)}
    assert found == {
        ("[release] cflags.gfortran", "no such qualifier (compiler or system)"),
        ("[release] nokey.gnu", "fobos modes have no such key"),
    }
