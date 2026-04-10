"""Tests for Scaffolder.py — project boilerplate management."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fobis.Scaffolder import (
    Scaffolder,
    _fobos_deps_to_fpm,
    _git_submodule_deps_to_fpm,
    _parse_dep_spec,
    _resolve_dep_url,
    get_project_vars,
)

# ── Fixtures ───────────────────────────────────────────────────────────────────

_FULL_VARS = {
    "NAME": "MyProject",
    "SUMMARY": "A test Fortran project",
    "REPOSITORY": "https://github.com/user/myproject",
    "REPOSITORY_NAME": "myproject",
    "WEBSITE": "https://user.github.io",
    "AUTHORS": "Test Author",
    "EMAIL": "test@example.com",
    "YEAR": "2026",
    "DEPENDENCIES": "",
}


def _make_scaffolder(tmp_path, vars_dict=None):
    messages = []
    s = Scaffolder(
        project_vars=vars_dict or _FULL_VARS,
        cwd=str(tmp_path),
        print_n=messages.append,
        print_w=messages.append,
    )
    return s, messages


# ── Module-level helpers ───────────────────────────────────────────────────────


def test_parse_dep_spec_url_only():
    result = _parse_dep_spec("https://github.com/user/repo")
    assert result == {"url": "https://github.com/user/repo"}


def test_parse_dep_spec_with_tag():
    result = _parse_dep_spec("https://github.com/user/repo :: tag=v1.0.0")
    assert result["url"] == "https://github.com/user/repo"
    assert result["tag"] == "v1.0.0"


def test_parse_dep_spec_with_multiple_options():
    result = _parse_dep_spec("https://github.com/user/repo :: branch=main :: mode=gnu")
    assert result["branch"] == "main"
    assert result["mode"] == "gnu"


def test_resolve_dep_url_shorthand_adds_github_and_git():
    url = _resolve_dep_url("user/repo")
    assert url == "https://github.com/user/repo.git"


def test_resolve_dep_url_https_adds_git_suffix():
    url = _resolve_dep_url("https://github.com/user/repo")
    assert url.endswith(".git")


def test_resolve_dep_url_full_url_unchanged():
    url = _resolve_dep_url("https://github.com/user/repo.git")
    assert url == "https://github.com/user/repo.git"


def test_fobos_deps_to_fpm_empty():
    assert _fobos_deps_to_fpm({}) == ""


def test_fobos_deps_to_fpm_with_tag():
    deps = {"PENF": "szaghi/PENF :: tag=v1.5.0"}
    result = _fobos_deps_to_fpm(deps)
    assert "[dependencies]" in result
    assert "PENF" in result
    assert 'tag="v1.5.0"' in result


def test_fobos_deps_to_fpm_with_branch():
    deps = {"mylib": "https://github.com/user/mylib :: branch=develop"}
    result = _fobos_deps_to_fpm(deps)
    assert 'branch="develop"' in result


def test_fobos_deps_to_fpm_with_rev():
    deps = {"mylib": "https://github.com/user/mylib :: rev=abc123"}
    result = _fobos_deps_to_fpm(deps)
    assert 'rev="abc123"' in result


def test_fobos_deps_to_fpm_no_pin():
    deps = {"mylib": "https://github.com/user/mylib"}
    result = _fobos_deps_to_fpm(deps)
    assert "mylib" in result
    assert "tag" not in result and "branch" not in result and "rev" not in result


def test_git_submodule_deps_to_fpm_no_gitmodules(tmp_path):
    result = _git_submodule_deps_to_fpm(cwd=str(tmp_path))
    assert result == ""


def test_git_submodule_deps_to_fpm_empty_gitmodules(tmp_path):
    (tmp_path / ".gitmodules").write_text("")
    result = _git_submodule_deps_to_fpm(cwd=str(tmp_path))
    assert result == ""


def test_git_submodule_deps_to_fpm_with_submodule(tmp_path):
    (tmp_path / ".gitmodules").write_text(
        '[submodule "PENF"]\n    path = vendor/PENF\n    url = https://github.com/szaghi/PENF\n'
    )
    with patch("fobis.Scaffolder.syswork", return_value=(0, " abc1234 vendor/PENF (v1.0)\n")):
        result = _git_submodule_deps_to_fpm(cwd=str(tmp_path))
    assert "[dependencies]" in result
    assert "PENF" in result
    assert "github.com/szaghi/PENF.git" in result
    assert 'rev="abc1234"' in result


def test_git_submodule_deps_to_fpm_git_failure(tmp_path):
    """When git submodule status fails, URLs are still emitted without rev."""
    (tmp_path / ".gitmodules").write_text(
        '[submodule "mylib"]\n    path = vendor/mylib\n    url = https://github.com/user/mylib\n'
    )
    with patch("fobis.Scaffolder.syswork", return_value=(1, "")):
        result = _git_submodule_deps_to_fpm(cwd=str(tmp_path))
    assert "mylib" in result
    assert "rev=" not in result


# ── get_project_vars() ────────────────────────────────────────────────────────


def test_get_project_vars_all_from_git(tmp_path):
    def fake_syswork(cmd):
        if "remote get-url" in cmd:
            return (0, "https://github.com/user/myrepo\n")
        if "config user.name" in cmd:
            return (0, "Jane Doe\n")
        if "config user.email" in cmd:
            return (0, "jane@example.com\n")
        if "submodule status" in cmd:
            return (1, "")
        return (1, "")

    with patch("fobis.Scaffolder.syswork", side_effect=fake_syswork):
        vars_dict = get_project_vars(fobos=None)

    assert vars_dict["REPOSITORY"] == "https://github.com/user/myrepo"
    assert vars_dict["REPOSITORY_NAME"] == "myrepo"
    assert vars_dict["NAME"] == "myrepo"
    assert vars_dict["AUTHORS"] == "Jane Doe"
    assert vars_dict["EMAIL"] == "jane@example.com"


def test_get_project_vars_from_fobos(tmp_path):
    mock_fobos = MagicMock()
    mock_fobos.get_project_info.return_value = {
        "name": "AwesomeLib",
        "summary": "A great library",
        "repository": "https://github.com/user/awesomelib",
        "website": "https://user.github.io/awesomelib",
        "authors": ["Alice", "Bob"],
        "email": "alice@example.com",
        "year": "2025",
    }
    mock_fobos.get_dependencies.return_value = {}

    with patch("fobis.Scaffolder.syswork", return_value=(1, "")):
        vars_dict = get_project_vars(fobos=mock_fobos)

    assert vars_dict["NAME"] == "AwesomeLib"
    assert vars_dict["SUMMARY"] == "A great library"
    assert vars_dict["AUTHORS"] == "Alice, Bob"
    assert vars_dict["EMAIL"] == "alice@example.com"
    assert vars_dict["YEAR"] == "2025"
    assert vars_dict["REPOSITORY_NAME"] == "awesomelib"


def test_get_project_vars_overrides_take_priority():
    with patch("fobis.Scaffolder.syswork", return_value=(1, "")):
        vars_dict = get_project_vars(fobos=None, overrides={"NAME": "Overridden", "YEAR": "2099"})
    assert vars_dict["NAME"] == "Overridden"
    assert vars_dict["YEAR"] == "2099"


def test_get_project_vars_ssh_remote_normalised():
    """git@ SSH remote is converted to https://github.com/... URL."""
    with patch("fobis.Scaffolder.syswork", return_value=(0, "git@github.com:user/repo\n")):
        vars_dict = get_project_vars(fobos=None)
    assert vars_dict["REPOSITORY"].startswith("https://github.com/")
    assert ".git" not in vars_dict["REPOSITORY"]


# ── Scaffolder internal methods ───────────────────────────────────────────────


def test_scaffolder_loads_manifest(tmp_path):
    s, _ = _make_scaffolder(tmp_path)
    manifest = s.manifest
    assert len(manifest) > 0
    for _dest, entry in manifest.items():
        assert "source" in entry
        assert "category" in entry
        assert entry["category"] in ("verbatim", "templated", "init-only")


def test_scaffolder_render_substitutes_vars(tmp_path):
    s, _ = _make_scaffolder(tmp_path)
    template = "Hello {{NAME}}, repo: {{REPOSITORY}}"
    result = s._render(template)
    assert result == "Hello MyProject, repo: https://github.com/user/myproject"


def test_scaffolder_sha256_stable(tmp_path):
    s, _ = _make_scaffolder(tmp_path)
    h1 = s._sha256("hello")
    h2 = s._sha256("hello")
    assert h1 == h2
    assert s._sha256("hello") != s._sha256("world")


def test_scaffolder_filter_glob(tmp_path):
    s, _ = _make_scaffolder(tmp_path)
    assert s._filter("scripts/release.sh", "scripts/*") is True
    assert s._filter(".github/workflows/ci.yml", "scripts/*") is False
    assert s._filter("anything", None) is True


# ── Scaffolder.status() ───────────────────────────────────────────────────────


def test_status_reports_missing_files(tmp_path):
    s, messages = _make_scaffolder(tmp_path)
    s.status()
    assert any("MISSING" in m for m in messages)


def test_status_reports_ok_for_up_to_date_verbatim(tmp_path):
    s, messages = _make_scaffolder(tmp_path)
    # Pick a verbatim entry and write its canonical content
    verbatim_entry = next((dest, entry) for dest, entry in s.manifest.items() if entry["category"] == "verbatim")
    dest, _entry = verbatim_entry
    canonical = s._get_canonical(_entry)
    abs_path = tmp_path / dest
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(canonical, encoding="utf-8")

    messages.clear()
    s.status(files_glob=dest)
    assert any("OK" in m and "OUTDATED" not in m for m in messages)


def test_status_reports_outdated_for_modified_file(tmp_path):
    s, messages = _make_scaffolder(tmp_path)
    verbatim_entry = next((dest, entry) for dest, entry in s.manifest.items() if entry["category"] == "verbatim")
    dest, _entry = verbatim_entry
    abs_path = tmp_path / dest
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text("wrong content that differs from template", encoding="utf-8")

    messages.clear()
    s.status(files_glob=dest)
    assert any("OUTDATED" in m for m in messages)


def test_status_init_only_present_reports_ok(tmp_path):
    s, messages = _make_scaffolder(tmp_path)
    init_only_entry = next((dest, entry) for dest, entry in s.manifest.items() if entry["category"] == "init-only")
    dest, _entry = init_only_entry
    abs_path = tmp_path / dest
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text("anything — init-only files are never OUTDATED", encoding="utf-8")

    messages.clear()
    s.status(files_glob=dest)
    assert any("OK" in m for m in messages)
    assert not any("OUTDATED" in m for m in messages)


def test_status_strict_exits_when_drift(tmp_path):
    s, _ = _make_scaffolder(tmp_path)
    with pytest.raises(SystemExit):
        s.status(strict=True)


# ── Scaffolder.sync() ─────────────────────────────────────────────────────────


def test_sync_dry_run_does_not_write_files(tmp_path):
    s, _ = _make_scaffolder(tmp_path)
    s.sync(dry_run=True, yes=True)
    # No files should have been created under cwd
    created = [f for f in tmp_path.rglob("*") if f.is_file()]
    assert len(created) == 0


def test_sync_yes_writes_missing_files(tmp_path):
    s, messages = _make_scaffolder(tmp_path)
    s.sync(yes=True)
    assert any("Written" in m for m in messages)
    # At least some non-init-only files should now exist
    created = [f for f in tmp_path.rglob("*") if f.is_file()]
    assert len(created) > 0


def test_sync_skips_up_to_date_files(tmp_path):
    s, messages = _make_scaffolder(tmp_path)
    # First sync: creates everything
    s.sync(yes=True)
    messages.clear()
    # Second sync: nothing should change
    s.sync(yes=True)
    written_count_2 = sum(1 for m in messages if "Written" in m)
    assert written_count_2 == 0


def test_sync_skips_init_only_files(tmp_path):
    s, messages = _make_scaffolder(tmp_path)
    # Write wrong content to an init-only file
    init_only_dest = next(dest for dest, entry in s.manifest.items() if entry["category"] == "init-only")
    abs_path = tmp_path / init_only_dest
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text("custom content that sync must not touch", encoding="utf-8")

    messages.clear()
    s.sync(yes=True)
    # init-only file must be unchanged
    assert abs_path.read_text(encoding="utf-8") == "custom content that sync must not touch"


def test_sync_yes_false_confirm_exception_defaults_to_apply(tmp_path):
    """When typer.confirm raises (non-TTY), the exception handler applies changes."""
    s, messages = _make_scaffolder(tmp_path)
    with patch("typer.confirm", side_effect=Exception("no tty")):
        s.sync(yes=False)
    assert any("Written" in m for m in messages)


# ── Scaffolder.init() ─────────────────────────────────────────────────────────


def test_init_creates_missing_files(tmp_path):
    s, messages = _make_scaffolder(tmp_path)
    s.init(yes=True)
    assert any("created" in m for m in messages)
    created = [f for f in tmp_path.rglob("*") if f.is_file()]
    assert len(created) > 0


def test_init_skips_existing_files(tmp_path):
    s, messages = _make_scaffolder(tmp_path)
    # Run init twice: second run must not overwrite
    s.init(yes=True)
    first_contents = {
        str(f.relative_to(tmp_path)): f.read_text(encoding="utf-8") for f in tmp_path.rglob("*") if f.is_file()
    }
    messages.clear()
    s.init(yes=True)
    assert any("exists" in m for m in messages)
    for rel_path, content in first_contents.items():
        assert (tmp_path / rel_path).read_text(encoding="utf-8") == content


def test_init_creates_standard_directories(tmp_path):
    s, _ = _make_scaffolder(tmp_path)
    s.init(yes=True)
    for d in ("src", "docs", ".github/workflows"):
        assert (tmp_path / d).is_dir()


def test_init_prompts_for_missing_vars(tmp_path):
    """With missing vars and yes=True, typer.prompt is called; exception → empty."""
    sparse_vars = {k: "" for k in _FULL_VARS}
    sparse_vars["YEAR"] = "2026"
    s, messages = _make_scaffolder(tmp_path, vars_dict=sparse_vars)
    with patch("typer.prompt", side_effect=Exception("no tty")):
        s.init(yes=True)
    # Should still complete without crashing
    assert any("created" in m for m in messages)


# ── Scaffolder.list_files() ───────────────────────────────────────────────────


def test_list_files_covers_all_categories(tmp_path):
    s, messages = _make_scaffolder(tmp_path)
    s.list_files()
    text = "\n".join(messages)
    assert "Verbatim" in text
    assert "Templated" in text
