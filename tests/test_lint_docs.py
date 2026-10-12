"""The committed lint-rule docs match the rule registry (regenerate: python docs/scripts/gen_lint_rules.py)."""

from __future__ import annotations

import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "docs", "scripts", "gen_lint_rules.py")
OUT_DIR = os.path.join(ROOT, "docs", "lint-rules")


def _generator():
    spec = importlib.util.spec_from_file_location("gen_lint_rules", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lint_rule_docs_are_up_to_date():
    expected = _generator().generate()
    committed = {name for name in os.listdir(OUT_DIR) if name.endswith(".md") or name == "sidebar.json"}
    assert committed == set(expected), "rule pages added/removed: run python docs/scripts/gen_lint_rules.py"
    stale = []
    for name, content in expected.items():
        with open(os.path.join(OUT_DIR, name), encoding="utf-8") as handle:
            if handle.read() != content:
                stale.append(name)
    assert not stale, f"stale rule pages {stale}: run python docs/scripts/gen_lint_rules.py"
