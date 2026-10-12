"""Tests for ``fobis ecosystem impact``: the public API of Fortran modules (access statements, generics, types,
constants), the API change between a tag and the working tree, re-exports, the usages in dependent projects
(references, only lists, renames, removed names), the reports, and the CLI on a temporary ecosystem (the model is
a FakeProvider)."""

from __future__ import annotations

import json
import subprocess

import pytest
from typer.testing import CliRunner

from fobis.ai.impact import (
    Impact,
    api_changes,
    fortran_sources,
    impact_bundle,
    module_api,
    project_changes,
    render_markdown,
    render_text,
    usages_in,
)
from fobis.cli import app
from fobis.lint.engine import analyse
from fobis.llm import FakeProvider

GEOMETRY = """\
module geometry
use kinds, only: rk
implicit none
private
public :: area, scale_all, point, unit_length, shift, perimeter
real(rk), parameter :: unit_length = 1.0_rk
type :: point
  real(rk) :: x, y
end type point
interface shift
  module procedure shift_point
end interface shift
contains
pure function area(r) result(a)
real(rk), intent(in) :: r
real(rk) :: a
a = 3.14159_rk * r**2
end function area
subroutine scale_all(x, s)
real(rk), intent(inout) :: x(:)
real(rk), intent(in) :: s
x = x * s
end subroutine scale_all
function perimeter(r) result(p)
real(rk), intent(in) :: r
real(rk) :: p
p = 2 * 3.14159_rk * r
end function perimeter
subroutine shift_point(p, d)
type(point), intent(inout) :: p
real(rk), intent(in) :: d
p%x = p%x + d
end subroutine shift_point
subroutine helper()
end subroutine helper
end module geometry
"""
KINDS = "module kinds\nimplicit none\ninteger, parameter :: rk = kind(1.d0)\nend module kinds\n"
FACADE = "module lib\nuse geometry\nimplicit none\nprivate\npublic :: area, point\nend module lib\n"
APP = """\
program app
use geometry, only: area, sc => scale_all
use kinds, only: rk
implicit none
real(rk) :: v(3) = 1.0_rk
print *, area(2.0_rk)
call sc(v, 2.0_rk)
end program app
"""
VIEWER = """\
program viewer
use lib
implicit none
type(point) :: p
print *, area(1.0d0)
end program viewer
"""


def _git(repo, *args) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


def _api(text: str) -> dict:
    return module_api(analyse(text, "x.f90"))


# ── public API ─────────────────────────────────────────────────────────────────


def test_module_api_follows_access_statements():
    api = _api(GEOMETRY)["geometry"]
    assert sorted(api) == ["area", "perimeter", "point", "scale_all", "shift", "unit_length"]  # helper is private
    assert api["area"].signature.splitlines() == [
        "pure function area(r)",
        "real(rk), intent(in) :: r",
        "result: real(rk) :: a",
    ]
    assert api["shift"].kind == "generic" and api["shift"].signature == "generic: shift_point"
    assert api["point"].kind == "type" and "real(rk) :: x, y" in api["point"].signature
    assert api["unit_length"].signature == "real(rk), parameter :: unit_length = 1.0_rk"
    public_default = _api("module m\ninteger :: counter\ncontains\nsubroutine s()\nend subroutine s\nend module m\n")
    assert sorted(public_default["m"]) == ["counter", "s"]


def test_api_changes():
    old = _api(GEOMETRY)
    new_text = (
        GEOMETRY.replace("subroutine scale_all(x, s)", "subroutine scale_all(x, s, n)")
        .replace("x = x * s", "x = x * s * n")
        .replace(", perimeter\n", ", diameter\n")
        .replace("function perimeter(r) result(p)", "function diameter(r) result(p)")
        .replace("end function perimeter", "end function diameter")
        .replace("unit_length = 1.0_rk", "unit_length = 2.0_rk")
    )
    changes = {(c.name, c.change) for c in api_changes(old, _api(new_text))}
    assert changes == {
        ("scale_all", "changed"),
        ("perimeter", "removed"),
        ("diameter", "added"),
        ("unit_length", "changed"),
    }
    (gone,) = api_changes(old, {})
    assert (gone.kind, gone.change, gone.breaking) == ("module", "removed", True)


# ── ecosystem ──────────────────────────────────────────────────────────────────


def _project(root, name, files: dict[str, str], deps: dict[str, str] | None = None):
    repo = root / name
    (repo / "src").mkdir(parents=True)
    for path, text in files.items():
        (repo / "src" / path).write_text(text)
    fobos = "[default]\ncompiler = gnu\nsrc = ./src/\n"
    if deps:
        fobos += "\n[dependencies]\ndeps_dir = third_party\n" + "".join(f"{k} = {v}\n" for k, v in deps.items())
    (repo / "fobos").write_text(fobos)
    (repo / ".gitignore").write_text("third_party/\n")
    _git(repo, "init", "-q", "-b", "master")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "feat: initial")
    _git(repo, "tag", "v1.0.0")
    return repo


@pytest.fixture
def eco(tmp_path, monkeypatch):
    """geom (the library) <- app (uses it directly) <- viewer (uses its facade module lib)."""
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("[user]\n\tname = T\n\temail = t@t\n[commit]\n\tgpgsign = false\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    geom = _project(tmp_path, "geom", {"kinds.f90": KINDS, "geometry.f90": GEOMETRY, "lib.f90": FACADE})
    _project(tmp_path, "app", {"app.f90": APP}, {"geom": "https://github.com/demo/geom"})
    _project(tmp_path, "viewer", {"viewer.f90": VIEWER}, {"app": "https://github.com/demo/app"})
    cfg = tmp_path / "config.ini"
    cfg.write_text(f"[ecosystem]\nroot = {tmp_path}\nprojects = geom app viewer\n")
    return tmp_path, geom, str(cfg)


def _break(geom):
    path = geom / "src" / "geometry.f90"
    text = path.read_text()
    text = text.replace("pure function area(r) result(a)", "pure function area(r, scale) result(a)")
    text = text.replace("real(rk), intent(in) :: r\nreal(rk) :: a", "real(rk), intent(in) :: r, scale\nreal(rk) :: a")
    text = text.replace(", perimeter\n", "\n")
    path.write_text(text)


def test_project_changes_and_reexports(eco):
    _, geom, _ = eco
    assert project_changes(str(geom)) == ("v1.0.0", [])
    _break(geom)
    base, changes = project_changes(str(geom))
    assert base == "v1.0.0"
    assert {(c.module, c.name, c.change, c.via) for c in changes} == {
        ("geometry", "area", "changed", ""),
        ("geometry", "perimeter", "removed", ""),
        ("lib", "area", "changed", "geometry::area"),  # re-exported by the facade module
    }


def test_usages_in_dependents(eco):
    root, geom, _ = eco
    _break(geom)
    _, changes = project_changes(str(geom))
    app_usages = usages_in("app", str(root / "app"), changes, fortran_sources(str(root / "app")))
    assert [(u.path, u.line, u.names) for u in app_usages] == [("src/app.f90", 2, ["area"])]
    assert app_usages[0].references == [(6, "area", "print *, area(2.0_rk)")]
    viewer = usages_in("viewer", str(root / "viewer"), changes, fortran_sources(str(root / "viewer")))
    assert [(u.module, u.names) for u in viewer] == [("lib", ["area"])]  # through the facade


def test_removed_name_in_an_only_list_breaks_the_use(eco):
    root, geom, _ = eco
    _break(geom)
    extra = root / "app" / "src" / "extra.f90"
    extra.write_text("subroutine extra()\nuse geometry, only: perimeter\nend subroutine extra\n")
    _, changes = project_changes(str(geom))
    found = usages_in("app", str(root / "app"), changes, [str(extra)])
    assert [(u.names, u.references) for u in found] == [(["perimeter"], [])]


def test_reports(eco):
    root, geom, _ = eco
    _break(geom)
    base, changes = project_changes(str(geom))
    usages = usages_in("app", str(root / "app"), changes, fortran_sources(str(root / "app")))
    impact = Impact("geom", base, changes, ["app", "viewer"], usages)
    text = render_text(impact)
    assert "BREAKING changed procedure geometry::area" in text and "- pure function area(r)" in text
    assert "+ pure function area(r, scale)" in text and "lib::area (re-exports geometry::area)" in text
    assert "app: affected\n  src/app.f90:2: use geometry, only: area, sc => scale_all  [changed: area]" in text
    assert "viewer: not affected" in text and "3 breaking change(s); 1 of 2 dependent project(s) affected." in text
    markdown = render_markdown(impact)
    assert "| **breaking**: removed | procedure `geometry::perimeter` |" in markdown
    assert "- **app**: 1 place(s) to update" in markdown
    data = impact.to_dict()
    assert data["usages"][0]["references"] == [{"line": 6, "name": "area", "statement": "print *, area(2.0_rk)"}]
    assert [s.id for s in impact_bundle(impact).sources][-1] == "use:app:src/app.f90:2"


def test_cli(eco, monkeypatch):
    root, geom, cfg = eco
    runner = CliRunner()
    result = runner.invoke(app, ["ecosystem", "impact", "geom", "-c", cfg])
    assert result.exit_code == 0, result.output
    assert "none (no public interface" in result.output
    _break(geom)
    result = runner.invoke(app, ["ecosystem", "impact", "geom", "-c", cfg])
    assert result.exit_code == 1 and "app: affected" in result.output and "viewer: affected" in result.output
    data = json.loads(runner.invoke(app, ["ecosystem", "impact", "geom", "-c", cfg, "--format", "json"]).output)
    assert data["base"] == "v1.0.0" and {u["project"] for u in data["usages"]} == {"app", "viewer"}
    markdown = runner.invoke(app, ["ecosystem", "impact", "geom", "-c", cfg, "--format", "markdown"]).output
    assert markdown.startswith("### Impact of `geom` changes since `v1.0.0`")
    assert runner.invoke(app, ["ecosystem", "impact", "geom", "-c", cfg, "--format", "html"]).exit_code == 2
    context = runner.invoke(app, ["ecosystem", "impact", "geom", "-c", cfg, "--deep-context"])
    assert context.exit_code == 0 and "=== system prompt ===" in context.output
    answer = {
        "insufficient": False,
        "claims": [{"kind": "breaking", "text": "app calls area with one argument.", "citations": ["S1", "S4"]}],
    }
    provider = FakeProvider([json.dumps(answer)])
    monkeypatch.setattr("fobis.llm.get_provider", lambda c, on_status=None: provider)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(root / "xdg"))
    deep = runner.invoke(app, ["ecosystem", "impact", "geom", "-c", cfg, "--deep"])
    assert "Summary [llm]:\nWhat breaks:\n  - app calls area with one argument. [1][2]" in deep.output
    assert len(provider.calls) == 1
