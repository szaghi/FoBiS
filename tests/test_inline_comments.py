"""A fobos keeps an inline ``;``/``#`` comment in the value: FoBiS warns, and the docs never show one."""

from __future__ import annotations

import configparser
import subprocess
import sys
from pathlib import Path

from fobis.Fobos import inline_comments

DOCS_SCRIPTS = Path(__file__).resolve().parent.parent / "docs" / "scripts"


def parse(text: str) -> configparser.RawConfigParser:
    config = configparser.RawConfigParser()
    config.optionxform = str
    config.read_string(text)
    return config


def test_inline_comments_found_shell_commands_skipped():
    config = parse(
        "[default]\ncompiler = gnu ; my laptop\ncflags = -c -O2 # fast\nlflags = -O2\n"
        "[dependencies]\nutils = path=../utils   ; mine\n"
        "[test]\nlauncher = mpirun -np {ranks} ; split into words, not a shell\n"
        "[rule-docs]\nrule_1 = make clean ; make\n"
        "[verification]\nsetup = module purge ; module load gcc\n"
        "[ecosystem]\ncheck = fobis build # then test\n"
    )
    assert inline_comments(config) == [
        ("default", "compiler", "; my laptop"),
        ("default", "cflags", "# fast"),
        ("dependencies", "utils", "; mine"),
        ("test", "launcher", "; split into words, not a shell"),
    ]


def test_no_whitespace_no_comment():
    """``-gen-interfaces#-fpe`` and ``{} \\;`` are not comments (the separator must follow whitespace)."""
    config = parse("[default]\ncflags = -gen-interfaces#-fpe-all=0\n[x]\nfind = -exec gcov {} \\;\n")
    assert inline_comments(config) == []


def test_build_warns(tmp_path):
    (tmp_path / "fobos").write_text("[default]\ncompiler = gnu\ntarget = a.f90 ; the program\n")
    (tmp_path / "a.f90").write_text("program a\nend program\n")
    result = subprocess.run([sys.executable, "-m", "fobis", "build"], cwd=tmp_path, capture_output=True, text=True)
    assert 'warning: fobos [default] target: "; the program" is part of the value' in result.stdout + result.stderr


def test_docs_show_no_inline_comment():
    sys.path.insert(0, str(DOCS_SCRIPTS))
    from check_doc_commands import inline_comments as doc_comments

    text = "```ini\n[default]\ncompiler = gnu ; x\n; fine\ncflags = -c\n[rule-a]\nrule_1 = a ; b\n```\n"
    assert list(doc_comments(text)) == [(3, "compiler")]
