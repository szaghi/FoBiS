"""The command reference is generated from the command line: every option of every command and subcommand
(``docs/reference/*.md``, between markers), the map of the commands and the table of every fobos mode key
(``docs/fobos/index.md``). Regenerate with ``python docs/scripts/gen_cli_reference.py``."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "docs" / "scripts" / "gen_cli_reference.py"


def test_command_reference_is_current(capsys):
    spec = importlib.util.spec_from_file_location("gen_cli_reference", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    code = module.main(["--check"])
    assert code == 0, f"stale reference (python docs/scripts/gen_cli_reference.py):\n{capsys.readouterr().out}"
