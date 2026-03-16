"""Unit tests for --json structured output (issue #161)."""

import json
import textwrap

import pytest

from fobis.fobis import _all_files, _JsonCollector, _obj_files

# ---------------------------------------------------------------------------
# _JsonCollector
# ---------------------------------------------------------------------------


class TestJsonCollector:
    def test_initial_state(self):
        c = _JsonCollector()
        assert c.messages == []
        assert c.warnings == []

    def test_print_n_buffers(self):
        c = _JsonCollector()
        c.print_n("hello")
        c.print_n("world")
        assert c.messages == ["hello", "world"]

    def test_print_w_buffers(self):
        c = _JsonCollector()
        c.print_w("warn1")
        assert c.warnings == ["warn1"]

    def test_print_n_default_empty(self):
        c = _JsonCollector()
        c.print_n()
        assert c.messages == [""]

    def test_print_w_default_empty(self):
        c = _JsonCollector()
        c.print_w()
        assert c.warnings == [""]


# ---------------------------------------------------------------------------
# _obj_files / _all_files helpers
# ---------------------------------------------------------------------------


class TestFileHelpers:
    def test_obj_files_missing_dir(self, tmp_path):
        assert _obj_files(str(tmp_path / "nonexistent")) == set()

    def test_obj_files_finds_dot_o(self, tmp_path):
        (tmp_path / "foo.o").write_text("x")
        (tmp_path / "bar.f90").write_text("x")
        result = _obj_files(str(tmp_path))
        assert result == {str(tmp_path / "foo.o")}

    def test_obj_files_recursive(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "baz.o").write_text("x")
        result = _obj_files(str(tmp_path))
        assert str(sub / "baz.o") in result

    def test_all_files_missing_dir(self, tmp_path):
        assert _all_files(str(tmp_path / "nonexistent")) == set()

    def test_all_files_returns_all(self, tmp_path):
        (tmp_path / "a.o").write_text("x")
        (tmp_path / "b.mod").write_text("x")
        result = _all_files(str(tmp_path))
        assert result == {str(tmp_path / "a.o"), str(tmp_path / "b.mod")}


# ---------------------------------------------------------------------------
# Integration tests: fobis build/clean --json
# ---------------------------------------------------------------------------


def _build_fobos(tmp_path, content):
    """Write a fobos file to tmp_path."""
    (tmp_path / "fobos").write_text(textwrap.dedent(content))


def _build_source(tmp_path, name, content):
    """Write a Fortran source file to tmp_path."""
    (tmp_path / name).write_text(textwrap.dedent(content))


@pytest.fixture
def simple_project(tmp_path):
    """Minimal single-program project."""
    _build_source(
        tmp_path,
        "hello.f90",
        """\
        program hello
          print *, 'hello json'
        end program hello
        """,
    )
    _build_fobos(
        tmp_path,
        f"""\
        [default]
        src = {tmp_path}
        build_dir = {tmp_path}/build
        obj_dir = obj
        mod_dir = mod
        compiler = gnu
        """,
    )
    return tmp_path


class TestBuildJson:
    def test_build_json_ok(self, simple_project, monkeypatch, capsys):
        monkeypatch.chdir(simple_project)
        from fobis.fobis import run_fobis

        run_fobis(fake_args=["build", "--fobos", "fobos", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["status"] == "ok"
        assert "target" in data
        assert isinstance(data["objects_compiled"], int)
        assert isinstance(data["errors"], list)

    def test_build_json_objects_counted(self, simple_project, monkeypatch, capsys):
        monkeypatch.chdir(simple_project)
        from fobis.fobis import run_fobis

        run_fobis(fake_args=["build", "--fobos", "fobos", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        # One source file → at least one object compiled
        assert data["objects_compiled"] >= 1

    def test_build_json_rebuild_skips(self, simple_project, monkeypatch, capsys):
        monkeypatch.chdir(simple_project)
        from fobis.fobis import run_fobis

        # First build
        run_fobis(fake_args=["build", "--fobos", "fobos", "--json"])
        capsys.readouterr()
        # Second build — objects already up to date
        run_fobis(fake_args=["build", "--fobos", "fobos", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["status"] == "ok"
        assert data["objects_compiled"] == 0  # nothing recompiled


class TestCleanJson:
    def test_clean_json_after_build(self, simple_project, monkeypatch, capsys):
        monkeypatch.chdir(simple_project)
        from fobis.fobis import run_fobis

        # Build first
        run_fobis(fake_args=["build", "--fobos", "fobos"])
        capsys.readouterr()
        # Now clean with --json
        run_fobis(fake_args=["clean", "--fobos", "fobos", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["status"] == "ok"
        assert isinstance(data["removed"], list)
        assert isinstance(data["errors"], list)

    def test_clean_json_removes_objects(self, simple_project, monkeypatch, capsys):
        monkeypatch.chdir(simple_project)
        from fobis.fobis import run_fobis

        # Build first
        run_fobis(fake_args=["build", "--fobos", "fobos"])
        capsys.readouterr()
        # Clean
        run_fobis(fake_args=["clean", "--fobos", "fobos", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        # All reported removed files should end with .o, .mod, or .smod
        for f in data["removed"]:
            assert f.endswith((".o", ".mod", ".smod")), f"Unexpected file in removed: {f}"

    def test_clean_json_empty_project(self, simple_project, monkeypatch, capsys):
        """Clean on a never-built project should succeed with empty removed list."""
        monkeypatch.chdir(simple_project)
        from fobis.fobis import run_fobis

        run_fobis(fake_args=["clean", "--fobos", "fobos", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["status"] == "ok"
        assert data["removed"] == []
