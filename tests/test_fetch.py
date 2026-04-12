"""Tests for FoBiS.py fetch dependency modes."""

import configparser
import os
import tempfile
from unittest.mock import patch

import pytest

from fobis.Fetcher import Fetcher
from tests.helpers import run_build

# ── unit tests: save_config / load_config ────────────────────────────────────


def test_fetch_sources_dep_goes_to_src_key():
    """use=sources dep must appear under 'src', not 'dependon'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fetcher = Fetcher(deps_dir=tmpdir)
        deps_info = [
            {"name": "src_dep", "path": "/fake/src_dep", "mode": "", "use": "sources"},
            {"name": "fobos_dep", "path": "/fake/fobos_dep", "mode": "gnu", "use": "fobos"},
        ]
        fetcher.save_config(deps_info)
        cfg = fetcher.load_config()

        assert "src" in cfg
        assert "/fake/src_dep" in cfg["src"]
        assert "/fake/src_dep" not in " ".join(cfg.get("dependon", []))
        assert "dependon" in cfg
        assert any("/fake/fobos_dep/fobos:gnu" in e for e in cfg["dependon"])
        assert "/fake/fobos_dep" not in cfg.get("src", [])


def test_fetch_default_use_is_sources():
    """Default use=sources must produce 'src' key only — no 'dependon'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fetcher = Fetcher(deps_dir=tmpdir)
        deps_info = [{"name": "dep", "path": "/fake/default", "mode": "", "use": "sources"}]
        fetcher.save_config(deps_info)
        cfg = fetcher.load_config()

        assert "src" in cfg
        assert "dependon" not in cfg


def test_fetch_fobos_dep_no_mode_no_colon():
    """use=fobos dep without a mode must have no colon suffix in the fobos path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fetcher = Fetcher(deps_dir=tmpdir)
        deps_info = [{"name": "dep", "path": "/fake/fobos_dep", "mode": "", "use": "fobos"}]
        fetcher.save_config(deps_info)
        cfg = fetcher.load_config()

        assert "dependon" in cfg
        assert cfg["dependon"] == ["/fake/fobos_dep/fobos"]


def test_fetch_load_config_empty():
    """load_config on a missing file must return an empty dict."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fetcher = Fetcher(deps_dir=tmpdir)
        assert fetcher.load_config() == {}


# ── parse_dep_spec body (lines previously uncovered) ─────────────────────────


def test_parse_dep_spec_url_only():
    fetcher = Fetcher(deps_dir="/fake")
    result = fetcher.parse_dep_spec("https://github.com/user/repo")
    assert result == {"url": "https://github.com/user/repo"}


def test_parse_dep_spec_with_tag():
    fetcher = Fetcher(deps_dir="/fake")
    result = fetcher.parse_dep_spec("https://github.com/user/repo :: tag=v1.0.0")
    assert result["tag"] == "v1.0.0"
    assert result["url"] == "https://github.com/user/repo"


def test_parse_dep_spec_multiple_options():
    fetcher = Fetcher(deps_dir="/fake")
    result = fetcher.parse_dep_spec("https://github.com/user/repo :: branch=main :: mode=gnu")
    assert result["branch"] == "main"
    assert result["mode"] == "gnu"


# ── _resolve_url() ────────────────────────────────────────────────────────────


def test_resolve_url_shorthand_to_github():
    fetcher = Fetcher(deps_dir="/fake")
    assert fetcher._resolve_url("user/repo") == "https://github.com/user/repo"


def test_resolve_url_full_https_unchanged():
    fetcher = Fetcher(deps_dir="/fake")
    url = "https://github.com/user/repo"
    assert fetcher._resolve_url(url) == url


def test_resolve_url_http_unchanged():
    fetcher = Fetcher(deps_dir="/fake")
    url = "http://example.com/repo"
    assert fetcher._resolve_url(url) == url


def test_resolve_url_git_at_unchanged():
    fetcher = Fetcher(deps_dir="/fake")
    url = "git@github.com:user/repo.git"
    assert fetcher._resolve_url(url) == url


# ── fetch() — git operations mocked ──────────────────────────────────────────


def test_fetch_clones_new_dependency():
    with tempfile.TemporaryDirectory() as tmpdir:
        fetcher = Fetcher(deps_dir=tmpdir)
        dep_dir = os.path.join(tmpdir, "newdep")
        # dep_dir does not yet exist → clone path
        with patch("fobis.Fetcher.syswork", return_value=(0, "")) as mock_sw:
            result, _commit = fetcher.fetch("newdep", "https://github.com/user/newdep")
        assert result == dep_dir
        assert any("clone" in call[0][0] for call in mock_sw.call_args_list)


def test_fetch_clone_failure_returns_dep_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        fetcher = Fetcher(deps_dir=tmpdir)
        with patch("fobis.Fetcher.syswork", return_value=(1, "error: not found")):
            result, _commit = fetcher.fetch("baddep", "https://github.com/user/baddep")
        assert result == os.path.join(tmpdir, "baddep")


def test_fetch_existing_dep_no_update():
    with tempfile.TemporaryDirectory() as tmpdir:
        dep_dir = os.path.join(tmpdir, "existingdep")
        os.makedirs(dep_dir)
        fetcher = Fetcher(deps_dir=tmpdir)
        # rev-parse HEAD is called even when already cloned
        with patch("fobis.Fetcher.syswork", return_value=(0, "")):
            result, _commit = fetcher.fetch("existingdep", "https://github.com/user/existingdep")
        assert result == dep_dir


def test_fetch_existing_dep_with_update():
    with tempfile.TemporaryDirectory() as tmpdir:
        dep_dir = os.path.join(tmpdir, "dep")
        os.makedirs(dep_dir)
        fetcher = Fetcher(deps_dir=tmpdir)
        with patch("fobis.Fetcher.syswork", return_value=(0, "")) as mock_sw:
            fetcher.fetch("dep", "https://github.com/user/dep", update=True)
        # Should call git fetch and then git merge
        calls = [c[0][0] for c in mock_sw.call_args_list]
        assert any("fetch" in c for c in calls)
        assert any("merge" in c for c in calls)


def test_fetch_with_tag_checks_out_ref():
    with tempfile.TemporaryDirectory() as tmpdir:
        dep_dir = os.path.join(tmpdir, "dep")
        os.makedirs(dep_dir)
        fetcher = Fetcher(deps_dir=tmpdir)
        with patch("fobis.Fetcher.syswork", return_value=(0, "")) as mock_sw:
            fetcher.fetch("dep", "https://github.com/user/dep", tag="v1.0.0")
        calls = [c[0][0] for c in mock_sw.call_args_list]
        assert any("checkout" in c and "v1.0.0" in c for c in calls)


def test_fetch_checkout_failure_logged():
    with tempfile.TemporaryDirectory() as tmpdir:
        dep_dir = os.path.join(tmpdir, "dep")
        os.makedirs(dep_dir)
        warnings = []
        fetcher = Fetcher(deps_dir=tmpdir, print_w=warnings.append)
        with patch("fobis.Fetcher.syswork", return_value=(1, "error: ref not found")):
            fetcher.fetch("dep", "https://github.com/user/dep", branch="nonexistent")
        assert any("error" in w.lower() or "Error" in w for w in warnings)


# ── build_dep() ───────────────────────────────────────────────────────────────


def test_build_dep_warns_when_no_fobos():
    with tempfile.TemporaryDirectory() as tmpdir:
        warnings = []
        fetcher = Fetcher(deps_dir="/fake", print_w=warnings.append)
        fetcher.build_dep("testdep", tmpdir)  # no fobos in tmpdir
        assert any("no fobos" in w for w in warnings)


def test_build_dep_success():
    with tempfile.TemporaryDirectory() as tmpdir:
        (open(os.path.join(tmpdir, "fobos"), "w")).close()
        messages = []
        fetcher = Fetcher(deps_dir="/fake", print_n=messages.append)
        with patch("fobis.Fetcher.syswork", return_value=(0, "build ok")):
            fetcher.build_dep("testdep", tmpdir)
        assert any("build ok" in m for m in messages)


def test_build_dep_with_mode():
    with tempfile.TemporaryDirectory() as tmpdir:
        (open(os.path.join(tmpdir, "fobos"), "w")).close()
        fetcher = Fetcher(deps_dir="/fake")
        with patch("fobis.Fetcher.syswork", return_value=(0, "")) as mock_sw:
            fetcher.build_dep("testdep", tmpdir, mode="gnu")
        cmd = mock_sw.call_args[0][0]
        assert "-mode" in cmd and "gnu" in cmd


def test_build_dep_build_failure_logged():
    with tempfile.TemporaryDirectory() as tmpdir:
        (open(os.path.join(tmpdir, "fobos"), "w")).close()
        warnings = []
        fetcher = Fetcher(deps_dir="/fake", print_w=warnings.append)
        with patch("fobis.Fetcher.syswork", return_value=(1, "compile error")):
            fetcher.build_dep("testdep", tmpdir)
        assert any("Error" in w or "error" in w for w in warnings)


# ── _build_dep_tracked() ─────────────────────────────────────────────────────


def test_build_dep_tracked_warns_when_no_fobos():
    with tempfile.TemporaryDirectory() as tmpdir:
        warnings = []
        fetcher = Fetcher(deps_dir="/fake", print_w=warnings.append)
        fetcher._build_dep_tracked("testdep", tmpdir)
        assert any("no fobos" in w for w in warnings)


def test_build_dep_tracked_success():
    with tempfile.TemporaryDirectory() as tmpdir:
        (open(os.path.join(tmpdir, "fobos"), "w")).close()
        messages = []
        fetcher = Fetcher(deps_dir="/fake", print_n=messages.append)
        with patch("fobis.Fetcher.syswork", return_value=(0, "tracked ok")):
            fetcher._build_dep_tracked("testdep", tmpdir)
        assert any("tracked ok" in m for m in messages)


def test_build_dep_tracked_with_mode():
    with tempfile.TemporaryDirectory() as tmpdir:
        (open(os.path.join(tmpdir, "fobos"), "w")).close()
        fetcher = Fetcher(deps_dir="/fake")
        with patch("fobis.Fetcher.syswork", return_value=(0, "")) as mock_sw:
            fetcher._build_dep_tracked("testdep", tmpdir, mode="release")
        cmd = mock_sw.call_args[0][0]
        assert "track_build" in cmd and "-mode" in cmd and "release" in cmd


# ── install_from_github() ─────────────────────────────────────────────────────


def test_install_from_github_no_build():
    with tempfile.TemporaryDirectory() as tmpdir:
        dep_dir = os.path.join(tmpdir, "myrepo")
        os.makedirs(dep_dir)
        messages = []
        fetcher = Fetcher(deps_dir=tmpdir, print_n=messages.append)
        with patch("fobis.Fetcher.syswork", return_value=(0, "")):
            fetcher.install_from_github("user/myrepo", no_build=True)
        assert any("no-build" in m or "skipping" in m for m in messages)


# ── _install_artifacts() ─────────────────────────────────────────────────────


def test_install_artifacts_no_track_files_warns():
    with tempfile.TemporaryDirectory() as dep_dir, tempfile.TemporaryDirectory() as prefix:
        warnings = []
        fetcher = Fetcher(deps_dir="/fake", print_w=warnings.append)
        fetcher._install_artifacts(dep_dir, prefix, "bin/", "lib/", "include/")
        assert any("No installable" in w for w in warnings)


def test_install_artifacts_installs_program(tmp_path):
    dep_dir = tmp_path / "dep"
    dep_dir.mkdir()
    prefix = tmp_path / "prefix"
    prefix.mkdir()

    # Create a fake executable that "exists"
    exe = dep_dir / "myapp"
    exe.write_text("fake binary")

    # Write a .track_build file
    track = configparser.ConfigParser()
    track["build"] = {"output": str(exe), "program": "True"}
    with open(dep_dir / "myapp.track_build", "w") as f:
        track.write(f)

    fetcher = Fetcher(deps_dir="/fake")
    fetcher._install_artifacts(str(dep_dir), str(prefix), "bin/", "lib/", "include/")

    installed = list((prefix / "bin").iterdir())
    assert len(installed) == 1
    assert installed[0].name == "myapp"


def test_install_artifacts_installs_library_with_mod(tmp_path):
    dep_dir = tmp_path / "dep"
    dep_dir.mkdir()
    prefix = tmp_path / "prefix"
    prefix.mkdir()

    lib = dep_dir / "libmylib.a"
    lib.write_text("fake lib")
    mod = dep_dir / "mymod.mod"
    mod.write_text("fake mod")

    track = configparser.ConfigParser()
    track["build"] = {"output": str(lib), "library": "True", "mod_file": str(mod)}
    with open(dep_dir / "mylib.track_build", "w") as f:
        track.write(f)

    fetcher = Fetcher(deps_dir="/fake")
    fetcher._install_artifacts(str(dep_dir), str(prefix), "bin/", "lib/", "include/")

    assert (prefix / "lib" / "libmylib.a").exists()
    assert (prefix / "include" / "mymod.mod").exists()


def test_install_artifacts_skips_missing_output(tmp_path):
    dep_dir = tmp_path / "dep"
    dep_dir.mkdir()
    prefix = tmp_path / "prefix"
    prefix.mkdir()

    track = configparser.ConfigParser()
    track["build"] = {"output": "/nonexistent/path", "program": "True"}
    with open(dep_dir / "ghost.track_build", "w") as f:
        track.write(f)

    warnings = []
    fetcher = Fetcher(deps_dir="/fake", print_w=warnings.append)
    fetcher._install_artifacts(str(dep_dir), str(prefix), "bin/", "lib/", "include/")
    # No artifacts installed → warning emitted
    assert any("No installable" in w for w in warnings)


def test_install_artifacts_skips_track_without_output_key(tmp_path):
    dep_dir = tmp_path / "dep"
    dep_dir.mkdir()
    prefix = tmp_path / "prefix"
    prefix.mkdir()

    track = configparser.ConfigParser()
    track["build"] = {"something_else": "value"}
    with open(dep_dir / "noout.track_build", "w") as f:
        track.write(f)

    warnings = []
    fetcher = Fetcher(deps_dir="/fake", print_w=warnings.append)
    fetcher._install_artifacts(str(dep_dir), str(prefix), "bin/", "lib/", "include/")
    assert any("No installable" in w for w in warnings)


# ── lock file: save_lock / load_lock / verify_lock ───────────────────────────


def test_fetch_writes_lock():
    """fetch() should commit+sha256 end up in fobos.lock."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fetcher = Fetcher(deps_dir=tmpdir)
        # Simulate a successful clone that returns a commit sha
        with patch("fobis.Fetcher.syswork") as mock_sw:
            # git clone → success; rev-parse HEAD → commit sha
            def sw_side(cmd):
                if "rev-parse" in cmd:
                    return (0, "abc123deadbeef\n")
                if "archive" in cmd:
                    return (0, "")
                return (0, "")
            mock_sw.side_effect = sw_side
            _dep_dir, commit = fetcher.fetch("mylib", "https://github.com/user/mylib")

        # Save a lock with the returned commit
        fetcher.save_lock([{"name": "mylib", "url": "https://github.com/user/mylib",
                            "commit": commit, "sha256": "fake_sha256"}])
        lock = fetcher.load_lock()
        assert "mylib" in lock
        assert lock["mylib"]["commit"] == commit


def test_fetch_load_lock_missing_returns_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        fetcher = Fetcher(deps_dir=tmpdir)
        assert fetcher.load_lock() == {}


def test_fetch_verify_lock_pass():
    """Lock commit matches HEAD → no warning."""
    with tempfile.TemporaryDirectory() as tmpdir:
        dep_dir = os.path.join(tmpdir, "dep")
        os.makedirs(dep_dir)
        fetcher = Fetcher(deps_dir=tmpdir)
        lock = {"dep": {"commit": "abc123", "url": "https://github.com/user/dep"}}
        with patch("fobis.Fetcher.syswork", return_value=(0, "abc123\n")):
            warnings = []
            fetcher.print_w = warnings.append
            result = fetcher.verify_lock("dep", dep_dir, lock)
        assert result is True
        assert warnings == []


def test_fetch_verify_lock_mismatch():
    """Lock commit ≠ HEAD → warning emitted, returns False."""
    with tempfile.TemporaryDirectory() as tmpdir:
        dep_dir = os.path.join(tmpdir, "dep")
        os.makedirs(dep_dir)
        fetcher = Fetcher(deps_dir=tmpdir)
        lock = {"dep": {"commit": "abc123", "url": "https://github.com/user/dep"}}
        with patch("fobis.Fetcher.syswork", return_value=(0, "deadbeef\n")):
            warnings = []
            fetcher.print_w = warnings.append
            result = fetcher.verify_lock("dep", dep_dir, lock)
        assert result is False
        assert any("abc123" in w or "deadbeef" in w or "does not match" in w for w in warnings)


def test_fetch_verify_lock_name_not_in_lock():
    """Dependency not in lockfile → True (no check)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fetcher = Fetcher(deps_dir=tmpdir)
        lock = {}
        result = fetcher.verify_lock("unknown", "/fake/dep", lock)
        assert result is True


# ── semver spec parsing ───────────────────────────────────────────────────────


def test_fetch_semver_conflicts_with_tag_errors():
    """Spec with both semver= and tag= must raise ValueError at parse time."""
    fetcher = Fetcher(deps_dir="/fake")
    with pytest.raises(ValueError):
        fetcher.parse_dep_spec("https://github.com/user/repo :: tag=v1.2 :: semver=^1")


def test_fetch_semver_conflicts_with_branch_errors():
    """Spec with both semver= and branch= must raise ValueError at parse time."""
    fetcher = Fetcher(deps_dir="/fake")
    with pytest.raises(ValueError):
        fetcher.parse_dep_spec("https://github.com/user/repo :: branch=main :: semver=^1")


def test_parse_dep_spec_semver_only():
    """Spec with semver= and no other pin → parsed correctly."""
    fetcher = Fetcher(deps_dir="/fake")
    result = fetcher.parse_dep_spec("https://github.com/user/repo :: semver=^1.5")
    assert result["semver"] == "^1.5"
    assert "tag" not in result
    assert "branch" not in result


# ── integration tests ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("n", range(1, 5))
def test_fetch_dep_integration(monkeypatch, n):
    """Test fetch dependency integration scenario n."""
    assert run_build(monkeypatch, f"fetch-dep-test{n}"), f"fetch-dep-test{n} failed"
