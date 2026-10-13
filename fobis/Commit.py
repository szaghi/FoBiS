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

from __future__ import annotations

import json
import re
import subprocess
import textwrap
from typing import TYPE_CHECKING

from .llm.errors import ProviderResponseError
from .llm.provider import bounded, messages

if TYPE_CHECKING:
    from .llm.provider import Provider


class CommitError(Exception):
    """Base class of the errors raised while generating a commit message."""


class GitError(CommitError):
    """A git command failed."""


class NothingStagedError(CommitError):
    """There are no staged changes to describe."""


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

Type disambiguation — common mistakes:
  - 'docs' applies ONLY to files that are never executed: .md, .rst, docstrings,
    comments. String literals inside .py/.f90/etc. files that drive runtime
    behavior (prompts, templates, error messages, format strings) are NOT docs —
    use fix, feat, or refactor depending on intent.
  - Changes that correct wrong observable behavior → fix, even if they only edit
    text or configuration values.
  - 'revert' applies ONLY when the commit undoes a *specific prior commit* (e.g.
    `git revert <sha>`). Large deletions of legacy / dead / stale code are NOT
    reverts — they are refactor (if the intent is restructuring) or chore (if
    tooling / cleanup). A diff with many deletions is almost always refactor,
    not revert.

## Rules

Subject line:
  - Max 72 characters, imperative mood, lowercase, no trailing period
  - GOOD: fix(cli): prevent token refresh loop on page reload
  - BAD:  Fixed token bug.

Scope:
  - Infer from the directory or module most affected (e.g. cli, scaffold, fetcher, build)
  - Omit scope only when changes are genuinely cross-cutting
  - Scope is a COMPONENT NAME, never a filename — strip the path and extension.
  - GOOD: feat(scaffold): add init-only manifest category   ← component name
  - BAD:  feat(Scaffolder.py): ...                          ← filename, never do this
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

Style matching (formatting only — never content):
  - Use the recent commit history EXCLUSIVELY to match formatting style:
    length, punctuation, use of scope, use of body, tone.
  - NEVER infer what changed from commit history.
  - ALL content (type, scope, description, body) must be derived solely from the
    staged diff and stat. Commit history is a style ruler, not a content source.

Changelog readiness:
  - Use BREAKING CHANGE: footer (not inline) so git-cliff/release-please detect it
  - Reference issues in footers for traceability

All-files coverage (critical — violations are the most common mistake):
  - The stat section lists EVERY staged file. Your message MUST account for all of them.
  - Never write a message that focuses on one file and silently omits the others.
  - When the diff is truncated, the stat and the "[files not shown]" note tell you what
    was cut. Infer the purpose of those files from their names and sizes, then describe
    them — do not pretend they do not exist.
  - If several files belong to the same logical change, group them under one type/scope.
    If they represent genuinely separate concerns, prefer a scope that covers the whole
    (e.g. "tests") over one that names only a single module.

Never add co-authors. Output ONLY the raw commit message — no explanations,
no markdown fences, no "here is your commit message" preamble.
Output EXACTLY ONE commit message and then stop. Do not output multiple messages.

Forbidden: file manifests in the body (in ANY format).
  - NEVER reproduce the git stat as a list of files in the body. `git show --stat`
    already displays this; duplicating it is pure noise.
  - This ban covers EVERY format the model might try:
      * Section headers like "Files removed:" / "Files added:" / "Files modified:"
      * Generic intro headers like "The changes include:" / "Summary of changes:"
        followed by a file / operation enumeration
      * Bullet lists where each bullet is a file path or "Removal of foo.vim"
      * Numbered lists of files / change operations
      * Tables of files with line counts
    If your body contains an enumeration of more than two files OR of
    per-file operations, you are writing a manifest. Delete it.
  - "Accounting for every file" means the body's *reasons* cover the logical groups
    represented, not that filenames are enumerated. A single sentence like
    "remove the six unused colorschemes" accounts for all six without listing them.
  - Name a specific file only when it is load-bearing for the *why* (e.g. "remove
    plug.vim.old — stale vim-plug backup"). One or two named files is fine; a list
    is not.
  - BAD body ending:
      The changes include:
      - Removal of 13 legacy color scheme files
      - Addition of new ftdetect files
      - Updates to vimrc
  - GOOD body: prose that names the *reasons* the files were removed, grouped by
    motivation, with filenames only where they clarify the reason.

Forbidden: hallucinated BREAKING CHANGE footers.
  - Emit a BREAKING CHANGE footer ONLY when the diff removes or changes the
    signature of a published API: a CLI flag, a public function signature, a
    config file schema consumed by third parties, an exported module member, a
    database migration, a network protocol. The trigger is "downstream code
    that previously worked now fails."
  - Personal dotfiles, internal scripts, vendored config files, test helpers,
    and build scaffolding do NOT have downstream consumers and cannot produce
    breaking changes. A vim config rewrite is not breaking — there is no API.
  - NEVER emit "users will need to update" as the reason for a BREAKING CHANGE
    unless you can name the specific API and the specific downstream behavior
    that now fails. Vague "users may need to adapt" is a hallucination — drop it.
  - When in doubt, omit the footer. A missing BREAKING CHANGE on a truly
    breaking commit can be added later; a fabricated one poisons changelogs.

Forbidden: generic padding.
  - NEVER end the body with sentences like "this simplifies the configuration",
    "this streamlines the codebase", "this improves maintainability", or similar
    generic closers that could describe any refactor in any project. They add
    length without information.
  - If you cannot state a *specific* why, the body is too short — go back to the
    diff and find concrete reasons.

Diff-forensics checklist (read the diff like a reviewer, not a summarizer):
  - Before writing the body, scan the diff for at least one of:
      (a) dead code being removed (unreferenced functions, commented-out plugins,
          stale vendored files),
      (b) a duplicate or overwritten definition that was silently clobbering
          earlier lines,
      (c) a setting leaking beyond its intended scope (e.g. `set` at file level
          that should have been `setlocal` in ftplugin),
      (d) a band-aid being replaced with a proper fix (e.g. a timeout knob removed
          in favor of addressing the root cause),
      (e) a renamed or relocated file where the new location matches an idiomatic
          pattern the old one didn't (e.g. ftplugin/, ftdetect/, plugins/).
  - If you find any, name it concretely in the body — that is the *why*. These
    observations are the difference between a summary and a review.

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

ci(scaffold): update ci.yml boilerplate to match FLAP reference

### Example 4 — string-literal edits that fix runtime behavior (NOT docs)

fix(commit): prevent model from anchoring on git log instead of staged diff

The LLM was producing commit messages that echoed recent commit history
rather than describing the actual change. Root cause: the prompt labelled
the history section as a plain "style reference" without explicitly
forbidding content inference, and 15 entries gave the model enough
thematic signal to anchor on.

Tighten the system-prompt rule to name the failure mode explicitly,
add an IMPORTANT footer to the user prompt reinforcing the constraint,
and drop the history window from 15 to 5 entries.

(Note: only string literals and a default-argument value changed in the
diff — this is still a fix, not docs, because those strings are LLM
prompts that directly control runtime model output.)

### Example 5 — scope is a component name, never a filename

fix(fetcher): handle missing .fobis_deps directory on first fetch

Without an existing deps directory the path-existence check raised
FileNotFoundError before the clone could proceed.

(Note: the changed file was fobis/Fetcher.py — scope is "fetcher",
the component name, not "Fetcher.py".)\
"""


# ── Git helpers ────────────────────────────────────────────────────────────────


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def staged_stat() -> str:
    return _git("diff", "--no-color", "--cached", "--stat")


def staged_files() -> str:
    """Return a complete list of all staged files with their status (A/M/D/R)."""
    return _git("diff", "--no-color", "--cached", "--name-status")


def staged_diff(max_chars: int) -> str:
    """Return the staged unified diff, truncated at file boundaries when needed.

    When the full diff exceeds *max_chars*, each file's metadata header is
    preserved so the model can see every changed file, even if its hunks are
    omitted.  Files for which not even the header fits are listed explicitly at
    the end.
    """
    diff = _git("diff", "--no-color", "--cached", "--unified=3")
    if len(diff) <= max_chars:
        return diff

    # Locate the start position of every per-file section.
    boundaries = [m.start() for m in re.finditer(r"^diff --git ", diff, re.MULTILINE)]
    boundaries.append(len(diff))  # sentinel

    parts: list[str] = []
    budget = max_chars
    fully_omitted: list[str] = []

    for i in range(len(boundaries) - 1):
        chunk = diff[boundaries[i] : boundaries[i + 1]]
        fname_match = re.match(r"diff --git a/\S+ b/(\S+)", chunk)
        fname = fname_match.group(1) if fname_match else "?"

        if len(chunk) <= budget:
            parts.append(chunk)
            budget -= len(chunk)
        else:
            # Always show the metadata header (everything before the first hunk).
            hunk = re.search(r"^@@", chunk, re.MULTILINE)
            header_end = hunk.start() if hunk else len(chunk)
            header = chunk[:header_end]
            if budget >= len(header) + 40:
                omitted = len(chunk) - len(header)
                parts.append(header + f"@@ [+{omitted} chars not shown] @@\n")
                budget -= len(header) + 40
            else:
                fully_omitted.append(fname)

    if fully_omitted:
        parts.append(f"\n[{len(fully_omitted)} file(s) not shown at all: {', '.join(fully_omitted)}]\n")

    return "".join(parts)


def current_branch() -> str:
    result = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def recent_commits(n: int = 5) -> str:
    """The last *n* commits, one per line; empty on an unborn branch (the repository's first commit)."""
    head = subprocess.run(["git", "rev-parse", "--verify", "--quiet", "HEAD"], capture_output=True, text=True)
    if head.returncode != 0:
        return ""
    return _git("log", "--no-color", "--oneline", f"-{n}")


def build_prompt(stat: str, diff: str, commits: str, branch: str = "", files: str = "", facts: str = "") -> str:
    branch_line = f"- Branch: {branch}\n" if branch else ""
    files_section = (
        (f"## Complete file list (authoritative — every staged file is here)\n\n{files}\n\n") if files else ""
    )
    facts_section = f"{facts}\n\n" if facts else ""
    return (
        f"{branch_line}"
        "## Staged changes (stat)\n\n"
        f"{stat}\n\n"
        f"{files_section}"
        f"{facts_section}"
        "## Staged diff (may be truncated)\n\n"
        f"{diff}\n\n"
        "## Recent commits (style reference — formatting only, not content)\n\n"
        f"{commits}\n\n"
        "Generate the semantic commit message for ALL staged files in the complete file list above.\n"
        "Every entry in that list MUST be addressed — use file names and stat sizes for any file\n"
        "whose diff was omitted.\n"
        "IMPORTANT: derive ALL content from the diff and stat above. The commit history is\n"
        "used only to match style (length, tone, scope usage) — never to infer what changed.\n\n"
        "Before drafting, state to yourself (silently) the 1-3 concrete *reasons* this change\n"
        "was made. A reason is NOT 'simplifies configuration' or 'improves maintainability' —\n"
        "those are padding. A reason is specific: 'lightline was defined twice, second block\n"
        "silently overwrote the first' or 'pythonrc.vim set tabstop=2 globally instead of\n"
        "locally, leaking a Python setting into every filetype'. If the diff does not support\n"
        "a specific reason, the body should be shorter, not padded."
    )


def build_refine_prompt(draft: str, stat: str, diff: str, commits: str, files: str = "", facts: str = "") -> str:
    """Build a critique-and-rewrite prompt that feeds the draft back to the model."""
    files_section = (
        (f"## Complete file list (authoritative — every staged file is here)\n\n{files}\n\n") if files else ""
    )
    files_section += f"{facts}\n\n" if facts else ""
    return (
        "You produced this commit message for the staged diff:\n\n"
        f"{draft}\n\n"
        "## Staged changes (stat)\n\n"
        f"{stat}\n\n"
        f"{files_section}"
        "## Staged diff (may be truncated)\n\n"
        f"{diff}\n\n"
        "## Recent commits (style reference — formatting only, not content)\n\n"
        f"{commits}\n\n"
        "Critique the draft against these questions, then rewrite it:\n"
        "1. Does the subject line accurately name the primary change type and scope?\n"
        "2. Does it account for EVERY file in the complete file list — not just the most visible one?\n"
        "3. Does the body explain *why* this change was made, not just *what* changed?\n"
        "4. Is there a breaking change that was missed or an issue reference that should be added?\n"
        "5. Is the style consistent with the recent commit history?\n\n"
        "Output ONLY the final improved commit message — no preamble, no critique text, "
        "no markdown fences."
    )


# ── Message post-processing ────────────────────────────────────────────────────


def _strip_think_tags(text: str) -> str:
    """Remove <think>…</think> blocks some reasoning models emit."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences the model wraps output in despite being told not to.

    Handles three shapes:
      * Leading ```<lang>\\n...content...\\n```
      * Trailing ``` on its own line (common when the model half-complies)
      * Inline ``` at the start/end of a line that is otherwise the commit subject
    """
    stripped = text.strip()

    # Full fence: ```[lang]\n...\n```
    full = re.match(r"^```[a-zA-Z]*\n(.*?)\n```\s*$", stripped, flags=re.DOTALL)
    if full:
        return full.group(1).strip()

    # Leading fence only
    stripped = re.sub(r"^```[a-zA-Z]*\n", "", stripped)
    # Trailing fence only (on its own line)
    stripped = re.sub(r"\n```\s*$", "", stripped)
    # Orphan triple-backtick line anywhere (last line is the usual case)
    lines = [ln for ln in stripped.splitlines() if ln.strip() != "```"]
    return "\n".join(lines).strip()


def _take_first_message(text: str) -> str:
    """Return only the first commit message when the model repeats itself."""
    # Some models repeat the message separated by "---" lines
    parts = re.split(r"\n---+\n", text)
    return parts[0].strip()


# Headers the model uses to start a file-enumeration section. Case-insensitive.
_MANIFEST_HEADER_RE = re.compile(
    r"^\s*(?:\*\*)?(?:"
    r"files?\s+(?:removed|added|modified|deleted|changed|created|updated)"
    r"|(?:the\s+)?changes?\s+include"
    r"|summary\s+of\s+changes?"
    r"|(?:files?\s+)?(?:removed|added|modified|deleted|changed|created|updated)\s+files?"
    r")(?:\*\*)?\s*:?\s*$",
    re.IGNORECASE,
)


def _strip_file_manifest(text: str, print_w=None) -> str:
    """Remove hallucinated "Files removed:" manifest sections from the body.

    Small local models frequently enumerate every staged file in the body despite
    explicit prompts forbidding it (the stat already shows this). Detect the
    common section-header shapes and drop from that header through the end of the
    contiguous bullet-list block that follows.

    A "bullet-list block" is one or more lines beginning with ``-``, ``*``, or
    ``N.``. Blank lines inside the block are allowed; the block ends at the first
    non-bullet, non-blank line.
    """
    lines = text.splitlines()
    out: list[str] = []
    stripped_any = False
    i = 0
    bullet_re = re.compile(r"^\s*(?:[-*]|\d+\.)\s+")
    while i < len(lines):
        if _MANIFEST_HEADER_RE.match(lines[i]):
            # Peek ahead: is this header followed (after optional blank) by bullets?
            j = i + 1
            while j < len(lines) and lines[j].strip() == "":
                j += 1
            if j < len(lines) and bullet_re.match(lines[j]):
                # Skip header + bullet block (blanks permitted inside block)
                k = j
                while k < len(lines):
                    if lines[k].strip() == "" or bullet_re.match(lines[k]):
                        k += 1
                        continue
                    break
                # Trim any trailing blank lines we ate (leave one separator in out)
                while out and out[-1].strip() == "":
                    out.pop()
                stripped_any = True
                i = k
                continue
        out.append(lines[i])
        i += 1
    result = "\n".join(out).rstrip() + ("\n" if text.endswith("\n") else "")
    if stripped_any and print_w is not None:
        print_w(
            "⚠ stripped file-manifest section from body — the model re-emitted the git stat despite the prompt rule"
        )
    return result.strip()


SUBJECT_MAX = 72


def wrap_message(message: str, width: int = 90, print_w=None) -> str:
    """Wrap each paragraph of a commit message to at most *width* columns.

    The subject line (first line) is never wrapped — git tooling assumes
    single-line subjects, so wrapping it would corrupt the commit. If the
    subject exceeds SUBJECT_MAX (72 chars, per Conventional Commits), a
    warning is emitted via *print_w* and the subject is left as-is so the
    user sees the violation before committing.
    """
    lines = message.splitlines()
    if not lines:
        return message

    subject = lines[0]
    if len(subject) > SUBJECT_MAX and print_w is not None:
        print_w(
            f"⚠ subject line is {len(subject)} chars (max {SUBJECT_MAX}) — "
            "consider shortening or re-running with --refine-passes 1"
        )

    wrapped = [subject]
    for line in lines[1:]:
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


# ── Structured output ──────────────────────────────────────────────────────────

COMMIT_TYPES = ("feat", "fix", "perf", "refactor", "docs", "style", "test", "chore", "ci", "build", "revert")
COMMIT_TOKENS = 1024  # cap of a structured answer (the schema bounds its fields; a looping model stops here)
COMMIT_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": list(COMMIT_TYPES)},
        "scope": {"type": "string"},
        "breaking": {"type": "boolean"},
        "description": {"type": "string"},
        "body": {"type": "string"},
        "footers": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["type", "scope", "breaking", "description", "body", "footers"],
    "additionalProperties": False,
}
_STRUCTURED_NOTE = """

## Output format for this request

Answer with ONE JSON object, nothing else, with these fields:
  type        one of the types above
  scope       the component name, or "" when the change is cross-cutting
  breaking    true only for a breaking change of a published API (see the rules above)
  description the subject-line description: imperative, lowercase, no trailing period,
              WITHOUT the "type(scope):" prefix (the program builds the header)
  body        the body paragraphs ("" when the subject says it all)
  footers     footer lines such as "BREAKING CHANGE: ..." or "Refs #12" ([] when none)
The examples above show finished messages; they are not the change to describe."""
_STATUS_UNSUPPORTED = (400, 422)  # the provider rejected response_format


def commit_schema(scopes: list[str] | None = None) -> dict:
    """`COMMIT_SCHEMA` with its fields bounded (`fobis.llm.provider.bounded`), the scope restricted to *scopes*
    (plus "" for a cross-cutting change) when given."""
    schema = COMMIT_SCHEMA
    if scopes:
        properties = {**COMMIT_SCHEMA["properties"], "scope": {"type": "string", "enum": [*scopes, ""]}}
        schema = {**COMMIT_SCHEMA, "properties": properties}
    return bounded(schema, limits={"scope": 40, "description": 100, "body": 1500, "footers": 4})


def render_message(data: dict, scopes: list[str] | None = None) -> str:
    """Build the commit message from a structured answer (see `COMMIT_SCHEMA`).

    A scope among the fact-based *scopes* is kept as written (``prism/fnl``); any other is normalised to a
    lowercase component name (a file path or name loses its directories and extension).

    Raises
    ------
    ValueError
        *data* misses a field or has a type outside `COMMIT_TYPES`.
    """
    kind = str(data.get("type", "")).strip().lower()
    description = str(data.get("description", "")).strip()
    if kind not in COMMIT_TYPES or not description:
        raise ValueError(f"not a commit message: {data!r}")
    prefix = rf"^(?:{'|'.join(COMMIT_TYPES)})(?:\([^)]*\))?!?:\s*"
    description = re.sub(prefix, "", description, flags=re.IGNORECASE).rstrip(".").strip()
    if not re.match(r"^[A-Z]{2}", description):  # lowercase the first word, unless it is an acronym (API, MPI)
        description = description[:1].lower() + description[1:]
    scope = str(data.get("scope", "")).strip().strip("()")
    if scope not in (scopes or []):
        scope = re.sub(r"\.\w+$", "", scope.rsplit("/", 1)[-1]).lower()  # a component name, never a file name
    footers = [str(f).strip() for f in data.get("footers") or [] if str(f).strip()]
    footers = [f for f in footers if not f.lower().startswith("co-authored-by")]
    breaking = bool(data.get("breaking")) or any(f.startswith("BREAKING CHANGE:") for f in footers)
    header = f"{kind}{f'({scope})' if scope else ''}{'!' if breaking else ''}: {description}"
    parts = [header]
    body = str(data.get("body", "")).strip()
    if body:
        parts.append(body)
    if footers:
        parts.append("\n".join(footers))
    return "\n\n".join(parts)


def _parse_structured(text: str) -> dict | None:
    """The JSON object of a structured answer, None when *text* is not one."""
    text = _strip_markdown_fences(_strip_think_tags(text)).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


# ── Public entry point ─────────────────────────────────────────────────────────


def generate(
    provider: Provider,
    max_diff_chars: int,
    refine_passes: int = 0,
    print_n=print,
    print_w=print,
    structured: bool = True,
    facts: bool = True,
) -> str:
    """
    Generate a Conventional Commits message for the currently staged changes.

    With *structured* the model answers a JSON object (`COMMIT_SCHEMA`, enforced by the provider's grammar)
    and `render_message` builds the header, so the model cannot get the header syntax wrong; when the
    provider rejects the schema (HTTP 400/422) or the answer is not that JSON, the free-text pipeline is used.

    Parameters
    ----------
    provider : Provider
        The LLM to ask (see `fobis.llm.get_provider`).
    max_diff_chars : int
        Maximum diff characters to include in the prompt.
    refine_passes : int
        Number of critique-and-rewrite iterations after the initial draft.
        0 = single pass (default). 1-3 recommended for small models.
    print_n, print_w : callable
        Normal / warning message printers.
    structured : bool
        Ask for the structured answer (default); False uses the free-text pipeline only.
    facts : bool
        Add the facts of the change (`fobis.ai.change`: scope candidates from history and paths, Fortran line
        kinds, type hints) to the prompt, and restrict the structured scope to the candidates.

    Returns
    -------
    str
        The generated commit message, ready to use.

    Raises
    ------
    CommitError
        Nothing staged (`NothingStagedError`) or a failing git command (`GitError`).
    LLMError
        The provider failed to answer (see `fobis.llm.errors`).
    """
    stat = staged_stat()
    if not stat:
        raise NothingStagedError("Nothing staged. Run `git add <files>` first.")

    files = staged_files()
    diff = staged_diff(max_diff_chars)
    commits = recent_commits()
    branch = current_branch()

    use_schema = structured
    change = None
    if facts:
        from .ai.change import change_facts

        try:
            change = change_facts()
        except (OSError, ValueError) as exc:  # facts are an aid: without them the message is still generated
            print_w(f"facts of the change unavailable: {exc}")
    facts_text = change.render() if change is not None else ""
    scopes = change.scope_names if change is not None else []
    schema = commit_schema(scopes)

    def _from_text(raw: str) -> str:
        """The legacy pipeline: clean a free-text answer."""
        return _strip_file_manifest(
            _take_first_message(_strip_markdown_fences(_strip_think_tags(raw))),
            print_w=print_w,
        )

    def _ask(prompt: str) -> str:
        nonlocal use_schema
        if use_schema:
            try:
                raw = provider.chat(
                    messages(prompt, system=_SYSTEM_PROMPT + _STRUCTURED_NOTE),
                    schema=schema,
                    temperature=0.0,
                    max_tokens=COMMIT_TOKENS,
                ).text
            except ProviderResponseError as exc:
                if exc.status not in _STATUS_UNSUPPORTED:
                    raise
                print_w(f"{label} the provider rejected structured output (HTTP {exc.status}): using free text")
                use_schema = False
            else:
                data = _parse_structured(raw)
                if data is not None:
                    try:
                        return render_message(data, scopes)
                    except ValueError:
                        pass
                print_w(f"{label} the answer is not the requested JSON: using it as free text")
                return _from_text(raw)
        return _from_text(provider.chat(messages(prompt, system=_SYSTEM_PROMPT)).text)

    label = f"[{provider.name}:{provider.model}]"
    print_n(f"{label} Generating commit message…")
    prompt = build_prompt(stat, diff, commits, branch=branch, files=files, facts=facts_text)
    draft = wrap_message(_ask(prompt), print_w=print_w)

    for i in range(refine_passes):
        print_n(f"{label} Refining… (pass {i + 1}/{refine_passes})")
        refine_prompt = build_refine_prompt(draft, stat, diff, commits, files=files, facts=facts_text)
        draft = wrap_message(_ask(refine_prompt), print_w=print_w)

    return draft
