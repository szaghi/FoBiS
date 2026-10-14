"""Replay the historical merges of a repository CLONE and measure the deterministic pre-pass of
``fobis merge-assist``: how many conflict hunks it resolves, and how many of those match the resolution that was
committed. It adds and removes a temporary git worktree in the repository: run it on a clone
(``git clone --no-local SRC DST``), never on a working tree you care about.

With ``--model`` the drafts and the hunks the pre-pass leaves unresolved are also proposed by the configured LLM
(the user configuration's ``[llm]``, as ``fobis merge-assist`` uses it) and compared with the committed resolution.

Usage: python scripts/merge_replay.py CLONE [CLONE ...] [--limit N] [--model]
"""

from __future__ import annotations

import argparse
import json

from fobis.ai.merge import replay


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("clones", nargs="+")
    parser.add_argument("--limit", type=int, default=50, help="Merges to replay per repository (most recent first)")
    parser.add_argument("--model", action="store_true", help="Also ask the configured LLM about drafts and the rest")
    args = parser.parse_args()
    provider = None
    if args.model:
        from fobis.llm import LLMConfig, get_provider
        from fobis.UserConfig import UserConfig

        provider = get_provider(LLMConfig.from_user_config(UserConfig()))
    try:
        for clone in args.clones:
            print(clone)
            print(json.dumps(replay(clone, args.limit, provider).as_dict(), indent=2))
    finally:
        if provider is not None and hasattr(provider, "close"):
            provider.close()


if __name__ == "__main__":
    main()
