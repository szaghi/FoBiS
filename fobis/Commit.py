"""
Commit.py — LLM-assisted semantic commit-message generation for FoBiS.
"""

# Copyright (C) 2015  Stefano Zaghi
#
# This file is part of FoBiS.py.
#
# FoBiS.py is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# FoBiS.py is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with FoBiS.py. If not, see <http://www.gnu.org/licenses/>.

import json
import re
import subprocess
import sys
import textwrap
import urllib.error
import urllib.request

_SYSTEM_PROMPT = """\
You are an expert at writing Conventional Commits v1.0.0 messages.

## Message format

<type>[(<scope>)][!]: <description>

[body]

[footers]

## Type selection

| Type     | Use when                                    | Changelog section |
|----------|---------------------------------------------|-------------------|
| feat     | A new feature is introduced                 | Added             |
| fix      | A bug is corrected                          | Fixed             |
| perf     | Performance improvement, no API change      | Changed           |
| refactor | Code restructure, no feature or fix         | Changed           |
| docs     | Documentation changes only                  | Changed           |
| style    | Formatting, whitespace (no logic change)    | (omitted)         |
| test     | Test additions or updates only              | (omitted)         |
| chore    | Build, tooling, dependency bumps            | (omitted)         |
| ci       | CI/CD pipeline configuration changes        | (omitted)         |
| build    | Build system or compiler option changes     | (omitted)         |
| revert   | Reverts a previous commit                   | Removed           |

Prefer types that map to changelog sections (feat, fix, perf, revert) when the
change justifies it.

## Rules

Subject line:
  - Max 72 characters, imperative mood, lowercase, no trailing period
  - GOOD: fix(cli): prevent token refresh loop on page reload
  - BAD:  Fixed token bug.

Scope:
  - Infer from the directory or module most affected (e.g. cli, scaffold, fetcher, build)
  - Omit scope only when changes are genuinely cross-cutting
  - GOOD: feat(scaffold): add init-only manifest category
  - BAD:  feat: add init-only manifest category  (scope is obvious from the diff)

Body:
  - Explain the *why*, not the *what* — the diff already shows what changed
  - Separate from subject with a blank line; wrap at 72 chars
  - Include a body whenever the motivation is not self-evident from the subject
  - GOOD body: "Drift detection on project-specific files caused false OUTDATED
                reports on every sync; init-only skips those checks."
  - BAD body:  "Changed the category field to init-only in manifest.ini."

Breaking changes:
  - Append ! after type/scope AND add a BREAKING CHANGE: footer
  - GOOD: feat(api)!: remove legacy -compiler flag
          BREAKING CHANGE: -compiler is replaced by --compiler; update all scripts.

Footers:
  - Each on its own line after a blank line
  - Use BREAKING CHANGE:, Closes #N, Refs #N
  - Keep subject line free of issue numbers — put them in footers

Style matching:
  - Study the recent commit history provided and match its style closely
  - If history uses short single-line messages, do the same for simple changes
  - If history uses bodies for complex changes, follow that pattern

Changelog readiness:
  - Use BREAKING CHANGE: footer (not inline) so git-cliff/release-please detect it
  - Reference issues in footers for traceability

Never add co-authors. Output ONLY the raw commit message — no explanations,
no markdown fences, no "here is your commit message" preamble.
Output EXACTLY ONE commit message and then stop. Do not output multiple messages.

## Examples of well-formed messages

### Example 1

feat(scaffold): add init-only category and auto-discover fpm dependencies

Introduce a third manifest category for project-specific files that
should be seeded once but never overwritten by sync or flagged as
OUTDATED by status. Apply it to fpm.toml and docs/.vitepress/config.mts.

Auto-populate fpm.toml [dependencies] from the fobos [dependencies]
section (tag/rev/branch pins preserved), falling back to .gitmodules
+ git submodule status when no fobos deps are present.

### Example 2

fix(cli): restore tab-completion broken by CliRunner env isolation

CliRunner resets os.environ so the _FOBIS_COMPLETE variable was never
forwarded to the Typer app. Detect both the env-var and the
--install/show-completion flags before calling CliRunner.

### Example 3

ci(scaffold): update ci.yml boilerplate to match FLAP reference\
"""


# ── Git helpers ────────────────────────────────────────────────────────────────


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"git error: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def staged_stat() -> str:
    return _git("diff", "--cached", "--stat")


def staged_diff(max_chars: int) -> str:
    diff = _git("diff", "--cached", "--unified=3")
    if len(diff) > max_chars:
        diff = diff[:max_chars] + f"\n\n[diff truncated — showing first {max_chars} chars]"
    return diff


def current_branch() -> str:
    result = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def recent_commits(n: int = 15) -> str:
    return _git("log", "--oneline", f"-{n}")


def build_prompt(stat: str, diff: str, commits: str, branch: str = "") -> str:
    branch_line = f"- Branch: {branch}\n" if branch else ""
    return (
        f"{branch_line}"
        "## Staged changes (stat)\n\n"
        f"{stat}\n\n"
        "## Staged diff\n\n"
        f"{diff}\n\n"
        "## Recent commits (style reference)\n\n"
        f"{commits}\n\n"
        "Generate the semantic commit message for the staged changes above."
    )


def build_refine_prompt(draft: str, stat: str, diff: str, commits: str) -> str:
    """Build a critique-and-rewrite prompt that feeds the draft back to the model."""
    return (
        "You produced this commit message for the staged diff:\n\n"
        f"{draft}\n\n"
        "## Staged changes (stat)\n\n"
        f"{stat}\n\n"
        "## Staged diff\n\n"
        f"{diff}\n\n"
        "## Recent commits (style reference)\n\n"
        f"{commits}\n\n"
        "Critique the draft against these questions, then rewrite it:\n"
        "1. Does the subject line accurately name the primary change type and scope?\n"
        "2. Does it cover ALL changed files — not just the most obvious one?\n"
        "3. Does the body explain *why* this change was made, not just *what* changed?\n"
        "4. Is there a breaking change that was missed or an issue reference that should be added?\n"
        "5. Is the style consistent with the recent commit history?\n\n"
        "Output ONLY the final improved commit message — no preamble, no critique text, "
        "no markdown fences."
    )


# ── LLM backends ──────────────────────────────────────────────────────────────


def _post_stream(url: str, payload: dict, timeout: int = 120) -> str:
    """POST *payload* as JSON to *url* and collect streamed response tokens."""
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    collected = []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw_line in resp:
                line = raw_line.decode().strip()
                if not line:
                    continue
                # OpenAI SSE: "data: {...}" or "data: [DONE]"
                if line.startswith("data:"):
                    line = line[5:].strip()
                    if line == "[DONE]":
                        break
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Ollama native format
                token = chunk.get("message", {}).get("content", "")
                # OpenAI-compatible format
                if not token:
                    token = (
                        (chunk.get("choices", [{}])[0].get("delta", {}).get("content", ""))
                        if chunk.get("choices")
                        else ""
                    )
                if token:
                    collected.append(token)
                if chunk.get("done"):  # Ollama end-of-stream marker
                    break
    except urllib.error.URLError as exc:
        print(f"\nError: cannot reach LLM at {url}\n{exc}", file=sys.stderr)
        sys.exit(1)
    return "".join(collected).strip()


def ask_ollama(base_url: str, model: str, prompt: str) -> str:
    """Call the Ollama native chat API."""
    url = base_url.rstrip("/") + "/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": True,
    }
    return _post_stream(url, payload)


def ask_openai(base_url: str, model: str, prompt: str) -> str:
    """Call any OpenAI-compatible chat-completions endpoint."""
    url = base_url.rstrip("/") + "/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": True,
    }
    return _post_stream(url, payload)


# ── Message post-processing ────────────────────────────────────────────────────


def _strip_think_tags(text: str) -> str:
    """Remove <think>…</think> blocks some reasoning models emit."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _take_first_message(text: str) -> str:
    """Return only the first commit message when the model repeats itself."""
    # Some models repeat the message separated by "---" lines
    parts = re.split(r"\n---+\n", text)
    return parts[0].strip()


def wrap_message(message: str, width: int = 90) -> str:
    """Wrap each paragraph of a commit message to at most *width* columns."""
    lines = message.splitlines()
    wrapped = []
    for line in lines:
        if len(line) <= width:
            wrapped.append(line)
            continue
        n_indent = len(line) - len(line.lstrip())
        initial_indent = line[:n_indent]
        bullet = re.match(r"^(\s*(?:[-*]|\d+\.)\s+)", line)
        subsequent_indent = " " * len(bullet.group(1)) if bullet else initial_indent
        wrapped.append(
            textwrap.fill(
                line,
                width=width,
                initial_indent=initial_indent,
                subsequent_indent=subsequent_indent,
                break_long_words=False,
                break_on_hyphens=False,
            )
        )
    return "\n".join(wrapped)


# ── Public entry point ─────────────────────────────────────────────────────────


def generate(
    backend: str,
    url: str,
    model: str,
    max_diff_chars: int,
    refine_passes: int = 0,
    print_n=print,
    print_w=print,
) -> str:
    """
    Generate a Conventional Commits message for the currently staged changes.

    Parameters
    ----------
    backend : str
        "ollama" or "openai"
    url : str
        Base URL of the LLM server.
    model : str
        Model identifier.
    max_diff_chars : int
        Maximum diff characters to include in the prompt.
    refine_passes : int
        Number of critique-and-rewrite iterations after the initial draft.
        0 = single pass (default). 1–3 recommended for small models.
    print_n, print_w : callable
        Normal / warning message printers.

    Returns
    -------
    str
        The generated commit message, ready to use.
    """
    stat = staged_stat()
    if not stat:
        print_w("Nothing staged. Run `git add <files>` first.")
        sys.exit(1)

    diff = staged_diff(max_diff_chars)
    commits = recent_commits()
    branch = current_branch()

    def _ask(prompt: str) -> str:
        if backend == "openai":
            return ask_openai(url, model, prompt)
        return ask_ollama(url, model, prompt)

    print_n(f"[{backend}:{model}] Generating commit message…")
    prompt = build_prompt(stat, diff, commits, branch=branch)
    raw = _ask(prompt)
    draft = wrap_message(_take_first_message(_strip_think_tags(raw)))

    for i in range(refine_passes):
        print_n(f"[{backend}:{model}] Refining… (pass {i + 1}/{refine_passes})")
        refine_prompt = build_refine_prompt(draft, stat, diff, commits)
        raw = _ask(refine_prompt)
        draft = wrap_message(_take_first_message(_strip_think_tags(raw)))

    return draft
