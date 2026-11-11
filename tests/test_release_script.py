"""Tests for the scaffolded scripts/release.sh: its recovery hints must match what actually happened."""

from __future__ import annotations

import os
import shutil
import subprocess
from importlib import resources

import pytest

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="release.sh needs bash")

TEMPLATE = resources.files("fobis") / "scaffolds" / "verbatim" / "scripts" / "release.sh"


def git(cwd, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A released project (v1.0.0) with one unreleased commit, a local bare origin and a git-cliff stub."""
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(
        "[user]\n\tname = T\n\temail = t@example.com\n[commit]\n\tgpgsign = false\n[tag]\n\tgpgSign = false\n"
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    bindir = tmp_path / "bin"  # `git cliff` runs the git-cliff executable found on PATH
    bindir.mkdir()
    stub = bindir / "git-cliff"
    stub.write_text('#!/usr/bin/env bash\n# git-cliff --tag TAG --output FILE\necho "## [$2]" > "$4"\n')
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")

    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "master", str(bare))
    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", str(bare), str(work))
    (work / "scripts").mkdir()
    shutil.copy(str(TEMPLATE), work / "scripts" / "release.sh")
    (work / "scripts" / "release.sh").chmod(0o755)
    (work / "VERSION").write_text("v1.0.0\n")
    (work / "CHANGELOG.md").write_text("## [v1.0.0]\n")
    git(work, "add", "-A")
    git(work, "commit", "-qm", "feat: first")
    git(work, "tag", "-a", "v1.0.0", "-m", "v1.0.0")
    (work / "src.f90").write_text("! change\n")
    git(work, "add", "-A")
    git(work, "commit", "-qm", "fix: a change")
    git(work, "push", "-q", "origin", "master", "--tags")
    return work


def release(repo, answer: str = "y\n"):
    return subprocess.run(
        ["./scripts/release.sh", "v1.0.1"], cwd=repo, input=answer, capture_output=True, text=True, check=False
    )


def hint_commands(output: str) -> list[str]:
    """The commands the recovery message tells to run (4-space indented lines)."""
    return [line.strip() for line in output.splitlines() if line.startswith("    ") and line.strip().startswith("git ")]


def test_release_succeeds(repo):
    result = release(repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert git(repo, "ls-remote", "--tags", "origin", "refs/tags/v1.0.1")
    assert (repo / "VERSION").read_text().strip() == "v1.0.1"


def test_declined_changes_nothing(repo):
    head = git(repo, "rev-parse", "HEAD")
    result = release(repo, "n\n")
    assert result.returncode == 0 and "Aborted" in result.stdout
    assert git(repo, "rev-parse", "HEAD") == head
    assert not git(repo, "status", "--porcelain")


def test_failed_commit_reports_bumped_and_its_hint_restores_the_tree(repo):
    git(repo, "config", "commit.gpgsign", "true")
    git(repo, "config", "gpg.program", "false")  # signing fails: the commit is refused
    head = git(repo, "rev-parse", "HEAD")
    result = release(repo)
    out = result.stdout + result.stderr
    assert result.returncode != 0
    assert "FAILED at stage: bumped" in out  # not "committed": no commit was made
    assert "git tag" not in out  # tagging now would tag the previous commit
    assert git(repo, "rev-parse", "HEAD") == head
    assert git(repo, "status", "--porcelain")  # release files modified, and staged
    for command in hint_commands(out):
        subprocess.run(command, cwd=repo, shell=True, check=True)
    assert not git(repo, "status", "--porcelain")  # the hint really restores the tree
    assert (repo / "VERSION").read_text().strip() == "v1.0.0"


def test_failed_tag_reports_committed_and_its_hint_completes_the_release(repo):
    git(repo, "config", "tag.gpgSign", "true")
    git(repo, "config", "gpg.program", "false")  # the commit is fine, signing the tag fails
    result = release(repo)
    out = result.stdout + result.stderr
    assert result.returncode != 0
    assert "FAILED at stage: committed" in out
    assert git(repo, "log", "-1", "--format=%s") == "chore(release): v1.0.1"
    assert not git(repo, "tag", "-l", "v1.0.1")
    git(repo, "config", "tag.gpgSign", "false")
    for command in hint_commands(out):
        subprocess.run(command, cwd=repo, shell=True, check=True)
    assert git(repo, "ls-remote", "--tags", "origin", "refs/tags/v1.0.1")


def test_failed_push_reports_tagged_and_its_hint_completes_the_release(repo, tmp_path):
    git(repo, "config", "remote.origin.pushurl", str(tmp_path / "nowhere.git"))
    result = release(repo)
    out = result.stdout + result.stderr
    assert result.returncode != 0
    assert "FAILED at stage: tagged" in out
    assert git(repo, "tag", "-l", "v1.0.1") == "v1.0.1"
    git(repo, "config", "--unset", "remote.origin.pushurl")
    for command in hint_commands(out):
        subprocess.run(command, cwd=repo, shell=True, check=True)
    assert git(repo, "ls-remote", "--tags", "origin", "refs/tags/v1.0.1")


def test_die_after_confirmation_prints_the_recovery_hint(repo):
    """`die` exits without firing the ERR trap: after the confirmation it must still show how to recover."""
    script = repo / "scripts" / "release.sh"
    anchor = 'success "VERSION updated to ${NEW_TAG}"\n'
    text = script.read_text()
    assert text.count(anchor) == 1
    script.write_text(text.replace(anchor, anchor + 'die "injected failure"\n'))
    git(repo, "commit", "-qam", "test: inject a failure")
    git(repo, "push", "-q")
    result = release(repo)
    out = result.stdout + result.stderr
    assert result.returncode == 1
    assert "injected failure" in out
    assert "FAILED at stage: bumped" in out
    for command in hint_commands(out):
        subprocess.run(command, cwd=repo, shell=True, check=True)
    assert not git(repo, "status", "--porcelain")


def test_die_before_confirmation_prints_no_recovery_hint(repo):
    (repo / "dirty.txt").write_text("x")  # pre-flight refuses a dirty tree
    result = release(repo)
    assert result.returncode == 1
    assert "working tree is dirty" in result.stderr
    assert "FAILED at stage" not in result.stdout + result.stderr


# ── The project hook: scripts/release_hook.sh ────────────────────────────────
HOOK = """#!/usr/bin/env bash
# --check TAG: refuse a version README.md has no line for; TAG: write it there and print the file
set -euo pipefail
if [[ "$1" == --check ]]; then
   grep -q "^next: $2$" README.md || { echo "README.md: no 'next: $2' line" >&2; exit 3; }
   exit 0
fi
sed -i.bak "s/^next: $1$/released: $1/" README.md && rm -f README.md.bak
{body}
"""


def add_hook(repo, body: str = "echo README.md", next_version: str = "v1.0.1", executable: bool = True):
    """A committed hook and the README.md it updates."""
    (repo / "README.md").write_text(f"next: {next_version}\n")
    hook = repo / "scripts" / "release_hook.sh"
    hook.write_text(HOOK.replace("{body}", body))
    hook.chmod(0o755 if executable else 0o644)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "chore: a release hook")
    git(repo, "push", "-q")


def test_hook_files_are_committed_with_the_release(repo):
    add_hook(repo)
    result = release(repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "release_hook.sh: 1 file(s) to commit" in result.stdout
    assert git(repo, "log", "-1", "--format=%s") == "chore(release): v1.0.1"
    assert set(git(repo, "show", "--name-only", "--format=", "HEAD").split()) == {
        "CHANGELOG.md",
        "VERSION",
        "README.md",
    }
    assert (repo / "README.md").read_text() == "released: v1.0.1\n"
    assert not git(repo, "status", "--porcelain")


def test_hook_check_failure_stops_before_any_change(repo):
    add_hook(repo, next_version="v2.0.0")  # README.md is ready for another version
    head = git(repo, "rev-parse", "HEAD")
    result = release(repo)
    out = result.stdout + result.stderr
    assert result.returncode == 1
    assert "README.md: no 'next: v1.0.1' line" in result.stderr  # the hook's own message is shown
    assert "release_hook.sh --check v1.0.1 failed" in result.stderr
    assert "Proceed?" not in out and "FAILED at stage" not in out
    assert git(repo, "rev-parse", "HEAD") == head
    assert not git(repo, "status", "--porcelain")


def test_hook_failure_after_confirmation_hint_restores_the_tree(repo):
    add_hook(repo, body="echo README.md; exit 4")  # changes README.md, then fails
    head = git(repo, "rev-parse", "HEAD")
    result = release(repo)
    out = result.stdout + result.stderr
    assert result.returncode == 1
    assert "release_hook.sh v1.0.1 failed" in out
    assert "FAILED at stage: bumped" in out
    assert "may have changed other files" in out
    assert git(repo, "rev-parse", "HEAD") == head
    for command in hint_commands(out):
        subprocess.run(command, cwd=repo, shell=True, check=True)
    git(repo, "checkout", "HEAD", "--", "README.md")  # the hint's advice: git status shows what the hook changed
    assert not git(repo, "status", "--porcelain")


@pytest.mark.parametrize("printed", ["NOT_A_FILE.md", "/etc/hostname", "../origin.git/HEAD"])
def test_hook_output_must_name_files_of_the_repository(repo, printed):
    add_hook(repo, body=f"echo README.md; echo {printed}")
    result = release(repo)
    assert result.returncode == 1
    assert f"printed '{printed}'" in result.stderr
    assert git(repo, "log", "-1", "--format=%s") == "chore: a release hook"  # nothing committed


def test_hook_not_executable_is_not_run(repo):
    add_hook(repo, executable=False)
    result = release(repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "release_hook.sh is not executable: not run" in result.stdout + result.stderr
    assert (repo / "README.md").read_text() == "next: v1.0.1\n"  # untouched
    assert set(git(repo, "show", "--name-only", "--format=", "HEAD").split()) == {"CHANGELOG.md", "VERSION"}


# ── CMake: a version written into project() ───────────────────────────────────
def add_cmake(repo, project_line: str):
    """A committed CMakeLists.txt whose project() line is *project_line*."""
    (repo / "CMakeLists.txt").write_text(f"cmake_minimum_required(VERSION 3.13)\n{project_line}\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "build: cmake")
    git(repo, "push", "-q")


def test_cmake_literal_version_is_refused_before_any_change(repo):
    add_cmake(repo, "project(Demo VERSION 0.9.9 LANGUAGES Fortran)")
    head = git(repo, "rev-parse", "HEAD")
    result = release(repo)
    out = result.stdout + result.stderr
    assert result.returncode == 1
    assert "CMakeLists.txt declares project(... VERSION 0.9.9)" in result.stderr
    assert "Proceed?" not in out and "FAILED at stage" not in out
    assert git(repo, "rev-parse", "HEAD") == head
    assert not git(repo, "status", "--porcelain")


def test_cmake_version_read_from_version_file_is_accepted(repo):
    add_cmake(repo, "project(Demo VERSION ${demo_version} LANGUAGES Fortran)")
    result = release(repo)
    assert result.returncode == 0, result.stdout + result.stderr


def test_cmake_literal_version_kept_by_the_hook_is_committed(repo):
    add_cmake(repo, "project(Demo VERSION 1.0.0 LANGUAGES Fortran)")
    add_hook(
        repo,
        body='sed -i.bak "s/VERSION 1.0.0 /VERSION 1.0.1 /" CMakeLists.txt && rm -f CMakeLists.txt.bak\n'
        "echo README.md; echo CMakeLists.txt",
    )
    result = release(repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "project(Demo VERSION 1.0.1 " in (repo / "CMakeLists.txt").read_text()
    assert "CMakeLists.txt" in git(repo, "show", "--name-only", "--format=", "HEAD").split()


def test_cmake_literal_version_left_stale_by_the_hook_stops_before_the_commit(repo):
    add_cmake(repo, "project(Demo VERSION 1.0.0 LANGUAGES Fortran)")
    add_hook(repo)  # updates README.md only
    head = git(repo, "rev-parse", "HEAD")
    result = release(repo)
    out = result.stdout + result.stderr
    assert result.returncode == 1
    assert "still declares project(... VERSION 1.0.0)" in out and "1.0.1 expected" in out
    assert "FAILED at stage: bumped" in out
    assert git(repo, "rev-parse", "HEAD") == head
