"""The build plan (issue #218, phase 1): which files without modules and which submodules a target is built with."""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest

from fobis.fobis import run_fobis
from fobis.plan import external_procedures, logical_lines, make_plan, resolve_policy

GFORTRAN = shutil.which("gfortran") is not None
needs_gfortran = pytest.mark.skipif(not GFORTRAN, reason="gfortran not on PATH")


# --- what a file without modules defines -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "names"),
    [
        ("subroutine a(x)\nend subroutine a\n", ["a"]),
        ("recursive subroutine a()\nend\n", ["a"]),
        ("pure integer function f(x)\nend function\n", ["f"]),
        ("real(kind=8) function g(x) result(y)\nend function g\n", ["g"]),
        ("double precision function h()\nend\n", ["h"]),
        ("type(point_t) function p()\nend function\n", ["p"]),
        ("character(len=*) function c()\nend function\n", ["c"]),
        ("elemental impure real function e(x)\nend function\n", ["e"]),
        # internal procedures are not external
        (
            "subroutine outer()\ncall inner()\ncontains\nsubroutine inner()\nend subroutine inner\nend subroutine\n",
            ["outer"],
        ),
        # a function inside a subroutine, then a second external procedure
        (
            "subroutine s1()\ncontains\nfunction f1()\nend function\nend subroutine\nsubroutine s2()\nend\n",
            ["s1", "s2"],
        ),
        # interface blocks declare, they do not define
        ("interface\nsubroutine ext(x)\nend subroutine\nend interface\nsubroutine mine()\nend\n", ["mine"]),
        ("abstract interface\nfunction cb(x)\nend function\nend interface\n", []),
        # entry points are external names too
        ("subroutine s()\nentry s_alt()\nend subroutine\n", ["s", "s_alt"]),
        # fragments: statements only
        ("x = 1\ncall foo(x)\n", []),
        ("if (a) then\n", []),
        ("print *, 'the subroutine foo is not defined here'\n", []),
        ("! subroutine commented()\n", []),
        # continuation lines and ; separated statements
        ("subroutine long_one(a, &\n   b)\nend subroutine\n", ["long_one"]),
        ("subroutine a(); end subroutine; subroutine b(); end subroutine\n", ["a", "b"]),
        # cpp lines are skipped
        ("#ifdef X\nsubroutine with_cpp()\n#endif\nend subroutine\n", ["with_cpp"]),
    ],
)
def test_external_procedures_free_form(source, names):
    assert external_procedures(source).names == names


def test_external_procedures_fixed_form():
    source = (
        "C     a comment naming subroutine nothing\n"
        "      SUBROUTINE SAXPY(N, A, X,\n"
        "     &                 Y)\n"
        "      CALL HELPER(N)\n"
        "      END\n"
        "*     another comment\n"
        "      REAL*8 FUNCTION DDOT(N)\n"
        "      DDOT = 0\n"
        "      END\n"
    )
    assert external_procedures(source, fixed_form=True).names == ["saxpy", "ddot"]


def test_block_data_and_bind_c():
    found = external_procedures("block data init\ncommon /c/ x\nend block data\n")
    assert found.block_data and found.names == []
    found = external_procedures('subroutine s() bind(c, name="S")\nend subroutine\n')
    assert found.binds_c and found.names == ["s"]


def test_logical_lines_split_and_join():
    assert logical_lines("a = 1; b = 2 ! c ; d\n", fixed_form=False) == ["a = 1", " b = 2"]


# --- the policy -----------------------------------------------------------------------------------------------------


class _Args:
    def __init__(self, **kwargs):
        self.nomodlibs = None
        self.build_all = False
        self.mklib = None
        self.target = None
        self.__dict__.update(kwargs)


def test_policy_defaults_and_errors():
    assert resolve_policy(_Args(target="main.f90")) == "reachable"
    assert resolve_policy(_Args()) == "all"
    assert resolve_policy(_Args(target="lib.f90", mklib="static")) == "all"
    assert resolve_policy(_Args(target="main.f90", build_all=True)) == "all"
    assert resolve_policy(_Args(nomodlibs="None")) == "none"
    with pytest.raises(ValueError, match="one of reachable, all, none"):
        resolve_policy(_Args(nomodlibs="some"))


def test_no_roots_means_all():
    assert make_plan([], [], "reachable").policy == "all"


# --- real builds --------------------------------------------------------------------------------------------------

MAIN = """program main
use m, only : run
implicit none
real :: extf
call run()
print *, extf(2.0)
end program main
"""
MODULE = """module m
implicit none
contains
subroutine run()
call ext_sub()
end subroutine run
end module m
"""
EXT_SUB = "subroutine ext_sub()\nprint *, 'ext_sub'\nend subroutine ext_sub\n"
EXT_FUNC = "real function extf(x)\nreal, intent(in) :: x\nextf = 2 * x\nend function extf\n"
UNRELATED = "subroutine unrelated()\nprint *, 'unrelated'\nend subroutine unrelated\n"
FRAGMENT = "x = 1\ncall foo(x)\n"


def _project(root, **extra):
    src = root / "src"
    (src / "docs").mkdir(parents=True)
    (src / "main.f90").write_text(MAIN)
    (src / "m.f90").write_text(MODULE)
    (src / "ext_sub.f90").write_text(EXT_SUB)
    (src / "extf.f90").write_text(EXT_FUNC)
    (src / "docs" / "unrelated.f90").write_text(UNRELATED)
    (src / "docs" / "fragment.f90").write_text(FRAGMENT)
    for name, text in extra.items():
        path = src / name.replace("__", "/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return src


def _build(*extra, capsys=None):
    run_fobis(fake_args=["build", "--src", "src", "--target", "main.f90", *extra])
    return capsys.readouterr().out if capsys else ""


def _symbols(binary):
    out = subprocess.run(["nm", "--defined-only", str(binary)], capture_output=True, text=True, check=True).stdout
    return {line.split()[-1] for line in out.splitlines() if line.strip()}


@needs_gfortran
def test_reachable_builds_what_the_target_names(tmp_path, monkeypatch, capsys):
    _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    out = _build(capsys=capsys)
    symbols = _symbols(tmp_path / "main")
    assert {"ext_sub_", "extf_"} <= symbols
    assert "unrelated_" not in symbols
    assert "fragment" not in out.replace("fragment(s)", "")  # never compiled
    assert "1 fragment(s) defining no procedure and 1 not reachable" in out
    assert subprocess.run([str(tmp_path / "main")], capture_output=True, text=True).stdout.split() == [
        "ext_sub",
        "4.00000000",
    ]
    out = _build(capsys=capsys)
    assert "Compiling src" not in out  # nothing failed, nothing compiled again


@needs_gfortran
def test_verbose_lists_the_files_left_out(tmp_path, monkeypatch, capsys):
    _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    out = _build("--verbose", capsys=capsys)
    assert "src/docs/fragment.f90: fragment: defines no subroutine, function or block data" in out
    assert "src/docs/unrelated.f90: not reachable: no file of the target names unrelated" in out


@needs_gfortran
def test_all_is_the_old_behaviour_and_failures_are_remembered(tmp_path, monkeypatch, capsys):
    _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    out = _build("--nomodlibs", "all", capsys=capsys)
    assert "unrelated_" in _symbols(tmp_path / "main")
    assert "1 file(s) without modules do not compile and are not linked: src/docs/fragment.f90" in out
    assert json.loads((tmp_path / "obj" / ".fobis-failed.json").read_text())["failed"].keys() == {
        "src/docs/fragment.f90"
    }
    out = _build("--nomodlibs", "all", capsys=capsys)
    assert "Compiling src/docs/fragment.f90" not in out
    assert "(1 unchanged since they failed, not compiled again)" in out
    (tmp_path / "src" / "docs" / "fragment.f90").write_text(UNRELATED.replace("unrelated", "fixed"))
    out = _build("--nomodlibs", "all", capsys=capsys)
    assert "Compiling src/docs/fragment.f90" in out
    assert "fixed_" in _symbols(tmp_path / "main")
    assert not (tmp_path / "obj" / ".fobis-failed.json").exists()


@needs_gfortran
def test_none_links_no_external_procedure(tmp_path, monkeypatch):
    _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _build("--nomodlibs", "none")


@needs_gfortran
def test_a_module_failing_inside_a_non_module_build_is_compiled_again(tmp_path, monkeypatch, capsys):
    broken = "module broken\ninteger :: = 1\nend module broken\n"
    user = "subroutine uses_broken()\nuse broken\nend subroutine uses_broken\n"
    src = _project(tmp_path)
    (src / "broken.f90").write_text(broken)
    (src / "docs" / "uses_broken.f90").write_text(user)
    monkeypatch.chdir(tmp_path)
    # the target does not need the broken module: the file using it is reported, not linked, the build succeeds
    out = _build("--nomodlibs", "all", "--verbose", capsys=capsys)
    assert "src/docs/uses_broken.f90 (a file it uses does not compile: src/broken.f90)" in out
    # the target needs it: before, the module was taken for compiled (its failure ignored); now its compile fails
    (tmp_path / "src" / "main.f90").write_text(MAIN.replace("use m, only : run", "use m, only : run\nuse broken"))
    with pytest.raises(SystemExit):
        _build("--nomodlibs", "all", "--force-compile")


SUBMODULES = {
    "shape__f90": "module shape\ninterface\nmodule subroutine area()\nend subroutine\nend interface\nend module\n",
    "shape_impl__f90": "submodule(shape) shape_impl\ncontains\nmodule subroutine area()\n"
    "print *, 'area'\nend subroutine\nend submodule\n",
    "docs__other__f90": "module other\ninterface\nmodule subroutine o()\nend subroutine\nend interface\nend module\n",
    "docs__other_impl__f90": "submodule (other) other_impl\ninteger :: = broken\nend submodule\n",
    "docs__other_child__f90": "submodule (other : other_impl) other_child\nend submodule\n",
}


@needs_gfortran
def test_submodules_follow_their_ancestor(tmp_path, monkeypatch, capsys):
    files = {name.replace("__f90", ".f90").replace("__", "/"): text for name, text in SUBMODULES.items()}
    src = _project(tmp_path)
    for name, text in files.items():
        (src / name).parent.mkdir(parents=True, exist_ok=True)
        (src / name).write_text(text)
    (src / "main.f90").write_text(
        MAIN.replace("use m, only : run", "use m, only : run\nuse shape").replace(
            "call run()", "call run()\ncall area()"
        )
    )
    monkeypatch.chdir(tmp_path)
    out = _build("--verbose", capsys=capsys)
    assert "__shape_MOD_area" in _symbols(tmp_path / "main")
    # the submodules of a module the target does not use are left out, the broken one included; the child
    # submodule (ancestor:parent syntax) is recognised as a submodule
    assert "src/docs/other_impl.f90: not reachable: the target does not use its ancestor module other" in out
    assert "src/docs/other_child.f90: not reachable: the target does not use its ancestor module other" in out


@needs_gfortran
def test_a_name_built_by_the_preprocessor_is_missed_and_explained(tmp_path, monkeypatch, capsys):
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.F90").write_text("program main\nimplicit none\ncall PASTE(hid,den)()\nend program main\n")
    (src / "hidden.f90").write_text("subroutine hidden()\nend subroutine hidden\n")
    monkeypatch.chdir(tmp_path)
    args = ["build", "--src", "src", "--target", "main.F90", "--cflags", "-c -cpp -DPASTE(a,b)=a/**/b", "--json"]
    with pytest.raises(SystemExit):
        run_fobis(fake_args=args)
    document = json.loads(capsys.readouterr().out)
    facts = [fact for diagnosis in document["diagnoses"] for fact in diagnosis["facts"]]
    assert any("this build leaves that file out: not reachable" in fact for fact in facts), facts
    args[args.index("--json")] = "--nomodlibs"
    run_fobis(fake_args=[*args, "all"])


@needs_gfortran
def test_introspect_sources_says_what_is_left_out(tmp_path, monkeypatch, capsys):
    _project(tmp_path)
    (tmp_path / "fobos").write_text("[default]\ncompiler = gnu\nsrc = ./src/\ntarget = main.f90\n")
    monkeypatch.chdir(tmp_path)
    run_fobis(fake_args=["introspect", "--sources"])
    sources = {s["file"]: s for s in json.loads(capsys.readouterr().out)["sources"]}
    assert sources["./src/docs/fragment.f90"]["left_out"].startswith("fragment")
    assert sources["./src/docs/unrelated.f90"]["left_out"].startswith("not reachable")
    assert "left_out" not in sources["./src/extf.f90"]
    assert not (tmp_path / "obj").exists()


# --- review findings (night of 2026-11-16) -------------------------------------------------------------------------


@needs_gfortran
def test_a_remembered_failure_is_retried_when_a_module_it_uses_is_fixed(tmp_path, monkeypatch, capsys):
    src = tmp_path / "src"
    src.mkdir()
    (src / "helper.f90").write_text("module helper_m\ncontains\nsubroutine twice()\nend subroutine\nend module\n")
    (src / "ext.f90").write_text("subroutine ext_sub()\nuse helper_m, only : thrice\ncall thrice()\nend subroutine\n")
    (src / "main.f90").write_text("program main\ncall ext_sub()\nend program main\n")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):  # ext does not compile: not linked, undefined reference
        _build()
    capsys.readouterr()
    (src / "helper.f90").write_text(
        "module helper_m\ncontains\nsubroutine thrice()\nprint *, 'three'\nend subroutine\nend module\n"
    )
    _build()  # before: 'unchanged since they failed', never compiled again
    assert "three" in subprocess.run([str(tmp_path / "main")], capture_output=True, text=True).stdout


@needs_gfortran
def test_force_compile_retries_remembered_failures(tmp_path, monkeypatch, capsys):
    _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _build("--nomodlibs", "all", capsys=capsys)
    out = _build("--nomodlibs", "all", "--force-compile", capsys=capsys)
    assert "unchanged since they failed" not in out
    assert "Compiling src/docs/fragment.f90" in out


@needs_gfortran
def test_build_all_reports_a_failing_file_without_modules(tmp_path, monkeypatch, capsys):
    _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    run_fobis(fake_args=["build", "--src", "src", "--build-all"])  # before the review: exit 1
    out = capsys.readouterr().out
    assert "do not compile and are not linked: src/docs/fragment.f90" in out
    assert os.path.isfile(tmp_path / "main")


@needs_gfortran
def test_an_override_of_a_library_hook_is_kept(tmp_path, monkeypatch, capsys):
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "solve.f90").write_text("subroutine solve()\ncall hook()\nend subroutine\n")
    (lib / "hook.f90").write_text("subroutine hook()\nprint *, 'library default hook'\nend subroutine\n")
    for name in ("solve", "hook"):
        subprocess.run(["gfortran", "-c", str(lib / f"{name}.f90"), "-o", str(lib / f"{name}.o")], check=True)
    subprocess.run(["ar", "rcs", str(lib / "libext.a"), str(lib / "solve.o"), str(lib / "hook.o")], check=True)
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.f90").write_text("program main\ncall solve()\nend program main\n")
    (src / "hook.f90").write_text("subroutine hook()\nprint *, 'project override hook'\nend subroutine\n")
    monkeypatch.chdir(tmp_path)
    for args in (["--libs", "lib/libext.a"], ["--ext-libs", "ext", "--lib-dir", "lib"]):
        shutil.rmtree(tmp_path / "obj", ignore_errors=True)
        run_fobis(fake_args=["build", "--src", "src", "--target", "main.f90", *args])
        capsys.readouterr()
        out = subprocess.run([str(tmp_path / "main")], capture_output=True, text=True).stdout
        assert "project override hook" in out, args
