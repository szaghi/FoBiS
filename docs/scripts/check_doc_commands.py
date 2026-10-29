"""Check every ``fobis`` command written in the documentation against the real command line.

A command is a line of a fenced code block (``$ `` prompt allowed, ``\\`` continuations joined) or an inline code
span that starts with ``fobis``. Its subcommands must exist, and so must every option it names (``--opt`` or
``--opt=value``): the documentation once showed ``fobis test --name``, an option that never existed. Values,
placeholders (``REF``, ``<case>``) and what follows ``--`` are not checked; neither is the changelog (history).

Usage::

    python docs/scripts/check_doc_commands.py        # report, exit 1 when a command is wrong
"""

from __future__ import annotations

import re
import shlex
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent
SKIPPED = ("guide/changelog.md", "node_modules", ".vitepress")
_FENCE = re.compile(r"^(\s*)(```+|~~~+)")
_INLINE = re.compile(r"(?<!`)`(fobis [^`]+)`(?!`)")
_STOP = {"|", "||", "&&", ";", ">", ">>", "2>", "2>&1", "<", "&"}


@dataclass(frozen=True)
class Problem:
    path: str
    line: int
    command: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}: {self.command}"


def commands(text: str) -> Iterator[tuple[int, str]]:
    """``(line number, command)`` for every fobis command of a markdown text."""
    fence: str | None = None
    pending: tuple[int, str] | None = None
    for number, line in enumerate(text.splitlines(), 1):
        match = _FENCE.match(line)
        if match:
            fence = None if fence and match.group(2).startswith(fence[:3]) else fence or match.group(2)
            pending = None
            continue
        if fence is None:
            for span in _INLINE.finditer(line):
                yield number, span.group(1)
            continue
        if pending is not None:  # a continued command
            start, head = pending
            body = line.strip()
            pending = (start, head + " " + body.rstrip("\\").strip()) if body.endswith("\\") else None
            if pending is None:
                yield start, head + " " + body
            continue
        body = line.strip()
        if body.startswith("$ "):
            body = body[2:].strip()
        if body.startswith("fobis "):
            if body.endswith("\\"):
                pending = (number, body.rstrip("\\").strip())
            else:
                yield number, body


def _tokens(command: str) -> list[str]:
    try:
        words = shlex.split(command, comments=True)
    except ValueError:  # an unbalanced quote in an abridged example
        words = command.split()
    found = []
    for word in words:
        if word in _STOP:
            break
        if re.fullmatch(r"\[[^-].*\]|<.*>|--?<.*>", word):  # a placeholder: [options], <subcommand>, --<Tab>
            continue
        found.append(word.strip("[]()"))
    return found


def _is_group(node) -> bool:
    return isinstance(getattr(node, "commands", None), dict)


def check(command: str, root) -> str | None:
    """Why *command* is wrong for the click group *root*, or None. No ``import click``: Typer 0.27 no longer installs
    it (the CI has none); groups, options and arguments are told apart by their attributes."""

    if "legacy" in command:  # an example of the legacy syntax, labelled as such
        return None
    words = _tokens(command)[1:]
    if "..." in words or "…" in words:  # an abridged command
        return None
    node, path = root, ["fobis"]
    while words and _is_group(node):
        name = words[0]
        if name.startswith("-") or not re.fullmatch(r"[a-z][a-z0-9-]*", name):
            break  # an option, or a placeholder (<cmd>, ...)
        if name not in node.commands:
            return f"unknown command '{' '.join([*path, name])}'"
        node = node.commands[name]
        path.append(name)
        words = words[1:]
    from fobis.cli._app import OPTIONAL_VALUES

    names = {"--help"}
    takes_value = set()
    arguments = 0
    for param in node.params:
        opts = [*getattr(param, "opts", []), *getattr(param, "secondary_opts", [])]
        names.update(opts)
        if param.param_type_name == "option" and not param.is_flag and not param.count:
            takes_value.update(getattr(param, "opts", []))
        elif param.param_type_name == "argument":
            arguments += 10**6 if param.nargs == -1 else param.nargs
    if getattr(node, "context_settings", {}).get("allow_extra_args"):
        arguments = 10**6
    if node is root:  # Typer's --install-completion/--show-completion read the shell's name
        arguments = 1
    skip = False
    positional = 0
    for index, word in enumerate(words):
        if word == "--":
            break
        if skip:  # the value of the previous option (it may start with a dash: --cflags "-O2")
            skip = False
            continue
        option = word.split("|")[0].split("=", 1)[0]
        if not re.fullmatch(r"--?[A-Za-z][\w-]*", option):
            positional += 1
            if positional > arguments:
                return f"'{' '.join(path)}' takes no argument {word!r} (repeat the option for several values)"
            continue
        for alternative in word.split("|"):
            option = alternative.split("=", 1)[0]
            if option not in names:
                return f"'{' '.join(path)}' has no option {option}"
        following = words[index + 1] if index + 1 < len(words) else ""
        optional = option in OPTIONAL_VALUES and (not following or following.startswith("-"))
        skip = option in takes_value and "=" not in word and not optional
    return None


# sections that are not modes: their keys are checked by their own parsers
OTHER_SECTIONS = re.compile(
    r"modes|common-variables|project|dependencies|features|test|lint|gate|scheduler|verification|ecosystem|scaffold"
    r"|coverage|indexes"
    r"|include|externals|pkgconfig|examples?|llm|varsets|rule-.*|(case|assess|bench|varset|example|test|feature"
    r"|feature-group):.*|(target|example)\..*",
)
_INI_KEY = re.compile(r"^([A-Za-z_][\w.-]*)\s*[=:]")  # name.qualifier keys too
_SECTION = re.compile(r"^\[([^\]]+)\]\s*(;.*|#.*)?$")


def ini_blocks(text: str) -> Iterator[list[tuple[int, str]]]:
    """The ``(line number, line)`` lists of the ini code blocks of a markdown text."""
    block: list[tuple[int, str]] | None = None
    for number, line in enumerate(text.splitlines(), 1):
        if _FENCE.match(line):
            if block is None and line.strip().lstrip("`~").strip().startswith("ini"):
                block = []
                continue
            if block is not None:
                yield block
            block = None
            continue
        if block is not None:
            block.append((number, line))


def fobos_snippets(text: str) -> Iterator[tuple[int, str, str]]:
    """``(line, section, key)`` for every key of the ini blocks of a markdown text, except the blocks whose first
    line is a comment naming another file (``# fobos.lock ...``, ``# ~/.config/fobis/config.ini``)."""
    for block in ini_blocks(text):
        yield from _ini_keys(block)


def inline_comments(text: str) -> Iterator[tuple[int, str]]:
    """``(line, key)`` for every value of the ini blocks holding an inline ``;``/``#`` comment: a fobos keeps it in
    the value. Shell commands (``[rule-*]`` sections, ``fobis.Fobos.SHELL_KEYS``) are skipped, as FoBiS does."""
    from fobis.Fobos import _INLINE_COMMENT, SHELL_KEYS

    for block in ini_blocks(text):
        section = ""
        for number, line in block:
            head = _SECTION.match(line.strip())
            if head:
                section = head.group(1).strip()
                continue
            key = _INI_KEY.match(line)
            if not key or section.startswith("rule-") or key.group(1) in SHELL_KEYS:
                continue
            if _INLINE_COMMENT.search(line.partition("=")[2]):
                yield number, key.group(1)


def _ini_keys(block: list[tuple[int, str]]) -> Iterator[tuple[int, str, str]]:
    first = next((line.strip() for _, line in block if line.strip()), "")
    if first[:1] in "#;" and re.search(r"\.lock|config\.ini", first):
        return
    listed = set()  # the modes the block's [modes] declares: such a section is a mode whatever its name
    for index, (_, line) in enumerate(block):
        if line.strip() == "[modes]":
            for _, after in block[index + 1 :]:
                match = re.match(r"\s*modes\s*=\s*(.*)", after)
                if match:
                    listed.update(match.group(1).split(";")[0].split())
                    break
    section = ""
    for number, line in block:
        if line[:1] in (" ", "\t"):  # continuation lines
            continue
        head = _SECTION.match(line.strip())
        if head:
            section = head.group(1).strip()
            continue
        key = _INI_KEY.match(line)
        if key and section:
            yield number, (f"mode:{section}" if section in listed else section), key.group(1)


def problems(docs: Path = DOCS) -> list[Problem]:
    """Every wrong fobis command of the markdown pages under *docs*."""
    import typer

    from fobis.cli._app import app

    root = typer.main.get_command(app)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from gen_cli_reference import mode_keys  # the same keys as the fobos reference's table

    known = set(mode_keys())
    from fobis.Fobos import KEY_COMPILERS, KEY_SYSTEMS
    from fobis.lint import rule as lint_rule
    from fobis.lint import rules as _rules  # noqa: F401 (registers the rules)

    rules = set(lint_rule.RULES)
    found = []
    for page in sorted(docs.rglob("*.md")):
        relative = page.relative_to(docs).as_posix()
        if any(part in relative for part in SKIPPED):
            continue
        text = page.read_text()
        for number, command in commands(text):
            message = check(command, root)
            if message:
                found.append(Problem(relative, number, command, message))
        lines = [] if relative.startswith("lint-rules/") else text.splitlines()  # LNT003 shows a bad id on purpose
        for number, line in enumerate(lines, 1):  # rule ids named in suppressions and links
            for rule_id in re.findall(r"ignore\[([A-Z]{3}\d{3})\]|/lint-rules/([A-Z]{3}\d{3})", line):
                rule_id = rule_id[0] or rule_id[1]
                if rule_id not in rules:
                    found.append(Problem(relative, number, rule_id, "no such lint rule"))
        for number, key in inline_comments(text):
            found.append(Problem(relative, number, key, "inline comment: a fobos keeps it in the value"))
        for number, section, key in fobos_snippets(text):
            is_mode = section.startswith("mode:") or not OTHER_SECTIONS.fullmatch(section)
            base, _, qualifier = key.partition(".")
            if qualifier and is_mode and qualifier not in KEY_COMPILERS + KEY_SYSTEMS:
                found.append(Problem(relative, number, f"[{section}] {key}", "no such qualifier (compiler or system)"))
            if is_mode and base not in known and not key.startswith("$"):
                found.append(Problem(relative, number, f"[{section}] {key}", "fobos modes have no such key"))
    return found


def main() -> int:
    found = problems()
    for problem in found:
        print(problem)
    print(f"{len(found)} problem(s)" if found else "every documented fobis command and fobos mode key exists")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
