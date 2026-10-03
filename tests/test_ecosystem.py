"""Tests for Ecosystem — the ``fobis ecosystem`` command group (discover, dashboard, graph)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import pytest
from typer.testing import CliRunner

from fobis import Ecosystem as eco_mod
from fobis.cli import app
from fobis.Ecosystem import (
    Ecosystem,
    _ci_status,
    bump_version,
    discover,
    github_slug,
    is_releasable,
    mermaid,
    render_graph,
    render_html,
    render_table,
    suggest_bump,
)
from fobis.UserConfig import UserConfig

# ---------------------------------------------------------------------------
# Helpers: local git repositories, each a clone of a bare "origin"
# ---------------------------------------------------------------------------


@pytest.fixture
def git_env(tmp_path, monkeypatch):
    """Isolate git from the user's global configuration (signing, hooks, identity)."""
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("[user]\n\tname = Tester\n\temail = tester@example.com\n[commit]\n\tgpgsign = false\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    return tmp_path


def git(cwd, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def commit(repo, message: str, filename: str = "file.txt") -> str:
    path = repo / filename
    path.write_text(path.read_text() + message + "\n" if path.exists() else message + "\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def make_project(root, name: str, deps: dict[str, str] | None = None, push: bool = True, extra: str = ""):
    """Create ``root/name`` (fobos, VERSION v1.0.0, tag v1.0.0) cloned from ``root/remotes/name.git``."""
    bare = root / "remotes" / f"{name}.git"
    bare.mkdir(parents=True)
    git(bare, "init", "-q", "--bare", "-b", "master")
    repo = root / name
    repo.mkdir()
    git(repo, "init", "-q", "-b", "master")
    lines = ["[default]", "compiler = gnu", ""]
    if deps:
        lines += ["[dependencies]", "deps_dir = third_party"] + [f"{k} = {v}" for k, v in deps.items()]
    if extra:
        lines.append(extra)
    (repo / "fobos").write_text("\n".join(lines) + "\n")
    (repo / "VERSION").write_text("v1.0.0\n")
    (repo / ".gitignore").write_text("third_party/\n")
    commit(repo, "feat: initial")
    git(repo, "tag", "v1.0.0")
    git(repo, "remote", "add", "origin", str(bare))
    if push:
        git(repo, "push", "-q", "-u", "origin", "master", "--tags")
    return repo


def write_lock(repo, entries: dict[str, str]) -> None:
    lock = repo / "third_party" / "fobos.lock"
    lock.parent.mkdir(exist_ok=True)
    lock.write_text("".join(f"[{name}]\nurl = x\ncommit = {sha}\n\n" for name, sha in entries.items()))


def status_of(statuses, name):
    return next(s for s in statuses if s.name == name)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("messages", "expected"),
    [
        ([], None),
        (["fix: a"], "patch"),
        (["docs: a", "chore(ci): b"], "patch"),
        (["not conventional"], "patch"),
        (["fix: a", "feat(parser): b"], "minor"),
        (["feat!: drop API"], "major"),
        (["refactor(core)!: rename"], "major"),
        (["fix: a\n\nBREAKING CHANGE: removed x"], "major"),
    ],
)
def test_suggest_bump(messages, expected):
    assert suggest_bump(messages) == expected


@pytest.mark.parametrize(
    ("version", "bump", "expected"),
    [("v1.2.3", "patch", "v1.2.4"), ("1.2.3", "minor", "1.3.0"), ("v1.2.3", "major", "v2.0.0")],
)
def test_bump_version(version, bump, expected):
    assert bump_version(version, bump) == expected


@pytest.mark.parametrize(
    ("url", "slug"),
    [
        ("git@github.com:szaghi/PENF.git", "szaghi/PENF"),
        ("https://github.com/szaghi/FLAP", "szaghi/FLAP"),
        ("https://github.com/szaghi/FLAP.git/", "szaghi/FLAP"),
        ("https://gitlab.com/x/y", ""),
        ("/local/path/repo.git", ""),
    ],
)
def test_github_slug(url, slug):
    assert github_slug(url) == slug


# ---------------------------------------------------------------------------
# Projects and graph
# ---------------------------------------------------------------------------


def test_graph_levels_and_release_order(git_env):
    root = git_env
    make_project(root, "A")
    make_project(root, "B", {"A": "https://github.com/u/A"})
    make_project(root, "C", {"B": "https://github.com/u/B", "A": "https://github.com/u/A"})
    eco = Ecosystem([str(root / n) for n in ("C", "B", "A")])
    assert eco.projects["C"].deps == ["B", "A"]
    assert eco.levels() == ([["A"], ["B"], ["C"]], [])
    assert eco.release_order() == ["A", "B", "C"]
    assert eco.dependents("A") == ["C", "B"]


def test_graph_cycle_is_reported_not_looped(git_env):
    root = git_env
    make_project(root, "A", {"B": "u/B"})
    make_project(root, "B", {"A": "u/A"})
    make_project(root, "C")
    make_project(root, "D", {"A": "u/A"})
    eco = Ecosystem([str(root / n) for n in ("A", "B", "C", "D")])
    levels, cycle = eco.levels()
    assert levels == [["C"]]
    assert sorted(cycle) == ["A", "B", "D"]
    assert "dependency cycle" in render_graph(eco, color=False)


def test_dependency_matched_by_url_repo_name_and_externals(git_env):
    root = git_env
    make_project(root, "A")
    make_project(root, "B", {"core": "https://github.com/u/A.git", "stdlib": "fortran-lang/stdlib"})
    eco = Ecosystem([str(root / "A"), str(root / "B")])
    assert eco.projects["B"].deps == ["A"]
    assert eco.projects["B"].external == ["stdlib"]
    assert eco.dep_key("B", "A") == "core"
    assert "External dependencies (not managed): stdlib" in render_graph(eco, color=False)


def test_unreadable_projects_are_reported(git_env, tmp_path):
    (tmp_path / "plain").mkdir()
    (tmp_path / "nofobos").mkdir()
    git(tmp_path / "nofobos", "init", "-q")
    eco = Ecosystem([str(tmp_path / "missing"), str(tmp_path / "plain"), str(tmp_path / "nofobos")])
    errors = {p.name: p.error for p in eco.projects.values()}
    assert errors == {"missing": "directory not found", "plain": "not a git repository", "nofobos": "no fobos file"}
    statuses = eco.collect(fetch=False, ci=False)
    assert all(s.state == "error" for s in statuses)
    assert "directory not found" in render_table(statuses, color=False)


def test_duplicate_names_warn(git_env, tmp_path):
    make_project(tmp_path, "A")
    other = tmp_path / "other"
    other.mkdir()
    make_project(other, "A")
    eco = Ecosystem([str(tmp_path / "A"), str(other / "A")])
    assert list(eco.projects) == ["A"]
    assert "duplicate project name" in eco.warnings[0]


# ---------------------------------------------------------------------------
# Status collection
# ---------------------------------------------------------------------------


def test_status_of_released_project(git_env):
    root = git_env
    make_project(root, "A")
    (s,) = Ecosystem([str(root / "A")]).collect(fetch=False, ci=False)
    assert (s.branch, s.dirty, s.ahead, s.behind) == ("master", 0, 0, 0)
    assert (s.version, s.tag, s.unreleased, s.bump) == ("v1.0.0", "v1.0.0", 0, None)
    assert s.pushed
    assert s.ci == "unknown"
    assert isinstance(s.drift, int)
    assert s.state == "ok"


def test_status_dirty_ahead_unreleased(git_env):
    root = git_env
    repo = make_project(root, "A")
    commit(repo, "fix: a")
    commit(repo, "feat(io): b")
    (repo / "untracked.txt").write_text("x")
    (s,) = Ecosystem([str(repo)]).collect(fetch=False, ci=False)
    assert (s.dirty, s.ahead, s.behind) == (1, 2, 0)
    assert (s.unreleased, s.releasable, s.bump, s.next_version) == (2, 2, "minor", "v1.1.0")
    assert not s.pushed
    assert s.state == "unreleased"


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ([], False),
        (["docs/index.md"], False),
        ([".github/workflows/ci.yml", "README.md", "scripts/release.sh"], False),
        (["docs/package.json", "src/lib/a.F90"], True),
        (["fpm.toml"], True),
        (["fobos"], True),
    ],
)
def test_is_releasable(files, expected):
    assert is_releasable(files, eco_mod.DEFAULT_RELEASE_EXCLUDE) is expected


def test_only_releasable_commits_drive_the_bump(git_env):
    repo = make_project(git_env, "A")
    (repo / "docs").mkdir()
    (repo / ".github").mkdir()
    commit(repo, "feat(docs): new guide", "docs/guide.md")  # feat, but docs only: no release
    commit(repo, "build(fpm): track default branches", "fpm.toml")
    commit(repo, "ci: tweak", ".github/ci.yml")
    (s,) = Ecosystem([str(repo)]).collect(fetch=False, ci=False)
    assert (s.unreleased, s.releasable, s.bump, s.next_version) == (3, 1, "patch", "v1.0.1")
    assert s.state == "unreleased"
    assert "3, 1 to release (patch -> v1.0.1)" in render_table([s], color=False)


def test_nothing_to_release(git_env):
    repo = make_project(git_env, "A")
    commit(repo, "docs: typo", "README.md")
    (s,) = Ecosystem([str(repo)]).collect(fetch=False, ci=False)
    assert (s.unreleased, s.releasable, s.bump, s.next_version) == (1, 0, None, "")
    assert s.state == "ok"
    assert "1, none to release" in render_table([s], color=False)


def test_release_exclude_from_fobos(git_env):
    repo = make_project(git_env, "A", extra="[ecosystem]\nrelease_exclude = examples/*")
    assert Ecosystem([str(repo)]).projects["A"].release_exclude == ["examples/*"]
    (repo / "examples").mkdir()
    commit(repo, "feat: example", "examples/demo.f90")
    commit(repo, "docs: now counts", "README.md")
    (s,) = Ecosystem([str(repo)]).collect(fetch=False, ci=False)
    assert (s.releasable, s.bump) == (1, "patch")


def test_status_no_upstream(git_env):
    root = git_env
    make_project(root, "A", push=False)
    (s,) = Ecosystem([str(root / "A")]).collect(fetch=False, ci=False)
    assert s.ahead is None
    assert "no upstream" in render_table([s], color=False)


def test_fetch_updates_behind(git_env):
    root = git_env
    repo = make_project(root, "A")
    other = root / "other-clone"
    git(root, "clone", "-q", str(root / "remotes" / "A.git"), str(other))
    commit(other, "fix: upstream")
    git(other, "push", "-q")
    eco = Ecosystem([str(repo)])
    assert eco.collect(fetch=False, ci=False)[0].behind == 0
    (s,) = eco.collect(fetch=True, ci=False)
    assert s.behind == 1
    assert s.fetched


def test_pins_current_stale_unlocked(git_env):
    root = git_env
    a = make_project(root, "A")
    make_project(root, "B", {"A": "https://github.com/u/A"})
    make_project(root, "C", {"A": "https://github.com/u/A"})
    head = git(a, "rev-parse", "HEAD")
    write_lock(root / "B", {"A": head})
    eco = Ecosystem([str(root / n) for n in ("A", "B", "C")])

    statuses = eco.collect(fetch=False, ci=False)
    assert [(p.dep, p.state) for p in status_of(statuses, "B").pins] == [("A", "current")]
    assert [(p.dep, p.state) for p in status_of(statuses, "C").pins] == [("A", "unlocked")]
    assert status_of(statuses, "C").state == "stale"

    commit(a, "fix: newer")
    git(a, "push", "-q")
    statuses = eco.collect(fetch=False, ci=False)
    pin = status_of(statuses, "B").pins[0]
    assert (pin.state, pin.locked, pin.head) == ("stale", head, git(a, "rev-parse", "HEAD"))
    assert status_of(statuses, "B").state == "stale"


def test_pin_ahead_of_known_head(git_env):
    root = git_env
    a = make_project(root, "A")
    make_project(root, "B", {"A": "u/A"})
    newer = commit(a, "fix: local only")  # not pushed: origin/master still at the old head
    write_lock(root / "B", {"A": newer})
    statuses = Ecosystem([str(a), str(root / "B")]).collect(fetch=False, ci=False)
    assert status_of(statuses, "B").pins[0].state == "ahead"


# ---------------------------------------------------------------------------
# CI through gh (mocked)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("runs", "expected"),
    [
        ([], "none"),
        ([{"workflowName": "CI", "status": "completed", "conclusion": "success"}], "passing"),
        ([{"workflowName": "CI", "status": "completed", "conclusion": "failure"}], "failing"),
        ([{"workflowName": "CI", "status": "in_progress", "conclusion": ""}], "running"),
        (
            [
                {"workflowName": "CI", "status": "completed", "conclusion": "success"},  # re-run, newest first
                {"workflowName": "CI", "status": "completed", "conclusion": "failure"},
                {"workflowName": "Docs", "status": "completed", "conclusion": "skipped"},
            ],
            "passing",
        ),
    ],
)
def test_ci_status(monkeypatch, runs, expected):
    calls = []

    def fake_run(args, timeout=0):
        calls.append(args)
        return 0, json.dumps(runs)

    monkeypatch.setattr(eco_mod, "_run", fake_run)
    assert _ci_status("u/A", "abc", pushed=True) == expected
    assert calls[0][:5] == ["gh", "run", "list", "-R", "u/A"]


def test_ci_status_unknown_and_not_pushed(monkeypatch):
    monkeypatch.setattr(eco_mod, "_run", lambda args, timeout=0: (1, "gh: not logged in"))
    assert _ci_status("u/A", "abc", pushed=True) == "unknown"
    assert _ci_status("u/A", "abc", pushed=False) == "not pushed"
    assert _ci_status("", "abc", pushed=True) == "unknown"


def test_collect_without_gh_is_unknown(git_env, monkeypatch):
    make_project(git_env, "A")
    monkeypatch.setattr(eco_mod.shutil, "which", lambda name: None)
    (s,) = Ecosystem([str(git_env / "A")]).collect(fetch=False, ci=True)
    assert s.ci == "unknown"


# ---------------------------------------------------------------------------
# Renderers and discover
# ---------------------------------------------------------------------------


def test_renderers(git_env):
    root = git_env
    make_project(root, "A")
    make_project(root, "B", {"A": "u/A"})
    eco = Ecosystem([str(root / "A"), str(root / "B")])
    statuses = eco.collect(fetch=False, ci=False)

    table = render_table(statuses, color=False)
    assert "\033[" not in table
    assert table.splitlines()[0].startswith("Project")
    assert "not fetched" in table
    assert "\033[" in render_table(statuses, color=True)

    graph = render_graph(eco, color=False)
    assert "1. A  (level 0)" in graph
    assert "B\n`-- A" in graph

    source = mermaid(eco, statuses)
    assert 'p0["A"]:::ok' in source
    assert "p0 --> p1" in source
    assert 'p1["B"]:::stale' in source  # B has no lock: unlocked pin

    page = render_html(eco, statuses)
    assert page.startswith("<!doctype html>")
    assert "p0 --&gt; p1" in page
    assert "A &rarr; B" in page
    assert "@@" not in page  # every placeholder filled


def _page_data(page: str) -> dict:
    start = page.index('<script type="application/json" id="eco-data">') + len(
        '<script type="application/json" id="eco-data">'
    )
    return json.loads(page[start : page.index("</script>", start)])


def test_html_themes(git_env):
    make_project(git_env, "A")
    eco = Ecosystem([str(git_env / "A")])
    statuses = eco.collect(fetch=False, ci=False)
    data = _page_data(render_html(eco, statuses, theme="nord", mode="dark"))
    assert (data["theme"], data["mode"]) == ("nord", "dark")
    assert set(data["themes"]) == set(eco_mod.THEMES)
    assert data["mermaid"] == mermaid(eco, statuses)
    with pytest.raises(ValueError, match="unknown theme"):
        render_html(eco, statuses, theme="neon")
    with pytest.raises(ValueError, match="unknown mode"):
        render_html(eco, statuses, mode="dim")


@pytest.mark.parametrize("theme", list(eco_mod.THEMES))
def test_every_theme_is_complete(theme):
    keys = {"bg", "fg", "muted", "link", "green", "yellow", "orange", "red"}
    spec = eco_mod.THEMES[theme]
    assert spec["label"]
    for variant in ("light", "dark"):
        assert keys <= set(spec[variant]), (theme, variant)
        assert all(re.fullmatch(r"#[0-9a-f]{6}", c) for c in spec[variant].values()), (theme, variant)


def test_html_escapes_script_close(git_env, monkeypatch):
    make_project(git_env, "A")
    eco = Ecosystem([str(git_env / "A")])
    monkeypatch.setitem(eco_mod.THEMES, "evil", {"label": "</script><b>", "light": {}, "dark": {}})
    page = render_html(eco, eco.collect(fetch=False, ci=False), theme="evil")
    assert "</script><b>" not in page
    assert _page_data(page)["themes"]["evil"]["label"] == "</script><b>"


def test_discover(git_env, tmp_path):
    make_project(tmp_path, "A")
    make_project(tmp_path, "B")
    (tmp_path / "notes").mkdir()
    assert discover(str(tmp_path), [str(tmp_path / "A")]) == [str(tmp_path / "B")]
    assert discover(str(tmp_path / "missing"), []) == []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def write_config(tmp_path, projects: str) -> str:
    cfg = tmp_path / "config.ini"
    cfg.write_text(f"[ecosystem]\nroot = {tmp_path}\nprojects = {projects}\n")
    return str(cfg)


def test_cli_graph_and_dashboard_json(git_env, tmp_path):
    make_project(tmp_path, "A")
    make_project(tmp_path, "B", {"A": "u/A"})
    cfg = write_config(tmp_path, "A B")
    runner = CliRunner()

    result = runner.invoke(app, ["ecosystem", "graph", "-c", cfg, "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["release_order"] == ["A", "B"]

    result = runner.invoke(app, ["ecosystem", "dashboard", "-c", cfg, "--no-fetch", "--no-ci", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert [p["name"] for p in data["projects"]] == ["A", "B"]
    assert data["projects"][1]["pins"][0]["state"] == "unlocked"


def test_cli_dashboard_html(git_env, tmp_path, monkeypatch):
    make_project(tmp_path, "A")
    cfg = write_config(tmp_path, "A")
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)
    out = tmp_path / "dash.html"
    result = CliRunner().invoke(
        app, ["ecosystem", "dashboard", "-c", cfg, "--no-fetch", "--no-ci", "--format", "html", "-o", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert out.read_text().startswith("<!doctype html>")
    assert opened == ["file://" + str(out)]


def test_cli_dashboard_theme_from_config_and_cli(git_env, tmp_path, monkeypatch):
    make_project(tmp_path, "A")
    cfg = tmp_path / "config.ini"
    cfg.write_text(f"[ecosystem]\nroot = {tmp_path}\nprojects = A\ntheme = dracula\nmode = light\n")
    out = tmp_path / "dash.html"
    base = ["ecosystem", "dashboard", "-c", str(cfg), "--no-fetch", "--no-ci", "--format", "html", "--no-open"]
    runner = CliRunner()

    assert runner.invoke(app, [*base, "-o", str(out)]).exit_code == 0
    assert (_page_data(out.read_text())["theme"], _page_data(out.read_text())["mode"]) == ("dracula", "light")

    assert runner.invoke(app, [*base, "-o", str(out), "--theme", "Catppuccin", "--mode", "dark"]).exit_code == 0
    assert (_page_data(out.read_text())["theme"], _page_data(out.read_text())["mode"]) == ("catppuccin", "dark")

    result = runner.invoke(app, [*base, "-o", str(out), "--theme", "neon"])
    assert result.exit_code == 2
    assert "solarized" in result.output
    # a bad theme never breaks the terminal table
    assert (
        runner.invoke(
            app, ["ecosystem", "dashboard", "-c", str(cfg), "--no-fetch", "--no-ci", "--theme", "neon"]
        ).exit_code
        == 0
    )


def test_cli_errors(tmp_path):
    runner = CliRunner()
    empty = tmp_path / "empty.ini"
    empty.write_text("")
    assert runner.invoke(app, ["ecosystem", "graph", "-c", str(empty)]).exit_code == 1
    assert runner.invoke(app, ["ecosystem", "dashboard", "-c", str(empty), "--format", "pdf"]).exit_code == 2


def test_cli_discover(git_env, tmp_path):
    make_project(tmp_path, "A")
    make_project(tmp_path, "B")
    cfg = write_config(tmp_path, "A")
    result = CliRunner().invoke(app, ["ecosystem", "discover", "-c", cfg])
    assert result.exit_code == 0, result.output
    assert "  B\n" in result.output
    assert "fobis ecosystem add B" in result.output


def test_run_fobis_exit_code(git_env, tmp_path):
    """Through the real entry point the sub-app exits with the command's code and loads no fobos."""
    from fobis.fobis import run_fobis

    make_project(tmp_path, "A")
    cfg = write_config(tmp_path, "A")
    with pytest.raises(SystemExit) as exc:
        run_fobis(fake_args=["ecosystem", "graph", "-c", cfg])
    assert exc.value.code == 0


def test_main_runs_ecosystem_without_clirunner(git_env, tmp_path, monkeypatch, capsys):
    """fobis.main() dispatches ``ecosystem`` to the Typer app directly: real stdout and stdin."""
    import fobis.fobis as fobis_main

    make_project(tmp_path, "A")
    cfg = write_config(tmp_path, "A")
    monkeypatch.setattr(sys, "argv", ["fobis", "ecosystem", "graph", "-c", cfg])
    monkeypatch.setattr(fobis_main, "run_fobis", lambda *a, **k: pytest.fail("went through FoBiSConfig"))
    with pytest.raises(SystemExit) as exc:
        fobis_main.main()
    assert exc.value.code == 0
    assert "1. A  (level 0)" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# UserConfig [ecosystem] properties
# ---------------------------------------------------------------------------


def test_userconfig_ecosystem_unset(tmp_path):
    cfg = UserConfig(path=str(tmp_path / "none.ini"))
    assert cfg.ecosystem_root == ""
    assert cfg.ecosystem_projects == []
    assert (cfg.ecosystem_theme, cfg.ecosystem_mode) == ("github", "auto")


def test_userconfig_ecosystem_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg_path = tmp_path / "config.ini"
    cfg_path.write_text("[ecosystem]\nroot = ~/fortran\nprojects = PENF\n  FACE /abs/FLAP ~/other/X\n")
    cfg = UserConfig(path=str(cfg_path))
    assert cfg.ecosystem_root == str(tmp_path / "fortran")
    assert cfg.ecosystem_projects == [
        str(tmp_path / "fortran" / "PENF"),
        str(tmp_path / "fortran" / "FACE"),
        "/abs/FLAP",
        str(tmp_path / "other" / "X"),
    ]


def test_userconfig_ecosystem_relative_without_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg_path = tmp_path / "config.ini"
    cfg_path.write_text("[ecosystem]\nprojects = A\n")
    assert UserConfig(path=str(cfg_path)).ecosystem_projects == [str(tmp_path / "A")]


# ---------------------------------------------------------------------------
# Phase 2: exec, fetch, check, scaffold across projects
# ---------------------------------------------------------------------------


def test_select(git_env):
    make_project(git_env, "A")
    make_project(git_env, "B", {"A": "u/A"})
    make_project(git_env, "C", {"B": "u/B"})
    eco = Ecosystem([str(git_env / n) for n in ("C", "B", "A")])
    assert eco_mod.select(eco) == ["A", "B", "C"]
    assert eco_mod.select(eco, only=["c", "A"]) == ["A", "C"]
    assert eco_mod.select(eco, start="b") == ["B", "C"]
    with pytest.raises(ValueError, match="unknown project"):
        eco_mod.select(eco, only=["Z"])
    assert eco_mod.transitive_dependents(eco, "A") == ["B", "C"]
    assert eco_mod.transitive_dependents(eco, "C") == []


def test_run_step_classifies(tmp_path, capfd):
    assert eco_mod.run_step("p", "echo hello", str(tmp_path)).status == "passed"
    failed = eco_mod.run_step("p", "exit 3", str(tmp_path))
    assert (failed.status, failed.returncode, failed.detail) == ("failed", 3, "exit 3")
    crashed = eco_mod.run_step("p", "kill -SEGV $$", str(tmp_path))
    assert (crashed.status, crashed.detail) == ("crashed", "SIGSEGV")
    out = capfd.readouterr().out
    assert out.index("==> p: echo hello") < out.index("hello\n")  # header before the command's output


def test_exec_all_order_skip_fail_fast(git_env, tmp_path):
    make_project(tmp_path, "A")
    make_project(tmp_path, "B", {"A": "u/A"})
    make_project(tmp_path, "C", {"B": "u/B"})
    eco = Ecosystem([str(tmp_path / n) for n in ("C", "B", "A", "missing")])
    order = eco_mod.select(eco)
    log = tmp_path / "order.log"
    results = eco_mod.exec_all(eco, f"basename $PWD >> {log}; test $(basename $PWD) != B", order, echo=lambda *a: None)
    assert log.read_text().split() == ["A", "B", "C"]
    assert [(r.name, r.status) for r in results] == [
        ("A", "passed"),
        ("missing", "skipped"),  # unreadable, no dependencies: level 0
        ("B", "failed"),
        ("C", "passed"),
    ]
    results = eco_mod.exec_all(eco, "test $(basename $PWD) != B", order, fail_fast=True, echo=lambda *a: None)
    assert [r.status for r in results] == ["passed", "skipped", "failed", "not run"]
    assert "1 passed, 1 failed: B" in eco_mod.render_results(results, color=False)


def test_exec_uses_this_fobis(git_env, tmp_path, capfd):
    from fobis import __version__

    make_project(tmp_path, "A")
    eco = Ecosystem([str(tmp_path / "A")])
    (r,) = eco_mod.exec_all(eco, "fobis --version && FoBiS.py --version && command -v fobis", ["A"])
    assert r.status == "passed"
    out = capfd.readouterr().out
    assert out.count(__version__) == 2
    assert "/fobis-shim-" in out


def test_fetch_all_runs_fetch_update_in_dependents(git_env, tmp_path, monkeypatch):
    make_project(tmp_path, "A")
    make_project(tmp_path, "B", {"A": "u/A"})
    eco = Ecosystem([str(tmp_path / "A"), str(tmp_path / "B")])
    calls = []
    monkeypatch.setattr(
        eco_mod,
        "run_step",
        lambda name, cmd, cwd, env=None, echo=None: calls.append((name, cmd)) or eco_mod.StepResult(name, "passed"),
    )
    results = eco_mod.fetch_all(eco, ["A", "B"])
    assert calls == [("B", "fobis fetch --update")]
    assert [(r.name, r.status, r.detail) for r in results] == [("A", "skipped", "no dependencies"), ("B", "passed", "")]


def test_check_commands(git_env, tmp_path):
    make_project(tmp_path, "A", extra="[ecosystem]\ncheck = fobis build --mode x\n  ./run.sh")
    make_project(tmp_path, "B", extra="[rule-makecoverage]\nrule = true")
    make_project(tmp_path, "C")
    eco = Ecosystem([str(tmp_path / n) for n in "ABC"])
    assert eco_mod.check_commands(eco.projects["A"]) == ["fobis build --mode x", "./run.sh"]
    assert eco_mod.check_commands(eco.projects["B"]) == ["fobis rule --ex makecoverage"]
    assert eco_mod.check_commands(eco.projects["C"]) == ["fobis build"]


def test_copy_working_copy(git_env, tmp_path):
    repo = make_project(tmp_path, "A")
    (repo / "file.txt").write_text("modified, uncommitted\n")
    (repo / "new.txt").write_text("untracked\n")
    (repo / "third_party").mkdir()
    (repo / "third_party" / "ignored.o").write_text("build product\n")
    eco_mod.copy_working_copy(str(repo), str(tmp_path / "copy"))
    copy = tmp_path / "copy"
    assert (copy / "file.txt").read_text() == "modified, uncommitted\n"
    assert (copy / "new.txt").exists()
    assert not (copy / "third_party").exists()
    assert not (copy / ".git").exists()


def _fetched(dependent, dep_name, root):
    """Simulate 'fobis fetch': clone the dependency's remote into the dependent's deps_dir."""
    target = dependent / "third_party" / dep_name
    target.parent.mkdir(exist_ok=True)
    git(root, "clone", "-q", str(root / "remotes" / f"{dep_name}.git"), str(target))
    (dependent / "third_party" / ".deps_config.ini").write_text("[deps]\nsrc = third_party/" + dep_name + "\n")


def test_check_builds_dependents_against_local_working_copy(git_env, tmp_path):
    a = make_project(tmp_path, "A")
    b = make_project(
        tmp_path,
        "B",
        {"A": "u/A"},
        extra="[ecosystem]\ncheck = grep -q LOCAL third_party/A/file.txt\n  test -f third_party/.deps_config.ini",
    )
    c = make_project(tmp_path, "C", {"B": "u/B"}, extra="[ecosystem]\ncheck = test -f third_party/B/fobos")
    _fetched(b, "A", tmp_path)
    _fetched(c, "B", tmp_path)
    (a / "file.txt").write_text("LOCAL uncommitted change\n")  # never committed nor pushed
    eco = Ecosystem([str(p) for p in (a, b, c)])

    results, kept = eco_mod.check_dependents(eco, "A", echo=lambda *x: None)
    assert [(r.name, r.status) for r in results] == [("B", "passed"), ("C", "passed")]
    assert kept is None
    assert "LOCAL" not in (b / "third_party" / "A" / "file.txt").read_text()  # the real dependent is untouched
    assert not (b / "third_party" / "A" / "exe").exists()


def test_check_failure_keeps_stage_and_reports_missing_deps(git_env, tmp_path):
    make_project(tmp_path, "A")
    b = make_project(tmp_path, "B", {"A": "u/A"}, extra="[ecosystem]\ncheck = false")
    make_project(tmp_path, "C", {"A": "u/A", "X": "u/X"}, extra="[ecosystem]\ncheck = true")
    _fetched(b, "A", tmp_path)
    eco = Ecosystem([str(tmp_path / n) for n in "ABC"])
    results, kept = eco_mod.check_dependents(eco, "A", echo=lambda *x: None)
    assert [(r.name, r.status) for r in results] == [("B", "failed"), ("C", "skipped")]
    assert "dependency X not fetched in C" in results[1].detail
    assert kept and os.path.isdir(os.path.join(kept, "B"))


def test_scaffold_skip(git_env, tmp_path):
    from fobis.Scaffolder import Scaffolder

    repo = make_project(tmp_path, "A", extra="[scaffold]\nskip = scripts/release.sh .github/*")
    scaffolder = eco_mod.scaffold_for(str(repo))
    assert scaffolder.skip == ["scripts/release.sh", ".github/*"]
    states = dict(scaffolder.drift())
    assert states["scripts/release.sh"] == "skipped"
    assert all(s == "skipped" for d, s in states.items() if d.startswith(".github/"))
    scaffolder.sync(yes=True)
    assert not (repo / "scripts" / "release.sh").exists()
    assert (repo / "scripts" / "install.sh").exists()
    Scaffolder({}, cwd=str(tmp_path / "other"), skip=["scripts/*"]).init(yes=True)
    assert not (tmp_path / "other" / "scripts" / "install.sh").exists()


def test_cli_exec_and_errors(git_env, tmp_path, capfd):
    make_project(tmp_path, "A")
    cfg = write_config(tmp_path, "A")
    runner = CliRunner()
    assert runner.invoke(app, ["ecosystem", "exec", "-c", cfg, "--", "true"]).exit_code == 0
    assert runner.invoke(app, ["ecosystem", "exec", "-c", cfg, "--", "false"]).exit_code == 1
    assert runner.invoke(app, ["ecosystem", "exec", "-c", cfg]).exit_code == 2
    assert runner.invoke(app, ["ecosystem", "exec", "-c", cfg, "--only", "Z", "--", "true"]).exit_code == 2
    result = runner.invoke(app, ["ecosystem", "check", "-c", cfg, "A"])
    assert result.exit_code == 0
    assert "nothing to check" in result.output


def test_cli_scaffold_sync_never_writes_without_consent(git_env, tmp_path):
    repo = make_project(tmp_path, "A")
    cfg = write_config(tmp_path, "A")
    target = repo / "scripts" / "install.sh"
    base = ["ecosystem", "scaffold", "sync", "-c", cfg, "--files", "scripts/install.sh"]
    runner = CliRunner()

    result = runner.invoke(app, base)  # dry run
    assert result.exit_code == 0 and "Dry run" in result.output
    assert not target.exists()

    result = runner.invoke(app, [*base, "--apply"], input="n\n")
    assert result.exit_code == 0 and not target.exists()

    result = runner.invoke(app, [*base, "--apply"])  # no answer possible (EOF): nothing written
    assert result.exit_code == 1 and not target.exists()

    result = runner.invoke(app, [*base, "--apply"], input="y\n")
    assert result.exit_code == 0 and target.exists()

    status = runner.invoke(app, ["ecosystem", "scaffold", "status", "-c", cfg, "--files", "scripts/install.sh"])
    assert status.exit_code == 0 and "A: in sync" in status.output


# ---------------------------------------------------------------------------
# Phase 3: release train
# ---------------------------------------------------------------------------

FAKE_RELEASE = """#!/usr/bin/env bash
set -euo pipefail
read -rp "Proceed? [y/N] " answer
[[ "$answer" == y ]] || { echo "Aborted."; exit 0; }
echo "$1" > VERSION
git add VERSION
git commit -qm "chore(release): $1"
git tag -a "$1" -m "Release $1"
git push -q origin master --follow-tags
"""


def releasable_project(root, name, deps=None, script=FAKE_RELEASE, change="fix: a change"):
    """A project with release.sh committed, pushed, and one unreleased releasable commit."""
    repo = make_project(root, name, deps)
    (repo / "scripts").mkdir()
    (repo / "scripts" / "release.sh").write_text(script)
    (repo / "scripts" / "release.sh").chmod(0o755)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "chore: add release script")
    git(repo, "tag", "-f", "v1.0.0")  # the script commit is not a release change
    git(repo, "push", "-q", "--force", "origin", "master", "--tags")
    if change:
        commit(repo, change, "src.f90")
        git(repo, "push", "-q")
    return repo


@pytest.fixture
def release_env(git_env, monkeypatch):
    """git-cliff present, no gh, fetch of dependents recorded instead of run."""
    real_which = eco_mod.shutil.which
    monkeypatch.setattr(
        eco_mod.shutil,
        "which",
        lambda n: "/usr/bin/git-cliff" if n == "git-cliff" else None if n == "gh" else real_which(n),
    )
    fetched = []
    monkeypatch.setattr(
        eco_mod,
        "fetch_all",
        lambda eco, names, fail_fast=False, echo=None: (
            fetched.extend(names) or [eco_mod.StepResult(n, "passed") for n in names]
        ),
    )
    return fetched


def test_parse_bump_overrides(git_env):
    make_project(git_env, "A")
    eco = Ecosystem([str(git_env / "A")])
    assert eco_mod.parse_bump_overrides(["a=minor", "A=v2.0.0"], eco) == {"A": "v2.0.0"}
    for bad in ("A", "A=", "Z=patch", "A=huge", "A=2.0"):
        with pytest.raises(ValueError):
            eco_mod.parse_bump_overrides([bad], eco)


def test_plan_release(git_env, release_env):
    releasable_project(git_env, "A")
    releasable_project(git_env, "B", {"A": "u/A"}, change="feat: new API")
    releasable_project(git_env, "C", change=None)
    eco = Ecosystem([str(git_env / n) for n in "ABC"])
    statuses = eco.collect(fetch=False, ci=False)
    plan = eco_mod.plan_release(eco, statuses)
    assert [(i.name, i.bump, i.version, i.blockers) for i in plan] == [
        ("A", "patch", "v1.0.1", []),
        ("B", "minor", "v1.1.0", []),
    ]
    plan = eco_mod.plan_release(eco, statuses, overrides={"A": "major", "C": "v1.0.5"})
    assert [(i.name, i.bump, i.version) for i in plan] == [
        ("A", "major", "v2.0.0"),
        ("C", "explicit", "v1.0.5"),
        ("B", "minor", "v1.1.0"),
    ]
    assert "CI at HEAD: unknown" in plan[0].warnings
    assert "Release plan" in eco_mod.render_plan(plan, color=False)
    assert eco_mod.render_plan([], color=False).startswith("Nothing to release")


def test_plan_release_blockers(git_env, release_env):
    a = releasable_project(git_env, "A")
    releasable_project(git_env, "B")
    make_project(git_env, "C")
    commit(git_env / "C", "fix: no script", "x.f90")
    git(git_env / "C", "push", "-q")
    (a / "dirty.txt").write_text("x")
    eco = Ecosystem([str(git_env / n) for n in "ABC"])
    statuses = eco.collect(fetch=False, ci=False)
    status_of(statuses, "B").ci = "failing"
    plan = {i.name: i for i in eco_mod.plan_release(eco, statuses, overrides={"B": "v0.9.0"})}
    assert "working tree not clean (1 changed)" in plan["A"].blockers
    assert "v0.9.0 is not above the current v1.0.0" in plan["B"].blockers
    assert "CI failing at HEAD" in plan["B"].blockers
    assert "no executable scripts/release.sh" in plan["C"].blockers


def test_release_train(git_env, release_env):
    a = releasable_project(git_env, "A")
    b = releasable_project(git_env, "B", {"A": "u/A"})
    eco = Ecosystem([str(a), str(b)])
    plan = eco_mod.plan_release(eco, eco.collect(fetch=False, ci=False))
    results = eco_mod.run_release_train(eco, plan, yes=True, echo=lambda *x: None)
    assert [(r.name, r.status) for r in results] == [("A", "passed"), ("B", "passed")]
    assert "v1.0.1 pushed (GitHub release not awaited)" in results[0].detail
    for repo in (a, b):
        assert git(repo, "ls-remote", "--tags", "origin", "refs/tags/v1.0.1")
    assert release_env == ["B"]  # A's dependents refreshed after A's release
    # released: nothing left to plan
    assert eco_mod.plan_release(eco, eco.collect(fetch=False, ci=False)) == []


def test_release_train_stops_when_declined(git_env, release_env):
    declining = FAKE_RELEASE.replace('read -rp "Proceed? [y/N] " answer', "answer=n")
    a = releasable_project(git_env, "A", script=declining)
    b = releasable_project(git_env, "B", {"A": "u/A"})
    eco = Ecosystem([str(a), str(b)])
    plan = eco_mod.plan_release(eco, eco.collect(fetch=False, ci=False))
    results = eco_mod.run_release_train(eco, plan, yes=True, echo=lambda *x: None)
    assert [(r.name, r.status) for r in results] == [("A", "aborted"), ("B", "not run")]
    assert "v1.0.1 not created" in results[0].detail
    assert release_env == []


def test_release_train_waits_for_github(git_env, release_env, monkeypatch):
    a = releasable_project(git_env, "A")
    eco = Ecosystem([str(a)])
    eco.projects["A"].slug = "u/A"
    monkeypatch.setattr(eco_mod.shutil, "which", lambda n: "/usr/bin/" + n)
    answers = iter([False, True])
    monkeypatch.setattr(eco_mod, "github_release_published", lambda slug, tag: next(answers))
    plan = eco_mod.plan_release(eco, eco.collect(fetch=False, ci=False))
    (result,) = eco_mod.run_release_train(eco, plan, yes=True, interval=0, echo=lambda *x: None)
    assert (result.status, result.detail) == ("passed", "released v1.0.1")

    commit(a, "fix: again", "src.f90")
    git(a, "push", "-q")
    monkeypatch.setattr(eco_mod, "github_release_published", lambda slug, tag: False)
    plan = eco_mod.plan_release(eco, eco.collect(fetch=False, ci=False))
    (result,) = eco_mod.run_release_train(eco, plan, yes=True, timeout=0, interval=0, echo=lambda *x: None)
    assert result.status == "failed"
    assert "GitHub release not published" in result.detail


def test_cli_release(git_env, release_env, tmp_path):
    releasable_project(tmp_path, "A")
    cfg = write_config(tmp_path, "A")
    runner = CliRunner()
    base = ["ecosystem", "release", "-c", cfg, "--no-fetch"]

    result = runner.invoke(app, [*base, "--dry-run"])
    assert result.exit_code == 0 and "Dry run" in result.output and "v1.0.0 -> v1.0.1" in result.output

    result = runner.invoke(app, base)  # no answer possible: nothing released
    assert result.exit_code == 1
    assert not git(tmp_path / "A", "tag", "-l", "v1.0.1")

    assert runner.invoke(app, [*base, "--bump", "A=huge"]).exit_code == 2

    result = runner.invoke(app, [*base, "--bump", "A=minor", "--yes"])
    assert result.exit_code == 0, result.output
    assert git(tmp_path / "A", "tag", "-l", "v1.1.0") == "v1.1.0"

    result = runner.invoke(app, base)
    assert result.exit_code == 0 and "Nothing to release" in result.output


def test_cli_release_blocked_and_resume_hint(git_env, release_env, tmp_path):
    a = releasable_project(
        tmp_path, "A", script=FAKE_RELEASE.replace("git push -q origin master --follow-tags", "exit 4")
    )
    cfg = write_config(tmp_path, "A")
    runner = CliRunner()
    (a / "dirty.txt").write_text("x")
    result = runner.invoke(app, ["ecosystem", "release", "-c", cfg, "--no-fetch", "--yes"])
    assert result.exit_code == 1 and "BLOCKED" in result.output
    (a / "dirty.txt").unlink()
    result = runner.invoke(app, ["ecosystem", "release", "-c", cfg, "--no-fetch", "--yes", "--bump", "A=minor"])
    assert result.exit_code == 1
    assert "resume with: fobis ecosystem release --from A --bump A=minor" in result.output


# ---------------------------------------------------------------------------
# Registry editing: add / remove
# ---------------------------------------------------------------------------

USER_CONFIG = """# FoBiS user configuration
[llm]
# keep this comment
model = mymodel

[ecosystem]
# Directory the projects live in
root = {root}
projects = A
           B
theme = nord

[other]
key = value
"""


def test_set_ecosystem_projects_keeps_everything_else(tmp_path):
    cfg_path = tmp_path / "config.ini"
    cfg_path.write_text(USER_CONFIG.format(root=tmp_path))
    cfg = UserConfig(path=str(cfg_path))
    cfg.set_ecosystem_projects(["A", "C"])
    text = cfg_path.read_text()
    assert text == USER_CONFIG.format(root=tmp_path).replace("projects = A\n           B\n", "projects = A C\n")
    assert cfg.ecosystem_entries == ["A", "C"]  # reloaded
    assert cfg.ecosystem_theme == "nord"


def test_set_ecosystem_projects_creates_section_and_wraps(tmp_path):
    cfg_path = tmp_path / "config.ini"
    cfg_path.write_text("[llm]\nmodel = m\n")
    cfg = UserConfig(path=str(cfg_path))
    names = [f"Project{i:02d}" for i in range(20)]
    cfg.set_ecosystem_projects(names)
    lines = cfg_path.read_text().splitlines()
    assert lines[:3] == ["[llm]", "model = m", ""]
    assert lines[3] == "[ecosystem]"
    assert all(len(line) <= 100 for line in lines)
    assert UserConfig(path=str(cfg_path)).ecosystem_entries == names

    missing = tmp_path / "new" / "config.ini"  # no file yet
    UserConfig(path=str(missing)).set_ecosystem_projects(["A"])
    assert missing.read_text() == "[ecosystem]\nprojects = A\n"


def test_set_ecosystem_projects_section_without_key(tmp_path):
    cfg_path = tmp_path / "config.ini"
    cfg_path.write_text("[ecosystem]\n# projects = X Y\nroot = /r\n")
    UserConfig(path=str(cfg_path)).set_ecosystem_projects(["A"])
    assert cfg_path.read_text() == "[ecosystem]\nprojects = A\n# projects = X Y\nroot = /r\n"


def test_ecosystem_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg_path = tmp_path / "config.ini"
    cfg_path.write_text(f"[ecosystem]\nroot = {tmp_path / 'fortran'}\n")
    cfg = UserConfig(path=str(cfg_path))
    assert cfg.ecosystem_entry(str(tmp_path / "fortran" / "PENF")) == "PENF"
    assert cfg.ecosystem_entry(str(tmp_path / "elsewhere" / "X")) == "~/elsewhere/X"
    assert cfg.ecosystem_entry("/opt/Y") == "/opt/Y"


def test_cli_add_and_remove(git_env, tmp_path):
    for name in "ABC":
        make_project(tmp_path, name, {"A": "u/A"} if name == "B" else None)
    outside = tmp_path / "outside"
    outside.mkdir()
    make_project(outside, "D")
    (tmp_path / "plain").mkdir()
    cfg_path = tmp_path / "config.ini"
    cfg_path.write_text(f"# my config\n[ecosystem]\nroot = {tmp_path}\nprojects = A\n")
    cfg = str(cfg_path)
    runner = CliRunner()

    result = runner.invoke(app, ["ecosystem", "add", "-c", cfg, "B", str(outside / "D"), "A"])
    assert result.exit_code == 0, result.output
    assert "A: already registered" in result.output
    assert UserConfig(path=cfg).ecosystem_entries == ["A", "B", str(outside / "D")]
    assert cfg_path.read_text().startswith("# my config\n")

    before = cfg_path.read_text()
    for bad, message in [
        ("plain", "not a git repository"),
        ("nope", "no such directory"),
        (str(tmp_path / "remotes"), "not a git repository"),
    ]:
        result = runner.invoke(app, ["ecosystem", "add", "-c", cfg, "C", bad])
        assert result.exit_code == 1 and message in result.output, (bad, result.output)
        assert cfg_path.read_text() == before  # all or nothing: C not added either

    other = tmp_path / "other"
    other.mkdir()
    make_project(other, "B")
    result = runner.invoke(app, ["ecosystem", "add", "-c", cfg, str(other / "B")])
    assert result.exit_code == 1 and "the name B is already taken" in result.output

    result = runner.invoke(app, ["ecosystem", "remove", "-c", cfg, "a", "D"])
    assert result.exit_code == 0, result.output
    assert "note: B still depends on A" in result.output
    assert UserConfig(path=cfg).ecosystem_entries == ["B"]

    result = runner.invoke(app, ["ecosystem", "remove", "-c", cfg, "B", "Z"])
    assert result.exit_code == 1 and "Z: not registered" in result.output
    assert UserConfig(path=cfg).ecosystem_entries == ["B"]
