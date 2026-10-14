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
    (fresh / "t/01/a.txt").write_text("$ fobis test\n  PASS  x  (0.01 s)\n#0  0x751502e28d14 in ???\n")  # no libc lines
    (committed / "t/01/a.txt").write_text(
        "$ fobis test\n  PASS  x  (0.00 s)\n#0  0x7f0a12345678 in ???\n\tat ./signal/../sysdeps/x86_64/libc_sigaction.c:0\n"
    )
    (fresh / "t/01/b.txt").write_text("$ fobis build\nnew\n")
    (committed / "t/01/b.txt").write_text("$ fobis build\nold\n")
    (fresh / "t/01/c.txt").write_text("$ x\n")
    (fresh / "t/01/d.txt").write_text("$ git log --oneline -1\n4817230 feat: x\n")  # a hash of digits only
    (committed / "t/01/d.txt").write_text("$ git log --oneline -1\nc3b0b47 feat: x\n")
    (fresh / "t/01/e.measured.txt").write_text("$ fobis bench\nmedian 1.2 ms\n")  # a measurement: never compared
    (committed / "t/01/e.measured.txt").write_text("$ fobis bench\nmedian 3.4 ms\n[exit status 1]\n")
    (fresh / "t/01/f.measured.txt").write_text("$ fobis bench --record\n")
    (committed / "t/01/f.measured.txt").write_text("$ fobis bench\n")
    assert docs.compare(fresh, committed) == [
        "t/01/b.txt: differs (new 'new', committed 'old')",
        "t/01/c.txt: generated but not committed",
        "t/01/f.measured.txt: another command ($ fobis bench --record)",
    ]
    (fresh / docs.MANIFEST).write_text('{"compiler": "GNU Fortran (Ubuntu 14.2.0) 14.2.0"}')  # another compiler
    (fresh / "t/01/b.txt").write_text("$ fobis build\nother\n[exit status 1]\n")
    assert docs.compare(fresh, committed)[0] == "t/01/b.txt: [exit status 1] instead of [exit status 0]"


def test_a_scratch_directory_with_a_hexadecimal_suffix_is_not_a_hash():
    """mkdtemp suffixes are random: one made only of hex digits matched the hash rule first (a flaky CI failure)."""
    docs = _load()
    fresh = "modernize: base copy in ~/tmp/fobis-modernize-1a2b3c4d\n"
    committed = "modernize: base copy in ~/tmp/fobis-modernize-q8x_kz2m\n"
    assert (
        docs._normalised(fresh)
        == docs._normalised(committed)
        == "modernize: base copy in ~/tmp/fobis-modernize-RANDOM\n"
    )
    assert docs._first_difference(fresh, committed) is None
