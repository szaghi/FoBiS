"""The facts of parsed sources kept between builds (issue #218, phase 5).

A build reads every source file of its scan for its modules, uses and includes; on a large tree that is most of the
time of a build with nothing to do. The facts of a file are kept in ``<build_dir>/<obj_dir>/.fobis-parse-cache.json``
and used again while the file is unchanged.

A cached entry is used only when all of these are equal to the ones recorded: the FoBiS version and the settings the
parse reads (preprocessor flags, include directories, compiler, intrinsic modules, include extensions, preprocessor),
the file's size and modification time (ns), and the size and time of every file the preprocessor included into it.
``--no-parse-cache`` (mode key ``no_parse_cache``) parses every file.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from . import __version__
from .Dependency import Dependency
from .plan import ExternalProcedures

CACHE_FILE = ".fobis-parse-cache.json"
SCHEMA = 1


def _stamp(path: str) -> list[int] | None:
    try:
        info = os.stat(path)
    except OSError:
        return None
    return [info.st_size, info.st_mtime_ns]


def context_key(**settings: Any) -> str:
    """The digest of what the parse depends on besides the file itself."""
    text = json.dumps({"fobis": __version__, "schema": SCHEMA, **settings}, sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()


class ParseCache:
    def __init__(self, directory: str, context: str) -> None:
        self.path = os.path.join(directory, CACHE_FILE)
        self.context = context
        self.entries: dict[str, Any] = {}
        self.used: dict[str, Any] = {}
        self.hits = 0
        try:
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict) and data.get("context") == context:
                self.entries = data.get("files", {})
        except (OSError, ValueError):
            pass

    def restore(self, pfile: Any) -> bool:
        """Fill *pfile* from the cache when its entry is current; False otherwise (parse it)."""
        entry = self.entries.get(pfile.name)
        if not entry or entry.get("stamp") != _stamp(pfile.name):
            return False
        if any(_stamp(path) != stamp for path, stamp in entry.get("inputs", [])):
            return False
        facts = entry["facts"]
        for key in ("program", "module", "submodule", "include", "nomodlib", "submodule_ancestor"):
            setattr(pfile, key, facts[key])
        pfile.module_names = list(facts["module_names"])
        pfile.submodule_names = list(facts["submodule_names"])
        pfile.dependencies = [Dependency(dtype=t, name=n, located=bool(loc)) for t, n, loc in facts["dependencies"]]
        procedures = facts.get("external_procedures")
        pfile.external_procedures = ExternalProcedures(**procedures) if procedures is not None else None
        self.used[pfile.name] = entry
        self.hits += 1
        return True

    def store(self, pfile: Any) -> None:
        """Record the facts of a file just parsed."""
        stamp = _stamp(pfile.name)
        if stamp is None:
            return
        inputs = []
        for dep in pfile.dependencies or []:
            if dep.type == "include" and getattr(dep, "located", False):
                inputs.append([dep.name, _stamp(dep.name)])
        procedures = pfile.external_procedures
        self.used[pfile.name] = {
            "stamp": stamp,
            "inputs": inputs,
            "facts": {
                "program": pfile.program,
                "module": pfile.module,
                "submodule": pfile.submodule,
                "include": pfile.include,
                "nomodlib": pfile.nomodlib,
                "submodule_ancestor": pfile.submodule_ancestor,
                "module_names": list(pfile.module_names or []),
                "submodule_names": list(pfile.submodule_names or []),
                "dependencies": [
                    [d.type, d.name, bool(getattr(d, "located", False))] for d in pfile.dependencies or []
                ],
                "external_procedures": None
                if procedures is None
                else {"names": procedures.names, "block_data": procedures.block_data, "binds_c": procedures.binds_c},
            },
        }

    def save(self) -> None:
        """Write the entries of the files of this scan (the others are dropped), when anything changed."""
        if self.used == self.entries:
            return
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump({"context": self.context, "files": self.used}, handle, separators=(",", ":"))
            os.replace(tmp, self.path)
        except OSError:
            pass  # a cache that cannot be written is no error: the next build parses again
