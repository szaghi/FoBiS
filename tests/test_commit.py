"""Tests for Commit.py — LLM-assisted commit-message generation."""

from __future__ import annotations

import urllib.error
from unittest.mock import MagicMock, patch

import pytest

import fobis.Commit as Commit

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
    text = (
        "refactor: clean\n\n"
        "The change does three things:\n"
        "- fixes a bug\n"
        "- renames a function\n"
        "- updates docs\n"
    )
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


# ── _post_stream ───────────────────────────────────────────────────────────────


def _urlopen_mock(lines: list[bytes]) -> MagicMock:
    ctx = MagicMock()
    ctx.__enter__.return_value = lines
    ctx.__exit__.return_value = False
    return ctx


def test_post_stream_ollama_format():
    lines = [
        b'{"message": {"content": "feat"}, "done": false}\n',
        b'{"message": {"content": "(cli)"}, "done": true}\n',
    ]
    with patch("urllib.request.urlopen", return_value=_urlopen_mock(lines)):
        result = Commit._post_stream("http://localhost", {})
    assert result == "feat(cli)"


def test_post_stream_openai_sse_format():
    lines = [
        b'data: {"choices": [{"delta": {"content": "fix"}}]}\n',
        b'data: {"choices": [{"delta": {"content": ": bug"}}]}\n',
        b"data: [DONE]\n",
    ]
    with patch("urllib.request.urlopen", return_value=_urlopen_mock(lines)):
        result = Commit._post_stream("http://localhost", {})
    assert result == "fix: bug"


def test_post_stream_skips_blank_lines():
    lines = [b"\n", b"   \n", b'{"message": {"content": "ok"}, "done": true}\n']
    with patch("urllib.request.urlopen", return_value=_urlopen_mock(lines)):
        result = Commit._post_stream("http://localhost", {})
    assert result == "ok"


def test_post_stream_skips_invalid_json():
    lines = [b"not-json\n", b'{"message": {"content": "ok"}, "done": true}\n']
    with patch("urllib.request.urlopen", return_value=_urlopen_mock(lines)):
        result = Commit._post_stream("http://localhost", {})
    assert result == "ok"


def test_post_stream_url_error_exits():
    ctx = MagicMock()
    ctx.__enter__.side_effect = urllib.error.URLError("connection refused")
    ctx.__exit__.return_value = False
    with patch("urllib.request.urlopen", return_value=ctx), pytest.raises(SystemExit):
        Commit._post_stream("http://localhost", {})


# ── ask_ollama / ask_openai ────────────────────────────────────────────────────


def test_ask_ollama_builds_correct_url_and_payload():
    with patch("fobis.Commit._post_stream", return_value="feat: x") as mock_post:
        result = Commit.ask_ollama("http://localhost:11434", "mymodel", "prompt")
    assert result == "feat: x"
    url, payload = mock_post.call_args[0]
    assert url == "http://localhost:11434/api/chat"
    assert payload["model"] == "mymodel"
    assert payload["stream"] is True
    assert any(m["content"] == Commit._SYSTEM_PROMPT for m in payload["messages"])


def test_ask_ollama_strips_trailing_slash():
    with patch("fobis.Commit._post_stream", return_value="ok") as mock_post:
        Commit.ask_ollama("http://localhost:11434/", "m", "p")
    url, _ = mock_post.call_args[0]
    assert url == "http://localhost:11434/api/chat"


def test_ask_openai_builds_correct_url_and_payload():
    with patch("fobis.Commit._post_stream", return_value="fix: y") as mock_post:
        result = Commit.ask_openai("http://localhost:1234/", "gpt4", "prompt")
    assert result == "fix: y"
    url, payload = mock_post.call_args[0]
    assert url == "http://localhost:1234/v1/chat/completions"
    assert payload["model"] == "gpt4"
    assert payload["stream"] is True


# ── git helper functions ──────────────────────────────────────────────────────


def _proc(returncode=0, stdout="", stderr=""):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


def test_git_helper_exits_on_nonzero():
    with patch("subprocess.run", return_value=_proc(returncode=1, stderr="fatal")), pytest.raises(SystemExit):
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


# ── generate() ────────────────────────────────────────────────────────────────


_STAGED_FILES = "M\tfobis/Commit.py\nA\ttests/test_commit.py"


def test_generate_nothing_staged_exits():
    with patch("fobis.Commit.staged_stat", return_value=""), pytest.raises(SystemExit):
        Commit.generate("ollama", "http://localhost", "model", 1000)


def test_generate_ollama_single_pass():
    with (
        patch("fobis.Commit.staged_stat", return_value="1 file"),
        patch("fobis.Commit.staged_files", return_value=_STAGED_FILES),
        patch("fobis.Commit.staged_diff", return_value="diff"),
        patch("fobis.Commit.recent_commits", return_value="abc feat: prior"),
        patch("fobis.Commit.current_branch", return_value="main"),
        patch("fobis.Commit.ask_ollama", return_value="feat(cli): new feature") as mock_ask,
    ):
        result = Commit.generate("ollama", "http://localhost", "mymodel", 1000)
    assert result == "feat(cli): new feature"
    assert mock_ask.call_count == 1


def test_generate_openai_single_pass():
    with (
        patch("fobis.Commit.staged_stat", return_value="1 file"),
        patch("fobis.Commit.staged_files", return_value=_STAGED_FILES),
        patch("fobis.Commit.staged_diff", return_value="diff"),
        patch("fobis.Commit.recent_commits", return_value="abc fix: prior"),
        patch("fobis.Commit.current_branch", return_value="feature"),
        patch("fobis.Commit.ask_openai", return_value="fix(api): resolve timeout") as mock_ask,
    ):
        result = Commit.generate("openai", "http://localhost", "gpt4", 1000)
    assert result == "fix(api): resolve timeout"
    assert mock_ask.call_count == 1


def test_generate_strips_think_tags_from_response():
    raw = "<think>lengthy reasoning</think>feat(scope): clean subject"
    with (
        patch("fobis.Commit.staged_stat", return_value="1 file"),
        patch("fobis.Commit.staged_files", return_value=_STAGED_FILES),
        patch("fobis.Commit.staged_diff", return_value="diff"),
        patch("fobis.Commit.recent_commits", return_value="abc"),
        patch("fobis.Commit.current_branch", return_value="main"),
        patch("fobis.Commit.ask_ollama", return_value=raw),
    ):
        result = Commit.generate("ollama", "http://localhost", "model", 1000)
    assert "<think>" not in result
    assert result == "feat(scope): clean subject"


def test_generate_refine_passes_calls_ask_n_plus_one_times():
    responses = iter(["feat: initial draft", "feat(cli): refined version"])

    with (
        patch("fobis.Commit.staged_stat", return_value="1 file"),
        patch("fobis.Commit.staged_files", return_value=_STAGED_FILES),
        patch("fobis.Commit.staged_diff", return_value="diff"),
        patch("fobis.Commit.recent_commits", return_value="abc"),
        patch("fobis.Commit.current_branch", return_value="main"),
        patch("fobis.Commit.ask_ollama", side_effect=responses),
    ):
        result = Commit.generate("ollama", "http://localhost", "model", 1000, refine_passes=1)
    assert result == "feat(cli): refined version"


def test_generate_file_list_threaded_into_prompt():
    """The complete file list must appear in the prompt sent to the LLM."""
    captured_prompt: list[str] = []

    def capture_ask(url, model, prompt):
        captured_prompt.append(prompt)
        return "feat: ok"

    with (
        patch("fobis.Commit.staged_stat", return_value="2 files"),
        patch("fobis.Commit.staged_files", return_value="M\tfobis/Builder.py\nA\ttests/new.py"),
        patch("fobis.Commit.staged_diff", return_value="diff"),
        patch("fobis.Commit.recent_commits", return_value="abc"),
        patch("fobis.Commit.current_branch", return_value="main"),
        patch("fobis.Commit.ask_ollama", side_effect=capture_ask),
    ):
        Commit.generate("ollama", "http://localhost", "model", 1000)

    assert len(captured_prompt) == 1
    assert "fobis/Builder.py" in captured_prompt[0]
    assert "tests/new.py" in captured_prompt[0]


def test_generate_file_list_threaded_into_refine_prompt():
    """The complete file list must appear in the refine prompt too."""
    captured_prompts: list[str] = []

    def capture_ask(url, model, prompt):
        captured_prompts.append(prompt)
        return "feat: ok"

    with (
        patch("fobis.Commit.staged_stat", return_value="2 files"),
        patch("fobis.Commit.staged_files", return_value="M\tfobis/Commit.py\nA\ttests/x.py"),
        patch("fobis.Commit.staged_diff", return_value="diff"),
        patch("fobis.Commit.recent_commits", return_value="abc"),
        patch("fobis.Commit.current_branch", return_value="main"),
        patch("fobis.Commit.ask_ollama", side_effect=capture_ask),
    ):
        Commit.generate("ollama", "http://localhost", "model", 1000, refine_passes=1)

    assert len(captured_prompts) == 2
    # Both the initial and refine prompts must carry the file list
    for p in captured_prompts:
        assert "fobis/Commit.py" in p
        assert "tests/x.py" in p
