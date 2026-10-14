"""The documentation's command outputs are the real ones: ``docs/scripts/docs_examples.py --check`` reruns every
tutorial session (real gfortran builds, a real fetch from GitHub) and compares with the committed outputs, byte by byte
when the compiler is the recorded one, else by exit status. Regenerate with ``python docs/scripts/docs_examples.py``."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "docs" / "scripts" / "docs_examples.py"


def _load():
    spec = importlib.util.spec_from_file_location("docs_examples", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran")
def test_documented_outputs_are_current(capsys):
    code = _load().main(["--check"])
    out = capsys.readouterr().out
    assert code == 0, f"stale documentation outputs (python docs/scripts/docs_examples.py):\n{out}"


def test_compare_reports_drift_and_ignores_durations(tmp_path):
    docs = _load()
    fresh, committed = tmp_path / "fresh", tmp_path / "committed"
    for root in (fresh, committed):
        (root / "t" / "01").mkdir(parents=True)
        (root / docs.MANIFEST).write_text('{"compiler": "GNU Fortran (Ubuntu 13.4.0) 13.4.0"}')
    (fresh / "t/01/a.txt").write_text("$ fobis test\n  PASS  x  (0.01 s)\n")
    (committed / "t/01/a.txt").write_text("$ fobis test\n  PASS  x  (0.00 s)\n")
    (fresh / "t/01/b.txt").write_text("$ fobis build\nnew\n")
    (committed / "t/01/b.txt").write_text("$ fobis build\nold\n")
    (fresh / "t/01/c.txt").write_text("$ x\n")
    assert docs.compare(fresh, committed) == ["t/01/b.txt: differs", "t/01/c.txt: generated but not committed"]
    (fresh / docs.MANIFEST).write_text('{"compiler": "GNU Fortran (Ubuntu 14.2.0) 14.2.0"}')  # another compiler
    (fresh / "t/01/b.txt").write_text("$ fobis build\nother\n[exit status 1]\n")
    assert docs.compare(fresh, committed)[0] == "t/01/b.txt: [exit status 1] instead of [exit status 0]"
