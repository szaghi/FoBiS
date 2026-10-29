"""Regression tests of the review of #209: names and URLs read from a dependency's fobos (``transitive = true``) are
not trusted. A name ``..`` must not reach the project directory, a URL must not become a git option, MVS must not
crash when a newer version drops a dependency or on a tag that is not a version, a package name must not leave the
store, and a removed index entry takes its continuation lines with it."""

from __future__ import annotations

import os
import shutil

import pytest

from fobis.Fetcher import Fetcher
from fobis.fobis import run_fobis
from fobis.registry.resolve import Requirement, select
from fobis.registry.store import Store
from fobis.UserConfig import UserConfig
from tests.registry_helpers import fobis_package, isolate, remote

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git")


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    isolate(monkeypatch, tmp_path)


def _run(args, capsys):
    try:
        run_fobis(fake_args=args)
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    return code, captured.out + captured.err


@pytest.mark.parametrize("name", ["..", ".", "../x", "a/b", "-x"])
def test_dependency_names_never_leave_the_deps_dir(tmp_path, name):
    fetcher = Fetcher(deps_dir=str(tmp_path / ".fobis_deps"))
    with pytest.raises(ValueError, match=r"valid dependency name|outside"):
        fetcher.dep_dir(name)


@pytest.mark.parametrize(
    "spec",
    [
        "'--upload-pack=touch PWNED;:' file:///repo",
        "file:///repo :: mirror=--upload-pack=touch PWNED",
        "file:///repo :: rev=--orphan",
        "file:///repo :: tag=v1 x",
    ],
)
def test_urls_and_refs_never_become_git_options(tmp_path, spec):
    with pytest.raises(ValueError, match="is not a"):
        Fetcher(deps_dir=str(tmp_path)).parse_dep_spec(spec)


def test_a_transitive_entry_named_dotdot_cannot_wipe_the_project(tmp_path, monkeypatch, capsys):
    """The reviewer's reproduction: a dependency's fobos names a dependency '..'."""
    evil = remote(tmp_path, "evil", fobis_package("evil"))
    files = fobis_package("a")
    files["fobos"] += f"\n[dependencies]\n.. = {evil} :: rev=master\n"
    a = remote(tmp_path, "a", files)
    project = tmp_path / "proj"
    project.mkdir()
    (project / "SENTINEL").write_text("keep me\n")
    (project / "fobos").write_text(
        f"[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\n\n[dependencies]\ntransitive = true\na = {a} :: semver=^1.0\n"
    )
    monkeypatch.chdir(project)
    _, out = _run(["fetch", "--no-build"], capsys)
    assert (project / "SENTINEL").read_text() == "keep me\n" and (project / "fobos").is_file()
    assert "[dependencies] .. ignored" in out


def test_a_transitive_url_cannot_inject_a_git_option(tmp_path, monkeypatch, capsys):
    pwned = tmp_path / "PWNED"
    files = fobis_package("a")
    files["fobos"] += f"\n[dependencies]\nx = '--upload-pack=touch {pwned};:' file:///repo :: rev=abc\n"
    a = remote(tmp_path, "a", files)
    project = tmp_path / "proj"
    project.mkdir()
    (project / "fobos").write_text(
        f"[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\n\n[dependencies]\ntransitive = true\na = {a} :: semver=^1.0\n"
    )
    monkeypatch.chdir(project)
    _run(["fetch", "--no-build"], capsys)
    assert not pwned.exists()


def test_mvs_when_a_newer_version_drops_a_dependency():
    """a@1 requires b; c raises a to 2, which no longer requires b: b drops out (it crashed with IndexError)."""
    tags = {"u/a": ["v1.0.0", "v2.0.0"], "u/b": ["v1.0.0"], "u/c": ["v1.0.0"]}
    edges = {
        ("a", "v1.0.0"): [Requirement("b", "u/b", "^1.0")],
        ("c", "v1.0.0"): [Requirement("a", "u/a", "^2.0")],
    }

    def requirements_of(selection):
        return [Requirement(**r.__dict__) for r in edges.get((selection.name, selection.tag), [])]

    chosen = select([Requirement("a", "u/a", ">=1.0"), Requirement("c", "u/c", "^1.0")], tags.get, requirements_of)
    assert chosen["u/a"].tag == "v2.0.0" and "u/b" not in chosen


def test_mvs_with_a_tag_that_is_not_a_version():
    chosen = select([Requirement("a", "u/a", tag="stable-2024")], {"u/a": ["stable-2024"]}.get, lambda s: [])
    assert chosen["u/a"].ref == "stable-2024" and not chosen["u/a"].tag


@pytest.mark.parametrize("name", ["/home/u/work", "../../..", ".hidden"])
def test_package_names_never_leave_the_store(tmp_path, name):
    with pytest.raises(ValueError):
        Store(str(tmp_path / "store")).prefix("gnu-16-x", name, "1.0.0")


def test_removed_index_entry_takes_its_continuation_lines(tmp_path):
    path = tmp_path / "config.ini"
    path.write_text("[indexes]\nold = https://x/a\n    continued\nkeep = /b\n")
    cfg = UserConfig(path=str(path))
    cfg.set_indexes([("keep", "/b")])
    assert path.read_text() == "[indexes]\nkeep = /b\n"
    assert os.path.isfile(path)
