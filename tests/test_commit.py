"""Tests for Commit.py — LLM-assisted commit-message generation."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

import fobis.Commit as Commit
from fobis.llm import FakeProvider, LLMError

# ── Pure utility functions ─────────────────────────────────────────────────────


def test_strip_think_tags_removes_single_block():
    assert Commit._strip_think_tags("<think>reasoning</think>feat(cli): add x") == "feat(cli): add x"


def test_strip_think_tags_multiline_block():
    text = "<think>\nline1\nline2\n</think>fix: bug"
    assert Commit._strip_think_tags(text) == "fix: bug"


def test_strip_think_tags_no_tags():
    text = "feat: simple"
    assert Commit._strip_think_tags(text) == text


def test_strip_markdown_fences_full_block():
    text = "```\nfeat: subject\n\nbody\n```"
    assert Commit._strip_markdown_fences(text) == "feat: subject\n\nbody"


def test_strip_markdown_fences_with_lang():
    text = "```text\nfeat: subject\n\nbody\n```"
    assert Commit._strip_markdown_fences(text) == "feat: subject\n\nbody"


def test_strip_markdown_fences_trailing_only():
    text = "feat: subject\n\nbody\n```"
    assert Commit._strip_markdown_fences(text) == "feat: subject\n\nbody"


def test_strip_markdown_fences_leading_only():
    text = "```\nfeat: subject\n\nbody"
    assert Commit._strip_markdown_fences(text) == "feat: subject\n\nbody"


def test_strip_markdown_fences_none():
    text = "feat: clean\n\nbody"
    assert Commit._strip_markdown_fences(text) == text


def test_strip_file_manifest_files_removed_section():
    text = (
        "refactor: clean\n\n"
        "Body prose explaining the change.\n\n"
        "Files removed:\n"
        "- foo.vim (57 lines)\n"
        "- bar.vim (105 lines)\n"
    )
    result = Commit._strip_file_manifest(text)
    assert "Files removed" not in result
    assert "foo.vim" not in result
    assert "Body prose explaining the change." in result


def test_strip_file_manifest_changes_include_bullets():
    text = (
        "refactor: clean\n\n"
        "Body prose.\n\n"
        "The changes include:\n"
        "- Removal of 13 legacy files\n"
        "- Addition of new filetypes\n"
    )
    result = Commit._strip_file_manifest(text)
    assert "The changes include" not in result
    assert "Removal of 13" not in result
    assert "Body prose." in result


def test_strip_file_manifest_multiple_sections():
    text = (
        "refactor: clean\n\n"
        "Prose.\n\n"
        "Files removed:\n- a.vim\n- b.vim\n\n"
        "Files added:\n- c.vim\n\n"
        "Files modified:\n- d.vim\n"
    )
    result = Commit._strip_file_manifest(text)
    assert "Files removed" not in result
    assert "Files added" not in result
    assert "Files modified" not in result
    assert "a.vim" not in result
    assert "c.vim" not in result
    assert "Prose." in result


def test_strip_file_manifest_preserves_non_manifest_bullets():
    """Bullets NOT preceded by a manifest header must be preserved."""
    text = "refactor: clean\n\nThe change does three things:\n- fixes a bug\n- renames a function\n- updates docs\n"
    result = Commit._strip_file_manifest(text)
    assert "fixes a bug" in result
    assert "renames a function" in result


def test_strip_file_manifest_no_bullets_no_strip():
    """A 'Files removed:' header with prose (not bullets) is not a manifest."""
    text = "refactor: clean\n\nFiles removed: specifically the dead colorschemes.\n"
    result = Commit._strip_file_manifest(text)
    assert "Files removed: specifically" in result


def test_strip_file_manifest_warns():
    warnings = []
    text = "refactor: x\n\nProse.\n\nFiles removed:\n- a\n- b\n"
    Commit._strip_file_manifest(text, print_w=warnings.append)
    assert len(warnings) == 1
    assert "manifest" in warnings[0]


def test_strip_file_manifest_no_warn_when_absent():
    warnings = []
    Commit._strip_file_manifest("refactor: x\n\nClean body.\n", print_w=warnings.append)
    assert warnings == []


def test_take_first_message_single():
    assert Commit._take_first_message("feat: first") == "feat: first"


def test_take_first_message_multiple_separators():
    text = "feat: first\n---\nfeat: second\n---\nfeat: third"
    assert Commit._take_first_message(text) == "feat: first"


def test_wrap_message_short_lines_unchanged():
    msg = "feat(scope): short subject\n\nShort body."
    assert Commit.wrap_message(msg) == msg


def test_wrap_message_long_body_line_wrapped():
    long_body = "word " * 25  # 125 chars
    msg = "feat(scope): subject\n\n" + long_body.strip()
    result = Commit.wrap_message(msg, width=72)
    # Subject line stays; body lines are wrapped.
    body_lines = result.splitlines()[2:]
    for line in body_lines:
        assert len(line) <= 72


def test_wrap_message_preserves_long_subject():
    """Subject line must never be wrapped — git tooling assumes single-line subjects."""
    long_subject = "feat(scope): " + "word " * 20  # well over 72
    msg = long_subject + "\n\nBody."
    result = Commit.wrap_message(msg, width=72)
    assert result.splitlines()[0] == long_subject


def test_wrap_message_warns_on_overlong_subject():
    warnings = []
    long_subject = "feat(scope): " + "x" * 80  # > 72
    Commit.wrap_message(long_subject + "\n\nBody.", print_w=warnings.append)
    assert len(warnings) == 1
    assert "subject line" in warnings[0]
    assert str(len(long_subject)) in warnings[0]


def test_wrap_message_no_warning_on_short_subject():
    warnings = []
    Commit.wrap_message("feat: short\n\nBody.", print_w=warnings.append)
    assert warnings == []


def test_wrap_message_bullet_indent():
    msg = "feat: subject\n\n- " + "word " * 20
    result = Commit.wrap_message(msg, width=40)
    body_lines = result.splitlines()[2:]
    assert len(body_lines) > 1
    assert body_lines[1].startswith("  ")  # subsequent indent aligns with bullet body


def test_build_prompt_includes_branch():
    result = Commit.build_prompt("stat", "diff", "commits", branch="main")
    assert "Branch: main" in result
    assert "stat" in result
    assert "diff" in result
    assert "commits" in result


def test_build_prompt_no_branch():
    result = Commit.build_prompt("stat", "diff", "commits", branch="")
    assert "Branch:" not in result
    assert "stat" in result


def test_build_prompt_includes_complete_file_list():
    files = "M\tfobis/Commit.py\nA\ttests/test_commit.py"
    result = Commit.build_prompt("stat", "diff", "commits", files=files)
    assert "Complete file list" in result
    assert "fobis/Commit.py" in result
    assert "tests/test_commit.py" in result


def test_build_prompt_no_files_omits_section():
    result = Commit.build_prompt("stat", "diff", "commits", files="")
    assert "Complete file list" not in result


def test_build_refine_prompt_contains_draft_and_critique():
    result = Commit.build_refine_prompt("draft msg", "stat", "diff", "commits")
    assert "draft msg" in result
    assert "Critique" in result
    assert "stat" in result


def test_build_refine_prompt_includes_complete_file_list():
    files = "M\tfobis/Commit.py\nA\ttests/new_test.py"
    result = Commit.build_refine_prompt("draft", "stat", "diff", "commits", files=files)
    assert "Complete file list" in result
    assert "fobis/Commit.py" in result
    assert "new_test.py" in result


# ── git helper functions ──────────────────────────────────────────────────────


def _proc(returncode=0, stdout="", stderr=""):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


def test_git_helper_raises_on_nonzero():
    with patch("subprocess.run", return_value=_proc(returncode=1, stderr="fatal")), pytest.raises(Commit.GitError):
        Commit._git("status")


def test_staged_stat_returns_stripped_output():
    with patch("subprocess.run", return_value=_proc(stdout=" 1 file changed\n")):
        assert Commit.staged_stat() == "1 file changed"


def test_staged_files_returns_name_status():
    with patch("subprocess.run", return_value=_proc(stdout="M\tfobis/Commit.py\nA\ttests/test_commit.py\n")):
        result = Commit.staged_files()
    assert "fobis/Commit.py" in result
    assert "tests/test_commit.py" in result


def test_staged_diff_no_truncation():
    with patch("subprocess.run", return_value=_proc(stdout="diff content")):
        assert Commit.staged_diff(1000) == "diff content"


_FAKE_DIFF_A = """\
diff --git a/foo.py b/foo.py
index abc..def 100644
--- a/foo.py
+++ b/foo.py
@@ -1,3 +1,4 @@
 line1
+line2
 line3
"""

_FAKE_DIFF_B = """\
diff --git a/bar.py b/bar.py
index 111..222 100644
--- a/bar.py
+++ b/bar.py
@@ -1,2 +1,3 @@
 old
+new
 end
"""


def test_staged_diff_fits_entirely():
    full = _FAKE_DIFF_A + _FAKE_DIFF_B
    with patch("subprocess.run", return_value=_proc(stdout=full)):
        result = Commit.staged_diff(100_000)
    # _git() strips trailing whitespace; compare against the stripped canonical form
    assert result == full.strip()


def test_staged_diff_smart_truncation_shows_header():
    """When a file's diff is too large, its metadata header is preserved."""
    big_hunk = "@@ -1,100 +1,100 @@\n" + ("+" + "x" * 70 + "\n") * 50
    big_diff = "diff --git a/big.py b/big.py\nindex aaa..bbb 100644\n--- a/big.py\n+++ b/big.py\n" + big_hunk
    with patch("subprocess.run", return_value=_proc(stdout=big_diff)):
        # Budget too small for the full diff but large enough for the header
        result = Commit.staged_diff(200)
    assert "diff --git a/big.py" in result
    assert "not shown" in result


def test_staged_diff_fully_omitted_files_listed():
    """Files that don't even fit their header go into the 'not shown at all' note."""
    big_diff = (
        "diff --git a/huge.py b/huge.py\n"
        "index aaa..bbb 100644\n"
        "--- a/huge.py\n"
        "+++ b/huge.py\n"
        "@@ -1,500 +1,500 @@\n" + ("+" + "x" * 70 + "\n") * 200
    )
    with patch("subprocess.run", return_value=_proc(stdout=big_diff)):
        result = Commit.staged_diff(10)  # impossibly small budget
    assert "huge.py" in result
    assert "not shown at all" in result


def test_current_branch_success():
    with patch("subprocess.run", return_value=_proc(returncode=0, stdout="main\n")):
        assert Commit.current_branch() == "main"


def test_current_branch_failure_returns_empty():
    with patch("subprocess.run", return_value=_proc(returncode=1)):
        assert Commit.current_branch() == ""


def test_recent_commits():
    with patch("subprocess.run", return_value=_proc(stdout="abc123 feat: foo\n")):
        result = Commit.recent_commits()
    assert "feat: foo" in result


def test_recent_commits_empty_on_unborn_branch():
    with patch("subprocess.run", return_value=_proc(returncode=1)) as mock_run:
        assert Commit.recent_commits() == ""
    assert mock_run.call_count == 1  # git log is never attempted


# ── generate() ────────────────────────────────────────────────────────────────


_STAGED_FILES = "M\tfobis/Commit.py\nA\ttests/test_commit.py"


@pytest.fixture
def staged():
    """Patch the git helpers with a fixed staged change."""
    with (
        patch("fobis.Commit.staged_stat", return_value="1 file"),
        patch("fobis.Commit.staged_files", return_value=_STAGED_FILES),
        patch("fobis.Commit.staged_diff", return_value="diff"),
        patch("fobis.Commit.recent_commits", return_value="abc feat: prior"),
        patch("fobis.Commit.current_branch", return_value="main"),
    ):
        yield


def test_generate_nothing_staged_raises():
    with patch("fobis.Commit.staged_stat", return_value=""), pytest.raises(Commit.NothingStagedError):
        Commit.generate(FakeProvider([]), 1000)


def test_generate_single_pass(staged):
    provider = FakeProvider(["feat(cli): new feature"])
    result = Commit.generate(provider, 1000)
    assert result == "feat(cli): new feature"
    assert len(provider.calls) == 1


def test_generate_sends_commit_system_prompt_then_user_prompt(staged):
    provider = FakeProvider(["feat: x"])
    Commit.generate(provider, 1000)
    sent = provider.calls[0].messages
    assert [m["role"] for m in sent] == ["system", "user"]
    assert sent[0]["content"] == Commit._SYSTEM_PROMPT + Commit._STRUCTURED_NOTE
    assert provider.calls[0].schema == Commit.COMMIT_SCHEMA
    Commit.generate(provider := FakeProvider(["feat: x"]), 1000, structured=False)
    assert provider.calls[0].messages[0]["content"] == Commit._SYSTEM_PROMPT and provider.calls[0].schema is None


def _answer(**fields) -> str:
    data = {"type": "fix", "scope": "", "breaking": False, "description": "x", "body": "", "footers": []}
    data.update(fields)
    return json.dumps(data)


def test_render_message_builds_the_header():
    render = Commit.render_message
    assert render(json.loads(_answer(scope="fetcher", description="handle a missing deps dir."))) == (
        "fix(fetcher): handle a missing deps dir"
    )
    full = json.loads(
        _answer(
            type="feat",
            scope="fobis/Fetcher.py",  # a file given as scope: the component name is kept
            breaking=True,
            description="Fix(cli): Drop the -compiler flag",
            body="Replaced by --compiler.",
            footers=["BREAKING CHANGE: use --compiler", "Co-authored-by: bot <b@b>"],
        )
    )
    assert render(full) == (
        "feat(fetcher)!: drop the -compiler flag\n\nReplaced by --compiler.\n\nBREAKING CHANGE: use --compiler"
    )
    assert render(json.loads(_answer(description="API keys from env"))) == "fix: API keys from env"
    assert render(json.loads(_answer(footers=["BREAKING CHANGE: y"]))).startswith("fix!: x")
    for bad in ({"type": "wip", "description": "x"}, {"type": "fix", "description": ""}):
        with pytest.raises(ValueError):
            render(bad)


def test_generate_structured_answer_is_rendered(staged):
    provider = FakeProvider(
        ["```json\n" + _answer(scope="cli", description="restore completion", body="Why.") + "\n```"]
    )
    assert Commit.generate(provider, 1000) == "fix(cli): restore completion\n\nWhy."


def test_generate_falls_back_when_the_schema_is_rejected(staged):
    from fobis.llm import ProviderResponseError

    calls = []

    def reply(messages):
        calls.append(messages)
        if len(calls) == 1:
            raise ProviderResponseError("response_format not supported", status=400)
        return "feat(cli): plain text answer"

    warnings = []
    assert Commit.generate(FakeProvider(reply), 1000, print_w=warnings.append) == "feat(cli): plain text answer"
    assert "rejected structured output (HTTP 400)" in warnings[0]
    assert calls[1][0]["content"] == Commit._SYSTEM_PROMPT  # second request: free text


def test_generate_other_provider_errors_are_not_swallowed(staged):
    from fobis.llm import ProviderResponseError

    def reply(messages):
        raise ProviderResponseError("server error", status=500)

    with pytest.raises(ProviderResponseError):
        Commit.generate(FakeProvider(reply), 1000)


def test_generate_strips_think_tags_from_response(staged):
    provider = FakeProvider(["<think>lengthy reasoning</think>feat(scope): clean subject"])
    result = Commit.generate(provider, 1000)
    assert "<think>" not in result
    assert result == "feat(scope): clean subject"


def test_generate_refine_passes_calls_provider_n_plus_one_times(staged):
    provider = FakeProvider(["feat: initial draft", "feat(cli): refined version"])
    result = Commit.generate(provider, 1000, refine_passes=1)
    assert result == "feat(cli): refined version"
    assert len(provider.calls) == 2


def test_generate_propagates_provider_errors(staged):
    with pytest.raises(LLMError):
        Commit.generate(FakeProvider([]), 1000)


def test_generate_file_list_threaded_into_prompt():
    """The complete file list must appear in the prompt sent to the LLM."""
    provider = FakeProvider(["feat: ok"])
    with (
        patch("fobis.Commit.staged_stat", return_value="2 files"),
        patch("fobis.Commit.staged_files", return_value="M\tfobis/Builder.py\nA\ttests/new.py"),
        patch("fobis.Commit.staged_diff", return_value="diff"),
        patch("fobis.Commit.recent_commits", return_value="abc"),
        patch("fobis.Commit.current_branch", return_value="main"),
    ):
        Commit.generate(provider, 1000)

    assert len(provider.calls) == 1
    prompt = provider.calls[0].messages[-1]["content"]
    assert "fobis/Builder.py" in prompt
    assert "tests/new.py" in prompt


def test_generate_file_list_threaded_into_refine_prompt():
    """The complete file list must appear in the refine prompt too."""
    provider = FakeProvider(["feat: ok", "feat: ok"])
    with (
        patch("fobis.Commit.staged_stat", return_value="2 files"),
        patch("fobis.Commit.staged_files", return_value="M\tfobis/Commit.py\nA\ttests/x.py"),
        patch("fobis.Commit.staged_diff", return_value="diff"),
        patch("fobis.Commit.recent_commits", return_value="abc"),
        patch("fobis.Commit.current_branch", return_value="main"),
    ):
        Commit.generate(provider, 1000, refine_passes=1)

    assert len(provider.calls) == 2
    # Both the initial and refine prompts must carry the file list
    for call in provider.calls:
        prompt = call.messages[-1]["content"]
        assert "fobis/Commit.py" in prompt
        assert "tests/x.py" in prompt
