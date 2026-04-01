"""
Scaffolder.py — FoBiS scaffold feature: project boilerplate management.
"""

# Copyright (C) 2015  Stefano Zaghi
#
# This file is part of FoBiS.py.
#
# FoBiS.py is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# FoBiS.py is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with FoBiS.py. If not, see <http://www.gnu.org/licenses/>.

import configparser
import datetime
import difflib
import fnmatch
import hashlib
import os
import re
import sys
from importlib import resources

import typer

from .utils import print_fake, syswork


def _parse_dep_spec(spec: str) -> dict:
    """Parse a fobos dep spec string: URL [:: key=val ...]"""
    parts = [p.strip() for p in spec.split("::")]
    result = {"url": parts[0].strip()}
    for part in parts[1:]:
        if "=" in part:
            key, _, value = part.partition("=")
            result[key.strip()] = value.strip()
    return result


def _resolve_dep_url(url: str) -> str:
    """Expand user/repo shorthand to full GitHub HTTPS URL and ensure .git suffix."""
    if not url.startswith("http"):
        url = f"https://github.com/{url}"
    if not url.endswith(".git"):
        url = url + ".git"
    return url


def _fobos_deps_to_fpm(deps: dict) -> str:
    """Convert a fobos {name: spec} dict to an fpm.toml [dependencies] block."""
    if not deps:
        return ""
    lines = ["[dependencies]"]
    for name, spec in deps.items():
        parsed = _parse_dep_spec(spec)
        url = _resolve_dep_url(parsed["url"])
        if "tag" in parsed:
            pin = f', tag="{parsed["tag"]}"'
        elif "rev" in parsed:
            pin = f', rev="{parsed["rev"]}"'
        elif "branch" in parsed:
            pin = f', branch="{parsed["branch"]}"'
        else:
            pin = ""
        lines.append(f'{name} = {{ git="{url}"{pin} }}')
    return "\n".join(lines)


def _git_submodule_deps_to_fpm(cwd: str = ".") -> str:
    """Discover deps from .gitmodules + git submodule status as fpm.toml block."""
    gitmodules = os.path.join(cwd, ".gitmodules")
    if not os.path.exists(gitmodules):
        return ""
    cp = configparser.ConfigParser()
    cp.read(gitmodules)
    if not cp.sections():
        return ""

    # Build rev map: submodule path → commit SHA
    rev_map = {}
    result = syswork("git submodule status")
    if result[0] == 0:
        for line in result[1].splitlines():
            # Format: [+- ]SHA path [(desc)]
            stripped = line.strip().lstrip("+-U")
            parts = stripped.split()
            if len(parts) >= 2:
                rev_map[parts[1]] = parts[0][:40]

    lines = ["[dependencies]"]
    for section in cp.sections():
        # Section names look like: submodule "NAME"
        if not section.lower().startswith("submodule"):
            continue
        name = section.split('"')[1] if '"' in section else section.split()[-1]
        url = cp.get(section, "url", fallback="").strip()
        path = cp.get(section, "path", fallback="").strip()
        if not url:
            continue
        if not url.endswith(".git"):
            url = url + ".git"
        rev = rev_map.get(path, "")
        pin = f', rev="{rev}"' if rev else ""
        lines.append(f'{name} = {{ git="{url}"{pin} }}')
    return "\n".join(lines)


def get_project_vars(fobos=None, overrides=None):
    """
    Build the project variables dict from fobos metadata, git, and defaults.

    Resolution order for each variable:

    - NAME       : fobos [project] name → git remote repo slug → ''
    - SUMMARY    : fobos [project] summary → ''
    - REPOSITORY : fobos [project] repository → git remote get-url origin → ''
    - REPOSITORY_NAME : always derived from REPOSITORY (last URL path component);
                        not stored in fobos — use the repository option instead
    - WEBSITE    : fobos [project] website → ''
    - AUTHORS    : fobos [project] authors (newline-separated list, joined with ', ')
                   → git config user.name → ''
    - EMAIL      : fobos [project] email → git config user.email → ''
    - YEAR       : fobos [project] year → current calendar year

    Parameters
    ----------
    fobos : Fobos | None
        Fobos object for reading [project] section; None if no fobos file.
    overrides : dict | None
        Explicit overrides that take highest priority over all other sources.

    Returns
    -------
    dict
        Keys: NAME, SUMMARY, REPOSITORY, REPOSITORY_NAME, WEBSITE, AUTHORS, EMAIL, YEAR.
    """
    vars_dict = {
        "NAME": "",
        "SUMMARY": "",
        "REPOSITORY": "",
        "REPOSITORY_NAME": "",
        "WEBSITE": "",
        "AUTHORS": "",
        "EMAIL": "",
        "YEAR": str(datetime.date.today().year),
        "DEPENDENCIES": "",
    }

    if fobos is not None:
        info = fobos.get_project_info()
        if info.get("name"):
            vars_dict["NAME"] = info["name"]
        if info.get("summary"):
            vars_dict["SUMMARY"] = info["summary"]
        if info.get("repository"):
            vars_dict["REPOSITORY"] = info["repository"]
        if info.get("website"):
            vars_dict["WEBSITE"] = info["website"]
        if info.get("authors"):
            # fobos stores authors one-per-line (configparser continuation);
            # get_project_info() returns them as a list.
            # Templates receive a comma-separated string for {{AUTHORS}}.
            vars_dict["AUTHORS"] = ", ".join(info["authors"])
        if info.get("email"):
            vars_dict["EMAIL"] = info["email"]
        if info.get("year"):
            vars_dict["YEAR"] = info["year"]

    if not vars_dict["REPOSITORY"]:
        result = syswork("git remote get-url origin")
        if result[0] == 0:
            url = result[1].strip()
            url = re.sub(r"^git@github\.com:", "https://github.com/", url)
            url = re.sub(r"\.git$", "", url)
            vars_dict["REPOSITORY"] = url

    # REPOSITORY_NAME is always derived — it is not a fobos option.
    if vars_dict["REPOSITORY"]:
        vars_dict["REPOSITORY_NAME"] = vars_dict["REPOSITORY"].rstrip("/").split("/")[-1]

    if not vars_dict["AUTHORS"]:
        result = syswork("git config user.name")
        if result[0] == 0:
            vars_dict["AUTHORS"] = result[1].strip()

    if not vars_dict["EMAIL"]:
        result = syswork("git config user.email")
        if result[0] == 0:
            vars_dict["EMAIL"] = result[1].strip()

    if not vars_dict["NAME"] and vars_dict["REPOSITORY_NAME"]:
        vars_dict["NAME"] = vars_dict["REPOSITORY_NAME"]

    # DEPENDENCIES: fobos [dependencies] section first, git submodules as fallback
    if fobos is not None:
        raw_deps = fobos.get_dependencies()
        if raw_deps:
            vars_dict["DEPENDENCIES"] = _fobos_deps_to_fpm(raw_deps)
    if not vars_dict["DEPENDENCIES"]:
        vars_dict["DEPENDENCIES"] = _git_submodule_deps_to_fpm()

    if overrides:
        for key, val in overrides.items():
            if key in vars_dict and val:
                vars_dict[key] = val

    return vars_dict


class Scaffolder:
    """
    Manages project boilerplate via bundled scaffold templates.

    Supports drift detection (status), synchronisation (sync),
    greenfield creation (init), and manifest listing (list).
    """

    def __init__(self, project_vars, cwd=None, print_n=None, print_w=None):
        """
        Parameters
        ----------
        project_vars : dict
            Template variable substitutions (NAME, SUMMARY, …).
        cwd : str | None
            Project root; defaults to the current working directory.
        print_n : callable | None
            Normal message printer.
        print_w : callable | None
            Warning/error message printer.
        """
        self.vars = dict(project_vars)
        self.cwd = cwd or os.getcwd()
        self.print_n = print_n or print_fake
        self.print_w = print_w or print_fake
        self._manifest = None

    @property
    def manifest(self):
        """Lazy-loaded manifest dict keyed by destination path."""
        if self._manifest is None:
            self._manifest = self._load_manifest()
        return self._manifest

    def _load_manifest(self):
        """Read and parse bundled manifest.ini."""
        pkg = resources.files("fobis") / "scaffolds"
        manifest_text = (pkg / "manifest.ini").read_text(encoding="utf-8")
        cp = configparser.ConfigParser()
        cp.read_string(manifest_text)
        entries = {}
        for dest in cp.sections():
            entries[dest] = {
                "source": cp.get(dest, "source"),
                "category": cp.get(dest, "category"),
                "executable": cp.getboolean(dest, "executable", fallback=False),
            }
        return entries

    def _read_template(self, source_rel):
        """Read a bundled template by its manifest source path."""
        pkg = resources.files("fobis") / "scaffolds"
        node = pkg
        for part in source_rel.split("/"):
            node = node / part
        return node.read_text(encoding="utf-8")

    def _render(self, template):
        """Replace {{VAR}} placeholders with project variables."""
        result = template
        for key, val in self.vars.items():
            result = result.replace("{{" + key + "}}", val)
        return result

    @staticmethod
    def _sha256(text):
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _file_sha256(self, path):
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8", errors="replace") as fh:
            return hashlib.sha256(fh.read().encode("utf-8")).hexdigest()

    def _get_canonical(self, entry):
        """Return the canonical content for a manifest entry (rendered if templated)."""
        raw = self._read_template(entry["source"])
        if entry["category"] == "templated":
            return self._render(raw)
        return raw

    def _unified_diff(self, old, new, dest):
        return "".join(
            difflib.unified_diff(
                old.splitlines(keepends=True),
                new.splitlines(keepends=True),
                fromfile=f"a/{dest}",
                tofile=f"b/{dest}",
            )
        )

    def _write_file(self, abs_path, content, executable=False):
        """Write content to abs_path, creating parent dirs as needed."""
        parent = os.path.dirname(abs_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        if executable:
            mode = os.stat(abs_path).st_mode
            os.chmod(abs_path, mode | 0o111)

    def _filter(self, dest, files_glob):
        if files_glob is None:
            return True
        return fnmatch.fnmatch(dest, files_glob)

    # ------------------------------------------------------------------
    # Public commands
    # ------------------------------------------------------------------

    def status(self, files_glob=None, strict=False):
        """
        Show drift report: OK, OUTDATED, or MISSING for each managed file.

        Parameters
        ----------
        files_glob : str | None
            Optional glob pattern to limit scope.
        strict : bool
            Exit non-zero if any drift is detected (for CI use).
        """
        any_drift = False
        for dest, entry in self.manifest.items():
            if not self._filter(dest, files_glob):
                continue
            abs_dest = os.path.join(self.cwd, dest)
            if not os.path.exists(abs_dest):
                self.print_w(f"  MISSING  {dest}")
                any_drift = True
            elif entry["category"] == "init-only":
                # Present and init-only: never check for drift
                self.print_n(f"  OK       {dest}")
            elif self._sha256(self._get_canonical(entry)) != self._file_sha256(abs_dest):
                self.print_n(f"  OUTDATED {dest}")
                any_drift = True
            else:
                self.print_n(f"  OK       {dest}")
        if strict and any_drift:
            sys.exit(1)

    def sync(self, dry_run=False, yes=False, files_glob=None):
        """
        Update files that differ from the canonical template.

        Parameters
        ----------
        dry_run : bool
            Show diffs without writing any files.
        yes : bool
            Apply all changes without prompting.
        files_glob : str | None
            Optional glob pattern to limit scope.
        """
        changed = 0
        for dest, entry in self.manifest.items():
            if not self._filter(dest, files_glob):
                continue
            if entry["category"] == "init-only":
                continue
            abs_dest = os.path.join(self.cwd, dest)
            canonical = self._get_canonical(entry)
            existing = ""
            if os.path.exists(abs_dest):
                with open(abs_dest, encoding="utf-8", errors="replace") as fh:
                    existing = fh.read()
                if self._sha256(canonical) == self._sha256(existing):
                    continue

            diff = self._unified_diff(existing, canonical, dest)
            self.print_n(f"\n--- {dest} ---")
            if diff:
                self.print_n(diff)
            else:
                self.print_n("  (new file)")

            if dry_run:
                continue

            if not yes:
                try:
                    answer = typer.confirm(f"Apply changes to {dest}?", default=True)
                except Exception:
                    answer = True
                if not answer:
                    continue

            self._write_file(abs_dest, canonical, executable=entry["executable"])
            self.print_n(f"  Written  {dest}")
            changed += 1

        if not dry_run:
            self.print_n(f"\n{changed} file(s) updated.")

    def init(self, yes=False):
        """
        Create all missing boilerplate in a new or existing repo.

        Prompts for missing project variables when no fobos provides them.

        Parameters
        ----------
        yes : bool
            Skip confirmation prompts.
        """
        _hints = {
            "AUTHORS": " (comma-separated, e.g. 'Jane Doe, John Smith')",
            "REPOSITORY": " (full URL, e.g. 'https://github.com/user/repo')",
        }
        missing_vars = [k for k, v in self.vars.items() if not v and k != "REPOSITORY_NAME"]
        if missing_vars:
            self.print_n("Some project variables are unset. Please provide them (press Enter to skip):")
            for var in missing_vars:
                hint = _hints.get(var, "")
                try:
                    val = typer.prompt(f"  {var}{hint}", default="")
                except Exception:
                    val = ""
                if val:
                    self.vars[var] = val
                    if var == "REPOSITORY":
                        self.vars["REPOSITORY_NAME"] = val.rstrip("/").split("/")[-1]
                    if var == "REPOSITORY_NAME" and not self.vars.get("REPOSITORY_NAME"):
                        self.vars["REPOSITORY_NAME"] = val

        for dirname in ("src", "docs", ".github/workflows", ".github/actions", "scripts"):
            os.makedirs(os.path.join(self.cwd, dirname), exist_ok=True)
            self.print_n(f"  dir      {dirname}/")

        created = 0
        for dest, entry in self.manifest.items():
            abs_dest = os.path.join(self.cwd, dest)
            if os.path.exists(abs_dest):
                self.print_n(f"  exists   {dest}")
                continue
            canonical = self._get_canonical(entry)
            self._write_file(abs_dest, canonical, executable=entry["executable"])
            self.print_n(f"  created  {dest}")
            created += 1

        self.print_n(f"\n{created} file(s) created.")

    def list_files(self):
        """List all managed template files grouped by category."""
        verbatim = [d for d, e in self.manifest.items() if e["category"] == "verbatim"]
        templated = [d for d, e in self.manifest.items() if e["category"] == "templated"]
        self.print_n("Verbatim files (copied as-is, SHA-256 drift detection):")
        for dest in verbatim:
            self.print_n(f"  {dest}")
        self.print_n("")
        self.print_n("Templated files ({{VAR}} substitution, rendered drift detection):")
        for dest in templated:
            self.print_n(f"  {dest}")
