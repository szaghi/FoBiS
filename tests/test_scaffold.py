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
        assert entry["category"] in ("verbatim", "templated", "init-only", "symlink", "patched")


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


def test_sync_yes_false_confirm_exception_writes_nothing(tmp_path):
    """When typer.confirm raises (no TTY, stdin at EOF), nothing is written: no consent, no write."""
    s, messages = _make_scaffolder(tmp_path)
    with patch("typer.confirm", side_effect=Exception("no tty")):
        s.sync(yes=False)
    assert not any("Written" in m for m in messages)
    assert any("no answer possible" in m for m in messages)
    assert not [f for f in tmp_path.rglob("*") if f.is_file()]


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
    """With missing vars and yes=False, typer.prompt is called; exception → empty."""
    sparse_vars = {k: "" for k in _FULL_VARS}
    sparse_vars["YEAR"] = "2026"
    s, messages = _make_scaffolder(tmp_path, vars_dict=sparse_vars)
    with patch("typer.prompt", side_effect=Exception("no tty")) as prompt:
        s.init(yes=False)
    assert prompt.called
    # Should still complete without crashing
    assert any("created" in m for m in messages)


def test_init_yes_never_prompts(tmp_path):
    """--yes means no interactive prompt at all: missing vars stay empty (it used to block on stdin)."""
    sparse_vars = {k: "" for k in _FULL_VARS}
    sparse_vars["YEAR"] = "2026"
    s, messages = _make_scaffolder(tmp_path, vars_dict=sparse_vars)
    with patch("typer.prompt", side_effect=AssertionError("prompted under --yes")) as prompt:
        s.init(yes=True)
    assert not prompt.called
    assert any("created" in m for m in messages)


_TEMPLATED_PROJECT_OWNED = ("fpm.toml", "docs/ford.md", "docs/.vitepress/config.mts", "fobos")


@pytest.mark.parametrize("dest", _TEMPLATED_PROJECT_OWNED)
def test_init_renders_templated_project_owned_files(tmp_path, dest):
    """GH #205: init-only/patched entries with a templated/ source are rendered, not copied raw."""
    s, _ = _make_scaffolder(tmp_path)
    assert s.manifest[dest]["category"] in ("init-only", "patched")
    assert s.manifest[dest]["source"].startswith("templated/")
    s.init(yes=True)
    text = (tmp_path / dest).read_text(encoding="utf-8")
    assert s._unrendered(text) == []
    assert "MyProject" in text


def test_status_after_init_reports_no_unrendered(tmp_path):
    s, messages = _make_scaffolder(tmp_path)
    s.init(yes=True)
    assert not any(state == "unrendered" for _, state in s.drift())
    messages.clear()
    s.status()
    assert not any("UNRENDERED" in m for m in messages)


@pytest.mark.parametrize("dest", ["fpm.toml", "docs/.vitepress/config.mts"])
def test_status_flags_unrendered_project_owned_file(tmp_path, dest):
    """A project-owned file still holding {{VAR}} placeholders is drift, not OK."""
    s, messages = _make_scaffolder(tmp_path)
    abs_path = tmp_path / dest
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(s._read_template(s.manifest[dest]["source"]), encoding="utf-8")  # raw, as GH #205 wrote it
    assert (dest, "unrendered") in s.drift(files_glob=dest)
    messages.clear()
    s.status(files_glob=dest)
    assert any("UNRENDERED" in m and "{{NAME}}" in m for m in messages)
    with pytest.raises(SystemExit):
        s.status(files_glob=dest, strict=True)


def test_unrendered_ignores_github_and_template_engine_expressions(tmp_path):
    """Only project-variable tokens count: ${{ github.x }} or {{ group }} are not placeholders."""
    s, _ = _make_scaffolder(tmp_path)
    assert s._unrendered("${{ github.ref_name }} {{ group }} {{VAR}}") == []
    assert s._unrendered("name = {{NAME}}, year {{YEAR}}") == ["{{NAME}}", "{{YEAR}}"]


# ── Scaffolder.list_files() ───────────────────────────────────────────────────


def test_list_files_covers_all_categories(tmp_path):
    s, messages = _make_scaffolder(tmp_path)
    s.list_files()
    text = "\n".join(messages)
    assert "Verbatim" in text
    assert "Templated" in text


# ── Packaging: every manifest entry must ship with the package ───────────────


def test_every_manifest_source_is_packaged():
    """Each `source = X` in manifest.ini must resolve to a real file on disk
    relative to the installed `fobis` package.

    Regression test for a packaging bug: setuptools' ``scaffolds/**/*``
    glob in ``[tool.setuptools.package-data]`` does NOT descend into
    dot-directories (``.github/``, ``.vitepress/``).  Without explicit
    dot-directory patterns, the wheel ships without those files and
    ``fobis scaffold status`` aborts with FileNotFoundError on the very
    first .github workflow entry.

    This test checks the *currently installed* package's scaffolds tree,
    so it passes trivially in editable installs (the source tree is
    visible directly) but catches the bug when run against a wheel-
    installed package.
    """
    import configparser
    from pathlib import Path

    import fobis

    scaffolds_root = Path(fobis.__file__).parent / "scaffolds"
    manifest_path = scaffolds_root / "manifest.ini"
    assert manifest_path.is_file(), f"manifest.ini missing at {manifest_path}"

    parser = configparser.RawConfigParser()
    parser.optionxform = str
    parser.read(manifest_path)

    missing: list[str] = []
    for section in parser.sections():
        if not parser.has_option(section, "source"):
            continue
        source_rel = parser.get(section, "source").strip()
        candidate = scaffolds_root / source_rel
        if not candidate.is_file():
            missing.append(source_rel)

    assert not missing, (
        "Manifest references files that are not on disk in the installed "
        "package.  In wheel installs this means setuptools' package-data "
        "glob is missing patterns for the dot-directories in those paths.  "
        f"Missing: {missing}"
    )


def test_verbatim_json_templates_are_strict_json():
    """Every *.json under scaffolds/verbatim/ must parse as strict JSON.

    Verbatim scaffolds are copied byte-for-byte to user projects and then
    consumed by tools that enforce strict JSON (npm, jq, etc.). A trailing
    comma — accepted by editors and JS — silently ships an unusable file.
    Walk the verbatim tree and json.load() each candidate.
    """
    import json
    from pathlib import Path

    import fobis

    verbatim_root = Path(fobis.__file__).parent / "scaffolds" / "verbatim"
    assert verbatim_root.is_dir(), f"verbatim/ missing at {verbatim_root}"

    invalid: list[tuple[str, str]] = []
    for path in sorted(verbatim_root.rglob("*.json")):
        try:
            with path.open() as fh:
                json.load(fh)
        except json.JSONDecodeError as e:
            invalid.append((str(path.relative_to(verbatim_root)), str(e)))

    assert not invalid, (
        "Verbatim JSON templates fail strict parse — they will break "
        "downstream tools (npm ci, jq, etc.) in scaffolded projects:\n"
        + "\n".join(f"  {p}: {err}" for p, err in invalid)
    )


# ── Scaffolder symlink category ───────────────────────────────────────────────


def _inject_symlink_entry(s, dest="CONTRIBUTING.md", target="docs/guide/contributing.md"):
    """Add a synthetic symlink manifest entry so symlink behaviour is testable in isolation."""
    s.manifest[dest] = {
        "source": None,
        "category": "symlink",
        "executable": False,
        "target": target,
    }
    return dest, target


def test_symlink_ensure_creates_link_when_missing(tmp_path):
    s, _ = _make_scaffolder(tmp_path)
    dest, target = _inject_symlink_entry(s)
    abs_dest = tmp_path / dest
    changed = s._ensure_symlink(str(abs_dest), target)
    assert changed is True
    assert abs_dest.is_symlink()
    import os

    assert os.readlink(str(abs_dest)) == target


def test_symlink_ensure_replaces_regular_file(tmp_path):
    s, _ = _make_scaffolder(tmp_path)
    dest, target = _inject_symlink_entry(s)
    abs_dest = tmp_path / dest
    abs_dest.write_text("a stale regular CONTRIBUTING file", encoding="utf-8")
    assert abs_dest.is_file() and not abs_dest.is_symlink()

    changed = s._ensure_symlink(str(abs_dest), target)
    assert changed is True
    assert abs_dest.is_symlink()


def test_symlink_ensure_skips_correct_link(tmp_path):
    import os

    s, _ = _make_scaffolder(tmp_path)
    dest, target = _inject_symlink_entry(s)
    abs_dest = tmp_path / dest
    os.symlink(target, str(abs_dest))
    # Already correct → no change
    assert s._ensure_symlink(str(abs_dest), target) is False


def test_status_reports_symlink_drift_for_regular_file(tmp_path):
    s, messages = _make_scaffolder(tmp_path)
    dest, _target = _inject_symlink_entry(s)
    (tmp_path / dest).write_text("regular file, not a link", encoding="utf-8")
    messages.clear()
    s.status(files_glob=dest)
    assert any("SYMLINK" in m for m in messages)


def test_status_reports_ok_for_correct_symlink(tmp_path):
    import os

    s, messages = _make_scaffolder(tmp_path)
    dest, target = _inject_symlink_entry(s)
    os.symlink(target, str(tmp_path / dest))
    messages.clear()
    s.status(files_glob=dest)
    assert any("OK" in m and "SYMLINK" not in m for m in messages)
    assert not any("SYMLINK" in m for m in messages)


def test_sync_creates_symlink_and_never_writes_through(tmp_path):
    """sync replaces a regular file with a link; it must NOT overwrite the link target."""
    s, messages = _make_scaffolder(tmp_path)
    dest, target = _inject_symlink_entry(s)
    # Create the canonical target with known content
    abs_target = tmp_path / target
    abs_target.parent.mkdir(parents=True, exist_ok=True)
    abs_target.write_text("CANONICAL CONTRIBUTING CONTENT", encoding="utf-8")
    # And a stale regular file at the root dest
    (tmp_path / dest).write_text("stale root file", encoding="utf-8")

    s.sync(yes=True, files_glob=dest)
    assert (tmp_path / dest).is_symlink()
    # The target must be untouched — proves we did not write through the link
    assert abs_target.read_text(encoding="utf-8") == "CANONICAL CONTRIBUTING CONTENT"
    assert any("Linked" in m for m in messages)


def test_sync_dry_run_does_not_create_symlink(tmp_path):
    s, _ = _make_scaffolder(tmp_path)
    dest, _target = _inject_symlink_entry(s)
    s.sync(dry_run=True, yes=True, files_glob=dest)
    assert not (tmp_path / dest).exists()


# ── Scaffolder [scaffold] apt_packages parametrization ─────────────────────────


class _FakeFobos:
    """Minimal fobos stub exposing the two getters get_project_vars consumes."""

    def __init__(self, apt_packages=""):
        self._apt = apt_packages

    def get_scaffold_config(self):
        return {"apt_packages": self._apt}

    def get_project_info(self):
        return {
            "name": "Demo",
            "authors": [],
            "version": "",
            "summary": "",
            "repository": "",
            "website": "",
            "email": "",
            "year": "",
        }

    def get_dependencies(self):
        return {}


def test_apt_packages_empty_renders_setup_build_env_unchanged(tmp_path):
    """No [scaffold] apt_packages → setup-build-env renders byte-identical to its template-with-empty-var."""
    vars_no_apt = get_project_vars(fobos=_FakeFobos(apt_packages=""))
    assert vars_no_apt["SCAFFOLD_APT_PACKAGES"] == ""
    s = Scaffolder(project_vars=vars_no_apt, cwd=str(tmp_path))
    entry = s.manifest[".github/actions/setup-build-env/action.yml"]
    assert entry["category"] == "templated"
    rendered = s._get_canonical(entry)
    # The placeholder vanished: no dangling braces, last apt target is the g++ line.
    assert "{{SCAFFOLD_APT_PACKAGES}}" not in rendered
    assert "g++-${{ inputs.gcc-version }}\n" in rendered


def test_apt_packages_set_appends_continuation_lines(tmp_path):
    """[scaffold] apt_packages → each package appended as a '\\'-continued apt line."""
    vars_apt = get_project_vars(fobos=_FakeFobos(apt_packages="libopenmpi-dev openmpi-bin"))
    assert vars_apt["SCAFFOLD_APT_PACKAGES"] == " \\\n          libopenmpi-dev \\\n          openmpi-bin"
    s = Scaffolder(project_vars=vars_apt, cwd=str(tmp_path))
    entry = s.manifest[".github/actions/setup-build-env/action.yml"]
    rendered = s._get_canonical(entry)
    assert "libopenmpi-dev" in rendered
    assert "openmpi-bin" in rendered
    # Still inside the single apt-install block (before update-alternatives).
    apt_block = rendered.split("update-alternatives")[0]
    assert "libopenmpi-dev" in apt_block and "openmpi-bin" in apt_block


# ── Scaffold run_tests.sh --np (MPI) support ──────────────────────────────────


def test_run_tests_sh_auto_dispatches_mpi_binaries(tmp_path):
    """run_tests.sh runs *mpi* binaries under mpirun, others serially; non-MPI
    projects never invoke mpirun and --np overrides the rank count."""
    import os
    import shutil
    import stat
    import subprocess
    from pathlib import Path

    import fobis

    src = Path(fobis.__file__).parent / "scaffolds" / "verbatim" / "scripts" / "run_tests.sh"
    script = tmp_path / "run_tests.sh"
    shutil.copy(src, script)

    exe_dir = tmp_path / "exe"
    exe_dir.mkdir()
    for nm in ("foo_test", "baz_mpi_test"):
        p = exe_dir / nm
        p.write_text("#!/bin/bash\nexit 0\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    xf = exe_dir / "bar_xfail_test"
    xf.write_text("#!/bin/bash\nexit 1\n")
    xf.chmod(xf.stat().st_mode | stat.S_IEXEC)

    # Fake mpirun records every invocation to a proof file, then execs the target.
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    proof = tmp_path / "mpirun_calls"
    mpirun = fakebin / "mpirun"
    mpirun.write_text(f'#!/bin/bash\necho "$@" >> {proof}\nshift 2\nexec "$@"\n')
    mpirun.chmod(mpirun.stat().st_mode | stat.S_IEXEC)
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}")

    # Default: only the *mpi* binary is wrapped, at -np 2; serial + xfail still classified.
    r = subprocess.run(["bash", str(script)], cwd=tmp_path, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout and "XFAIL" in r.stdout
    calls = proof.read_text()
    assert "exe/baz_mpi_test" in calls and "-np 2" in calls
    assert "foo_test" not in calls  # non-mpi binary ran serially

    # --np overrides the rank count for mpi binaries.
    proof.unlink()
    subprocess.run(["bash", str(script), "--np", "4"], cwd=tmp_path, capture_output=True, text=True, env=env)
    assert "-np 4" in proof.read_text()

    # A project with no *mpi* binaries never invokes mpirun.
    (exe_dir / "baz_mpi_test").unlink()
    proof.unlink()
    subprocess.run(["bash", str(script)], cwd=tmp_path, capture_output=True, text=True, env=env)
    assert not proof.exists()


def test_run_tests_sh_checks_expected_results(tmp_path):
    """run_tests.sh compares the output of a test with its <name>.result, if the project has one:
    a doctest printing F (exit 0) fails; a test without result is judged by its exit status only."""
    import shutil
    import stat
    import subprocess
    from pathlib import Path

    import fobis

    src = Path(fobis.__file__).parent / "scaffolds" / "verbatim" / "scripts" / "run_tests.sh"
    script = tmp_path / "run_tests.sh"
    shutil.copy(src, script)

    exe_dir = tmp_path / "exe"
    exe_dir.mkdir()
    for nm, body in (
        ("m-doctest-1", "echo ' T'"),  # matches its result, surrounding white space ignored
        ("m-doctest-11", "echo F"),  # differs from its result: the name of m-doctest-1 must not match it
        ("plain_test", "echo F"),  # no result: exit status only
    ):
        p = exe_dir / nm
        p.write_text(f"#!/bin/bash\n{body}\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    results = tmp_path / "src" / "tests" / "m"
    results.mkdir(parents=True)
    (results / "m-doctest-1.result").write_text("T")
    (results / "m-doctest-11.result").write_text("T")
    (exe_dir / "plain_test.result").write_text("T")  # inside the build directory: ignored

    r = subprocess.run(["bash", str(script)], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 1, r.stdout + r.stderr
    lines = r.stdout.splitlines()
    assert any("PASS" in line and "m-doctest-1" in line and "m-doctest-11" not in line for line in lines)
    assert any(
        "FAIL" in line and "m-doctest-11" in line and "src/tests/m/m-doctest-11.result" in line for line in lines
    )
    assert any("PASS" in line and "plain_test" in line for line in lines)
    assert "2/3 passed" in r.stdout


def test_run_tests_sh_caps_virtual_memory(tmp_path):
    """run_tests.sh --vmem KB runs every test under `ulimit -v KB`; a non-numeric cap is rejected."""
    import shutil
    import stat
    import subprocess
    from pathlib import Path

    import fobis

    src = Path(fobis.__file__).parent / "scaffolds" / "verbatim" / "scripts" / "run_tests.sh"
    script = tmp_path / "run_tests.sh"
    shutil.copy(src, script)

    exe_dir = tmp_path / "exe"
    exe_dir.mkdir()
    p = exe_dir / "limit_test"
    p.write_text('#!/bin/bash\n[[ "$(ulimit -v)" == 500000 ]]\n')
    p.chmod(p.stat().st_mode | stat.S_IEXEC)

    r = subprocess.run(["bash", str(script), "--vmem", "500000"], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    r = subprocess.run(["bash", str(script)], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 1  # no cap by default
    r = subprocess.run(["bash", str(script), "--vmem", "4G"], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 2
    assert "Invalid --vmem" in r.stderr


# ── Scaffolder `patched` category ─────────────────────────────────────────────

# Minimal VitePress-config shapes exercising each patch state. The title/nav
# lines stand in for arbitrary project-owned content that must survive untouched.
_CFG_CLEAN_VITE = """\
export default {
  title: 'MyProject',
  themeConfig: { nav: [{ text: 'Home', link: '/' }] },
  vite: {
    optimizeDeps: {
      include: ['mermaid'],
    },
  },
}
"""

_CFG_ALREADY_PATCHED = """\
export default {
  title: 'MyProject',
  vite: {
    build: {
      target: 'es2022',
    },
  },
}
"""

_CFG_USER_BUILD_BLOCK = """\
export default {
  title: 'MyProject',
  vite: {
    build: {
      chunkSizeWarningLimit: 900,
    },
  },
}
"""

_CFG_NO_VITE = """\
export default {
  title: 'MyProject',
  themeConfig: { nav: [] },
}
"""


def _patched_dest_and_scaffolder(tmp_path, content):
    s, messages = _make_scaffolder(tmp_path)
    dest = next(d for d, e in s.manifest.items() if e["category"] == "patched")
    abs_path = tmp_path / dest
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(content, encoding="utf-8")
    messages.clear()
    return s, messages, dest, abs_path


def test_manifest_has_patched_category(tmp_path):
    """config.mts is `patched`, not `init-only`, and names its fragment."""
    s, _ = _make_scaffolder(tmp_path)
    entry = s.manifest["docs/.vitepress/config.mts"]
    assert entry["category"] == "patched"
    assert entry["patches"] == ["vite-es2022-target"]
    assert "vite-es2022-target" in s.patches


def test_patched_probe_present_is_ok(tmp_path):
    """A file already carrying the fragment reports OK and sync leaves it byte-identical."""
    s, messages, dest, abs_path = _patched_dest_and_scaffolder(tmp_path, _CFG_ALREADY_PATCHED)
    before = abs_path.read_text(encoding="utf-8")

    s.status(files_glob=dest)
    assert any("OK" in m for m in messages)
    assert not any(("PATCH" in m or "MANUAL" in m) for m in messages)

    messages.clear()
    s.sync(yes=True, files_glob=dest)
    assert abs_path.read_text(encoding="utf-8") == before


def test_patched_inserts_into_clean_vite_block(tmp_path):
    """A clean `vite: {` with no `build:` gets the fragment; project content survives."""
    s, messages, dest, abs_path = _patched_dest_and_scaffolder(tmp_path, _CFG_CLEAN_VITE)

    s.status(files_glob=dest)
    assert any("PATCH" in m for m in messages)

    messages.clear()
    s.sync(yes=True, files_glob=dest)
    out = abs_path.read_text(encoding="utf-8")
    assert "target: 'es2022'" in out
    # project-owned lines untouched
    assert "title: 'MyProject'," in out
    assert "include: ['mermaid']," in out
    # fragment nested one level inside the 2-space `vite:` block → 4-space indent
    assert "    build: {\n      target: 'es2022',\n    },\n" in out
    # idempotent: a second sync is a no-op
    messages.clear()
    s.sync(yes=True, files_glob=dest)
    assert not any("Patched" in m for m in messages)


def test_patched_refuses_when_guard_present(tmp_path):
    """A user-owned `build: {` block blocks auto-insertion; file is left untouched."""
    s, messages, dest, abs_path = _patched_dest_and_scaffolder(tmp_path, _CFG_USER_BUILD_BLOCK)
    before = abs_path.read_text(encoding="utf-8")

    s.status(files_glob=dest)
    assert any("MANUAL" in m for m in messages)

    messages.clear()
    s.sync(yes=True, files_glob=dest)
    assert abs_path.read_text(encoding="utf-8") == before  # never written
    assert any("manual insertion" in m for m in messages)
    assert any("target: 'es2022'" in m for m in messages)  # fragment printed for the user


def test_patched_refuses_when_no_anchor(tmp_path):
    """No `vite: {` anchor at all → refuse to guess; file untouched, fragment printed."""
    s, messages, dest, abs_path = _patched_dest_and_scaffolder(tmp_path, _CFG_NO_VITE)
    before = abs_path.read_text(encoding="utf-8")

    s.status(files_glob=dest)
    assert any("MANUAL" in m for m in messages)

    messages.clear()
    s.sync(yes=True, files_glob=dest)
    assert abs_path.read_text(encoding="utf-8") == before
    assert any("manual insertion" in m for m in messages)


def test_patched_dry_run_does_not_write(tmp_path):
    """dry_run shows the diff but never writes the patched file."""
    s, messages, dest, abs_path = _patched_dest_and_scaffolder(tmp_path, _CFG_CLEAN_VITE)
    before = abs_path.read_text(encoding="utf-8")

    s.sync(dry_run=True, yes=True, files_glob=dest)
    assert abs_path.read_text(encoding="utf-8") == before
    assert any("target: 'es2022'" in m for m in messages)  # diff was shown


def test_patched_missing_file_is_not_created_by_sync(tmp_path):
    """sync does not create an absent patched file — that is init's job."""
    s, _messages = _make_scaffolder(tmp_path)
    dest = next(d for d, e in s.manifest.items() if e["category"] == "patched")
    s.sync(yes=True, files_glob=dest)
    assert not (tmp_path / dest).exists()


# ── Release notes: release.yml must find the heading cliff.toml writes ──────


def _scaffold_text(rel):
    from importlib import resources

    return (resources.files("fobis") / "scaffolds" / rel).read_text(encoding="utf-8")


def _cliff_heading(tag):
    """Render the version heading of the scaffolded cliff.toml for `tag`."""
    import re

    line = next(ln for ln in _scaffold_text("verbatim/cliff.toml").splitlines() if ln.startswith("## [{{ version"))
    version = tag
    if 'trim_start_matches(pat="v")' in line:
        version = tag[1:] if tag.startswith("v") else tag
    line = re.sub(r"\{\{ version[^}]*\}\}", version, line)
    return re.sub(r"\{\{ timestamp[^}]*\}\}", "2026-01-31", line)


@pytest.mark.parametrize("heading_tag", ["v1.2.3", None])
def test_release_workflow_extracts_cliff_changelog_section(tmp_path, heading_tag):
    """The notes script in release.yml must match the version heading that the
    scaffolded cliff.toml writes (GH #202: cliff.toml strips the tag's "v", the
    workflow searched for it, every release got the fallback text).  Headings
    that keep the "v" (heading_tag="v1.2.3") must match as well."""
    import subprocess
    import sys
    import textwrap

    workflow = _scaffold_text("templated/.github/workflows/release.yml")
    script = textwrap.dedent(workflow.split("<<'PYEOF'\n", 1)[1].split("PYEOF", 1)[0])
    heading = _cliff_heading("v1.2.3") if heading_tag is None else f"## [{heading_tag}] — 2026-01-31"
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        f"# Changelog\n\n{heading}\n\n### Bug fixes\n- Fix the reader\n\n## [1.2.2] — 2026-01-01\n\n### Bug fixes\n- Older fix\n",
        encoding="utf-8",
    )
    out = subprocess.run(
        [sys.executable, "-", "v1.2.3", str(changelog)], input=script, capture_output=True, text=True, check=True
    ).stdout
    assert out.startswith(heading)
    assert "- Fix the reader" in out
    assert "Older fix" not in out
    assert "See CHANGELOG.md for details" not in out


# ── Install smoke test: release.yml must run install.yml itself ─────────────


def _workflow(rel):
    yaml = pytest.importorskip("yaml")
    wf = yaml.safe_load(_scaffold_text(rel))
    # YAML 1.1 loads the bare key `on` as the boolean True
    wf["on"] = wf.pop(True, wf.get("on"))
    return wf


def test_release_workflow_runs_install_smoke_test():
    """A release published with GITHUB_TOKEN triggers no `release: published`
    workflow (GH #203): install.yml must be a reusable workflow called by
    release.yml after publishing, with the tag passed explicitly."""
    release = _workflow("templated/.github/workflows/release.yml")
    install = _workflow("verbatim/.github/workflows/install.yml")

    assert "release" not in install["on"]
    assert install["on"]["workflow_call"]["inputs"]["tag"]["required"] is True
    assert install["on"]["workflow_dispatch"]["inputs"]["tag"]["required"] is True
    # in a called workflow github.event is the caller's (tag push) event
    assert "github.event.release" not in _scaffold_text("verbatim/.github/workflows/install.yml")
    assert install["jobs"]["install"]["env"]["TAG"] == "${{ inputs.tag }}"

    caller = release["jobs"]["install"]
    assert caller["uses"] == "./.github/workflows/install.yml"
    assert caller["needs"] == "release"
    assert caller["with"]["tag"] == "${{ github.ref_name }}"
    # a called workflow can only narrow the caller's permissions
    assert caller["permissions"] == install["permissions"]


def test_release_workflow_publishes_only_from_tags():
    """workflow_dispatch from a branch must not publish a release named after it."""
    release = _workflow("templated/.github/workflows/release.yml")
    assert release["jobs"]["release"]["if"] == "startsWith(github.ref, 'refs/tags/v')"


def test_install_workflow_builds_fpm_from_the_release_tag():
    """The fpm step must test the released tag, not the default-branch head."""
    install = _workflow("verbatim/.github/workflows/install.yml")
    fpm = next(st for st in install["jobs"]["install"]["steps"] if st.get("name") == "FPM")
    assert '--branch "$TAG"' in fpm["run"]


def test_install_workflow_sets_up_build_env_before_any_build():
    """Every build step needs the CI compiler, apt_packages and FoBiS (GH #204):
    setup-build-env must run first, from the released tag, and each build step
    must be skipped when the project lacks that build system."""
    steps = _workflow("verbatim/.github/workflows/install.yml")["jobs"]["install"]["steps"]
    names = [st.get("name") for st in steps]
    checkout = steps[names.index("Checkout local actions")]
    assert checkout["with"]["ref"] == "${{ inputs.tag }}"
    setup = names.index("Setup build environment")
    assert steps[setup]["uses"] == "./.github/actions/setup-build-env"
    assert names.index("Checkout local actions") < setup
    builds = [
        i for i, st in enumerate(steps) if "run" in st and ("install.sh" in st["run"] or "fpm build" in st["run"])
    ]
    assert builds and min(builds) > setup
    for i in builds:
        assert "hashFiles(" in steps[i]["if"]
        assert "pipx" not in steps[i]["run"]


# ── install.sh: dependencies are fetched once the build is known to happen ───


def _install_sh_env(tmp_path, tools):
    """A PATH with only the system `tools` plus logging stubs in `stubs/`."""
    import os
    import shutil

    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in ("bash", "env", "grep", "sed", "tar", "rm", "cp", "gzip", "cat", *tools):
        path = shutil.which(tool)
        if path:
            (bindir / tool).symlink_to(path)
    log = tmp_path / "calls.log"
    return {**os.environ, "PATH": str(bindir), "STUB_LOG": str(log)}, bindir, log


def _stub(bindir, name, body='echo "$0 $*" >> "$STUB_LOG"'):
    stub = bindir / name
    stub.write_text(f"#!/bin/bash\n{body}\n", encoding="utf-8")
    stub.chmod(0o755)


def _install_sh_release(tmp_path, bindir, project_files):
    """Stub wget/curl/jq so `--download wget` extracts a tarball of `project_files`."""
    import tarfile

    src = tmp_path / "proj-1.0.0"
    src.mkdir()
    for name, text in project_files.items():
        (src / name).write_text(text, encoding="utf-8")
    tarball = tmp_path / "proj-1.0.0.tar.gz"
    with tarfile.open(tarball, "w:gz") as tar:
        tar.add(src, arcname=src.name)
    _stub(bindir, "curl", "echo '{}'")
    # read stdin as the real jq does: exiting first would SIGPIPE curl in `curl | jq` (pipefail -> exit 141)
    _stub(bindir, "jq", "cat > /dev/null\necho https://example.invalid/proj-1.0.0.tar.gz")
    _stub(bindir, "wget", f'cp "{tarball}" .')
    work = tmp_path / "work"
    work.mkdir()
    return work


_FOBOS_WITH_DEPS = "[modes]\nmodes = gnu\n\n[dependencies]\npenf = https://github.com/szaghi/PENF\n"


def _run_install_sh(work, env, *args):
    import subprocess

    script = work.parent / "install.sh"
    script.write_text(_scaffold_text("verbatim/scripts/install.sh"), encoding="utf-8")
    script.chmod(0o755)
    return subprocess.run(
        ["bash", str(script), "--repo", "owner/proj", "--tag", "v1.0.0", *args],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_install_sh_make_without_makefile_needs_no_fobis(tmp_path):
    """GH #204: a FoBiS-only project with [dependencies] and no Makefile must
    skip `--build make` cleanly instead of dying on the missing fobis."""
    env, bindir, log = _install_sh_env(tmp_path, ())
    _stub(bindir, "make")
    work = _install_sh_release(tmp_path, bindir, {"fobos": _FOBOS_WITH_DEPS})
    res = _run_install_sh(work, env, "--download", "wget", "--build", "make")
    assert res.returncode == 0, res.stderr
    assert "Makefile not found" in res.stdout
    assert not log.exists()


def test_install_sh_make_fetches_deps_then_builds(tmp_path):
    """A Makefile generated alongside the fobos builds from the fetched sources,
    which a release tarball does not contain: fetch them before `make`."""
    env, bindir, log = _install_sh_env(tmp_path, ())
    _stub(bindir, "fobis")
    _stub(bindir, "make")
    work = _install_sh_release(tmp_path, bindir, {"fobos": _FOBOS_WITH_DEPS, "Makefile": "all:\n"})
    res = _run_install_sh(work, env, "--download", "wget", "--build", "make")
    assert res.returncode == 0, res.stderr
    assert [line.split("/")[-1] for line in log.read_text().splitlines()] == ["fobis fetch", "make "]


def test_install_sh_make_with_deps_needs_fobis(tmp_path):
    """Without fobis the dependencies cannot be fetched: fail with a clear error,
    not with make's missing-source one."""
    env, bindir, log = _install_sh_env(tmp_path, ())
    _stub(bindir, "make")
    work = _install_sh_release(tmp_path, bindir, {"fobos": _FOBOS_WITH_DEPS, "Makefile": "all:\n"})
    res = _run_install_sh(work, env, "--download", "wget", "--build", "make")
    assert res.returncode != 0
    assert "fobis not found" in res.stderr
    assert not log.exists()


def test_install_sh_make_without_deps_needs_no_fobis(tmp_path):
    env, bindir, log = _install_sh_env(tmp_path, ())
    _stub(bindir, "make")
    work = _install_sh_release(tmp_path, bindir, {"fobos": "[modes]\nmodes = gnu\n", "Makefile": "all:\n"})
    res = _run_install_sh(work, env, "--download", "wget", "--build", "make")
    assert res.returncode == 0, res.stderr
    assert [line.split("/")[-1] for line in log.read_text().splitlines()] == ["make "]


def test_install_sh_cmake_fetches_deps_then_builds(tmp_path):
    env, bindir, log = _install_sh_env(tmp_path, ())
    _stub(bindir, "fobis")
    _stub(bindir, "cmake")
    work = _install_sh_release(tmp_path, bindir, {"fobos": _FOBOS_WITH_DEPS, "CMakeLists.txt": "project(p)\n"})
    res = _run_install_sh(work, env, "--download", "wget", "--build", "cmake")
    assert res.returncode == 0, res.stderr
    calls = [line.split("/")[-1] for line in log.read_text().splitlines()]
    assert calls == ["fobis fetch", "cmake -B build", "cmake --build build"]


def test_install_sh_fobis_fetches_deps_then_builds(tmp_path):
    env, bindir, log = _install_sh_env(tmp_path, ())
    _stub(bindir, "fobis")
    work = _install_sh_release(tmp_path, bindir, {"fobos": _FOBOS_WITH_DEPS})
    res = _run_install_sh(work, env, "--download", "wget", "--build", "fobis", "--mode", "gnu")
    assert res.returncode == 0, res.stderr
    calls = [line.split("/")[-1] for line in log.read_text().splitlines()]
    assert calls == ["fobis fetch", "fobis build --mode gnu"]
