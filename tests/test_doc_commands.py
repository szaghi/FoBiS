"""Every ``fobis`` command written in the documentation exists: its subcommands, its options, and no extra
arguments; every key of a fobos mode in an ``ini`` block is one FoBiS reads (``docs/scripts/check_doc_commands.py``).
The docs once showed ``fobis test --name``, never an option; an unknown mode key is ignored by FoBiS, silently."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import typer

from fobis.cli._app import app

SCRIPT = Path(__file__).resolve().parent.parent / "docs" / "scripts" / "check_doc_commands.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_doc_commands", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up there
    spec.loader.exec_module(module)
    return module


def test_every_documented_command_exists():
    problems = _load().problems()
    assert not problems, "\n".join(str(p) for p in problems)


def test_commands_are_found_in_blocks_continuations_and_inline_spans():
    text = (
        "Run `fobis build --mode gnu` first.\n\n```bash\n$ fobis test --filter 'a*'\n"
        "fobis build \\\n  --mode x \\\n  -j 2\necho fobis build\n```\n"
    )
    assert list(_load().commands(text)) == [
        (1, "fobis build --mode gnu"),
        (4, "fobis test --filter 'a*'"),
        (5, "fobis build --mode x -j 2"),
    ]


def test_check_reports_what_is_wrong():
    docs, root = _load(), typer.main.get_command(app)
    assert docs.check("fobis test --name 'x'", root) == "'fobis test' has no option --name"
    assert docs.check("fobis frobnicate", root) == "unknown command 'fobis frobnicate'"
    assert "takes no argument 'b/fobos'" in docs.check("fobis build --dependon a/fobos b/fobos", root)
    assert docs.check("fobis build --dependon a/fobos --dependon b/fobos", root) is None
    assert docs.check('fobis build --cflags "-O2 -g" --mode gnu', root) is None  # a value starting with a dash
    assert docs.check("fobis build --preprocessor --app -DX", root) is None  # --preprocessor alone: PreForM.py
    assert docs.check("fobis case run [--mode M] <case> | tee log", root) is None  # placeholders, a pipe
    assert docs.check("fobis gate ... --json", root) is None  # abridged


def test_fobos_snippets_keys_are_checked_in_modes_only():
    docs = _load()
    text = (
        "```ini\n[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\ncflag = -O2\nsrc = a\n  b\n\n[case:x]\ntarget = p\n```\n"
        "```ini\n# fobos.lock\n[penf]\ncommit = abc\n```\n"
    )
    keys = [(section, key) for _, section, key in docs.fobos_snippets(text)]
    assert keys == [
        ("modes", "modes"),
        ("mode:gnu", "compiler"),
        ("mode:gnu", "cflag"),
        ("mode:gnu", "src"),
        ("case:x", "target"),
    ]
    sys.path.insert(0, str(SCRIPT.parent))
    from gen_cli_reference import mode_keys

    keys = mode_keys()
    assert "cflag" not in keys and {"cflags", "build_dir", "template", "help", "prefix"} <= set(keys)
    assert "json_output" not in keys and "fobos_case_insensitive" not in keys  # command-line plumbing
