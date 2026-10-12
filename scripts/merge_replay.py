"""Replay the historical merges of a repository CLONE and measure the deterministic pre-pass of
``fobis merge-assist``: how many conflict hunks it resolves, and how many of those match the resolution that was
committed. It adds and removes a temporary git worktree in the repository: run it on a clone
(``git clone --no-local SRC DST``), never on a working tree you care about.

Usage: python scripts/merge_replay.py CLONE [CLONE ...] [--limit N]
"""

from __future__ import annotations

import argparse
import json

from fobis.ai.merge import replay


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("clones", nargs="+")
    parser.add_argument("--limit", type=int, default=50, help="Merges to replay per repository (most recent first)")
    args = parser.parse_args()
    for clone in args.clones:
        print(clone)
        print(json.dumps(replay(clone, args.limit).as_dict(), indent=2))


if __name__ == "__main__":
    main()
