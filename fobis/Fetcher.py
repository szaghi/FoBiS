#!/usr/bin/env python
"""
Fetcher.py, module definition of FoBiS.py Fetcher object.

This module handles fetching and building GitHub-hosted FoBiS.py dependencies.
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
import hashlib
import os
import shutil
import subprocess
from collections.abc import Callable
from typing import Any

from .utils import print_fake, syswork


class Fetcher:
    """
    Fetcher handles fetching and building GitHub-hosted FoBiS.py dependencies.
    """

    DEPS_CONFIG_FILE = ".deps_config.ini"
    LOCK_FILE = "fobos.lock"

    def __init__(
        self,
        deps_dir: str,
        print_n: Callable[..., None] | None = None,
        print_w: Callable[..., None] | None = None,
    ) -> None:
        """
        Parameters
        ----------
        deps_dir : str
          directory where dependencies are stored
        print_n : {None}
          function for printing normal messages
        print_w : {None}
          function for printing warning messages
        """
        self.deps_dir = deps_dir
        self.print_n = print_n if print_n is not None else print_fake
        self.print_w = print_w if print_w is not None else print_fake

    def parse_dep_spec(self, spec: str) -> dict[str, str]:
        """
        Parse a dependency spec string into a dict.

        Format: URL [:: branch=X] [:: tag=X] [:: rev=X] [:: mode=X]
                    [:: use=sources|fobos] [:: semver=^1.5]

        Parameters
        ----------
        spec : str
          dependency specification string

        Returns
        -------
        dict
          parsed fields: 'url', and optionally 'branch', 'tag', 'rev', 'mode',
          'use', 'semver'

        Raises
        ------
        ValueError
          If both ``semver`` and a pinning key (tag/branch/rev) are specified.
        """
        parts = [p.strip() for p in spec.split("::")]
        result: dict[str, str] = {"url": self._resolve_url(parts[0].strip())}
        for part in parts[1:]:
            if "=" in part:
                key, _, value = part.partition("=")
                result[key.strip()] = value.strip()
        # Validate semver exclusivity
        if "semver" in result:
            conflicts = [k for k in ("tag", "branch", "rev") if k in result]
            if conflicts:
                raise ValueError(
                    f"Dependency spec error: 'semver' cannot be combined with "
                    f"{', '.join(conflicts)}. Use one or the other."
                )
        return result

    def list_remote_tags(self, url: str) -> list[str]:
        """
        List all tags in a remote git repository without cloning.

        Parameters
        ----------
        url : str
          Remote repository URL.

        Returns
        -------
        list[str]
          Tag names (e.g. ``['v1.4.0', 'v1.5.3']``).
        """
        result = syswork(f"git ls-remote --tags {url}")
        if result[0] != 0:
            self.print_w(f"Error listing tags for {url}:\n{result[1]}")
            return []
        tags: list[str] = []
        for line in result[1].splitlines():
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            ref = parts[1]
            # Skip peeled tags (refs/tags/vX.Y.Z^{})
            if ref.endswith("^{}"):
                continue
            if ref.startswith("refs/tags/"):
                tags.append(ref[len("refs/tags/") :])
        return tags

    def resolve_semver(self, name: str, url: str, constraint: str) -> str:
        """
        Resolve a semver constraint to a concrete tag.

        Parameters
        ----------
        name : str
        url : str
        constraint : str
          Semver constraint expression (e.g. ``'^1.5'``).

        Returns
        -------
        str
          Resolved tag name.

        Raises
        ------
        SystemExit
          If no tag satisfies the constraint.
        """
        import sys

        from .SemVer import resolve

        self.print_n(f"Resolving semver '{constraint}' for {name}...")
        tags = self.list_remote_tags(url)
        resolved = resolve(tags, constraint)
        if resolved is None:
            self.print_w(
                f"Error: no tag satisfies '{constraint}' for '{name}'.\n"
                f"Available tags: {', '.join(tags[:20]) or '(none)'}"
            )
            sys.exit(1)
        self.print_n(f"Resolved {name} semver '{constraint}' → {resolved}")
        return resolved

    def fetch(
        self,
        name: str,
        url: str,
        branch: str | None = None,
        tag: str | None = None,
        rev: str | None = None,
        update: bool = False,
        frozen_commit: str | None = None,
    ) -> tuple[str, str]:
        """
        Clone or update a dependency repo.

        Parameters
        ----------
        name : str
          dependency name (used as subdirectory name)
        url : str
          git repository URL
        branch : {None}
          branch to check out
        tag : {None}
          tag to check out
        rev : {None}
          revision/commit to check out
        update : {False}
          if True, run git fetch to update before checking out
        frozen_commit : {None}
          if set, check out this exact commit SHA (from lockfile)

        Returns
        -------
        tuple[str, str]
          ``(dep_dir, commit_sha)``
        """
        dep_dir = os.path.join(self.deps_dir, name)
        if not os.path.exists(self.deps_dir):
            os.makedirs(self.deps_dir)
        if not os.path.exists(dep_dir):
            self.print_n("Cloning " + name + " from " + url)
            result = syswork("git clone " + url + " " + dep_dir)
            if result[0] != 0:
                self.print_w("Error cloning " + name + ":\n" + result[1])
                return dep_dir, ""
        elif update:
            self.print_n("Updating " + name)
            result = syswork("git -C " + dep_dir + " fetch")
            if result[0] != 0:
                self.print_w("Error fetching updates for " + name + ":\n" + result[1])
        else:
            self.print_n("Dependency " + name + " already fetched (use --update to refresh)")

        # Frozen mode: check out the pinned commit
        if frozen_commit:
            result = syswork("git -C " + dep_dir + " checkout " + frozen_commit)
            if result[0] != 0:
                self.print_w("Error checking out frozen commit " + frozen_commit + " for " + name + ":\n" + result[1])
        else:
            ref = tag or branch or rev
            if ref:
                self.print_n("Checking out " + ref + " for " + name)
                result = syswork("git -C " + dep_dir + " checkout " + ref)
                if result[0] != 0:
                    self.print_w("Error checking out " + ref + " for " + name + ":\n" + result[1])
            elif update:
                result = syswork("git -C " + dep_dir + " merge --ff-only")
                if result[0] != 0:
                    self.print_w("Error merging updates for " + name + ":\n" + result[1])

        # Record resolved HEAD commit
        sha_result = syswork("git -C " + dep_dir + " rev-parse HEAD")
        commit_sha = sha_result[1].strip() if sha_result[0] == 0 else ""
        return dep_dir, commit_sha

    def build_dep(self, name: str, dep_dir: str, mode: str | None = None) -> None:
        """
        Build a dependency using FoBiS.py build.

        Parameters
        ----------
        name : str
          dependency name (for messages)
        dep_dir : str
          path to the dependency directory
        mode : {None}
          fobos mode to use for building
        """
        fobos_file = os.path.join(dep_dir, "fobos")
        if not os.path.exists(fobos_file):
            self.print_w('Error: dependency "' + name + '" has no fobos file in ' + dep_dir)
            return
        self.print_n("Building dependency " + name)
        old_pwd = os.getcwd()
        os.chdir(dep_dir)
        if mode:
            result = syswork("FoBiS.py build -mode " + mode)
        else:
            result = syswork("FoBiS.py build")
        os.chdir(old_pwd)
        if result[0] != 0:
            self.print_w("Error building " + name + ":\n" + result[1])
        else:
            self.print_n(result[1])

    def save_config(self, deps_info: list[dict[str, Any]]) -> None:
        """
        Write the deps config file for use by FoBiS.py build.

        Deps with use='fobos' are written as 'dependon' entries (library approach).
        Deps with use='sources' (default) are written as 'src' entries (direct source inclusion).

        Parameters
        ----------
        deps_info : list
          list of dicts with keys 'name', 'path', 'mode', 'use'
        """
        config = configparser.RawConfigParser()
        config.add_section("deps")
        dependon_entries = []
        src_entries = []
        for dep in deps_info:
            if dep.get("use", "sources") == "fobos":
                fobos_path = os.path.join(dep["path"], "fobos")
                entry = fobos_path + ":" + dep["mode"] if dep.get("mode") else fobos_path
                dependon_entries.append(entry)
            else:
                src_entries.append(dep["path"])
        if dependon_entries:
            config.set("deps", "dependon", " ".join(dependon_entries))
        if src_entries:
            config.set("deps", "src", " ".join(src_entries))
        config_path = os.path.join(self.deps_dir, self.DEPS_CONFIG_FILE)
        with open(config_path, "w") as cfg_file:
            config.write(cfg_file)
        self.print_n("Saved deps config to " + config_path)

    def _resolve_url(self, repo: str) -> str:
        """
        Convert a shorthand repo reference to a full GitHub HTTPS URL.

        Accepts 'user/repo' (GitHub shorthand) or any full URL unchanged.

        Parameters
        ----------
        repo : str
          repository reference

        Returns
        -------
        str
          full git-cloneable URL
        """
        if repo.startswith("http://") or repo.startswith("https://") or repo.startswith("git@"):
            return repo
        return "https://github.com/" + repo

    def install_from_github(
        self,
        repo: str,
        branch: str | None = None,
        tag: str | None = None,
        rev: str | None = None,
        mode: str | None = None,
        update: bool = False,
        no_build: bool = False,
        prefix: str = "./",
        bin_dir: str = "bin/",
        lib_dir: str = "lib/",
        include_dir: str = "include/",
    ) -> None:
        """
        Clone, build, and install a GitHub-hosted FoBiS project.

        Parameters
        ----------
        repo : str
          repository reference ('user/repo' shorthand or full URL)
        branch : {None}
          branch to check out
        tag : {None}
          tag to check out
        rev : {None}
          revision/commit to check out
        mode : {None}
          fobos mode to use when building
        update : {False}
          re-fetch before building
        no_build : {False}
          clone only, skip building and installing
        prefix : str
          installation prefix directory
        bin_dir : str
          sub-directory under prefix for executables
        lib_dir : str
          sub-directory under prefix for libraries
        include_dir : str
          sub-directory under prefix for module files
        """
        url = self._resolve_url(repo)
        name = url.rstrip("/").split("/")[-1]
        if name.endswith(".git"):
            name = name[:-4]
        dep_dir, _commit = self.fetch(name, url, branch=branch, tag=tag, rev=rev, update=update)
        if no_build:
            self.print_n("Cloned " + name + " to " + dep_dir + " (--no-build: skipping build and install)")
            return
        self._build_dep_tracked(name, dep_dir, mode=mode)
        self._install_artifacts(dep_dir, prefix, bin_dir, lib_dir, include_dir)

    def _build_dep_tracked(self, name: str, dep_dir: str, mode: str | None = None) -> None:
        """
        Build a dependency using 'fobis build --track_build'.

        Parameters
        ----------
        name : str
          dependency name (for messages)
        dep_dir : str
          path to the dependency directory
        mode : {None}
          fobos mode to use for building
        """
        fobos_file = os.path.join(dep_dir, "fobos")
        if not os.path.exists(fobos_file):
            self.print_w('Error: "' + name + '" has no fobos file in ' + dep_dir)
            return
        self.print_n("Building " + name + " (with --track_build)")
        old_pwd = os.getcwd()
        os.chdir(dep_dir)
        cmd = "fobis build --track_build"
        if mode:
            cmd += " -mode " + mode
        result = syswork(cmd)
        os.chdir(old_pwd)
        if result[0] != 0:
            self.print_w("Error building " + name + ":\n" + result[1])
        else:
            self.print_n(result[1])

    def _install_artifacts(self, dep_dir: str, prefix: str, bin_dir: str, lib_dir: str, include_dir: str) -> None:
        """
        Scan dep_dir for .track_build files and copy artifacts to the prefix.

        Parameters
        ----------
        dep_dir : str
          root of the cloned dependency
        prefix : str
          installation prefix
        bin_dir : str
          sub-directory under prefix for executables
        lib_dir : str
          sub-directory under prefix for libraries
        include_dir : str
          sub-directory under prefix for module/include files
        """
        installed_any = False
        for root, _, files in os.walk(dep_dir):
            for filename in files:
                if not filename.endswith(".track_build"):
                    continue
                track_file = configparser.ConfigParser()
                track_file.read(os.path.join(root, filename))
                if not track_file.has_option("build", "output"):
                    continue
                output = track_file.get("build", "output")
                if not os.path.exists(output):
                    continue
                is_program = track_file.has_option("build", "program") and track_file.get("build", "program")
                is_library = track_file.has_option("build", "library") and track_file.get("build", "library")
                if is_program:
                    dest = os.path.join(prefix, bin_dir)
                    os.makedirs(dest, exist_ok=True)
                    self.print_n('Installing "' + output + '" -> "' + dest + '"')
                    shutil.copy(output, dest)
                    installed_any = True
                if is_library:
                    dest = os.path.join(prefix, lib_dir)
                    os.makedirs(dest, exist_ok=True)
                    self.print_n('Installing "' + output + '" -> "' + dest + '"')
                    shutil.copy(output, dest)
                    installed_any = True
                    if track_file.has_option("build", "mod_file"):
                        mod_file = track_file.get("build", "mod_file")
                        inc_dest = os.path.join(prefix, include_dir)
                        os.makedirs(inc_dest, exist_ok=True)
                        self.print_n('Installing "' + mod_file + '" -> "' + inc_dest + '"')
                        shutil.copy(mod_file, inc_dest)
        if not installed_any:
            self.print_w(
                "No installable artifacts found. Ensure the project fobos uses --track_build or check the fobos mode."
            )

    def _compute_sha256(self, dep_dir: str) -> str:
        """
        Compute SHA-256 of the git archive of HEAD in *dep_dir*.

        Parameters
        ----------
        dep_dir : str

        Returns
        -------
        str
          Hex digest, or empty string on failure.
        """
        try:
            result = subprocess.run(
                ["git", "-C", dep_dir, "archive", "HEAD"],
                capture_output=True,
            )
            if result.returncode != 0:
                return ""
            return hashlib.sha256(result.stdout).hexdigest()
        except Exception:
            return ""

    def save_lock(self, lock_entries: list[dict[str, str]]) -> None:
        """
        Write ``fobos.lock`` to the deps_dir root.

        Parameters
        ----------
        lock_entries : list[dict]
          Each dict: ``{'name', 'url', 'commit', 'sha256'}`` plus optional
          ``'branch'``, ``'tag'``, ``'rev'``, ``'semver'``, ``'resolved'``.
        """
        lock_path = os.path.join(self.deps_dir, self.LOCK_FILE)
        config = configparser.RawConfigParser()
        for entry in lock_entries:
            name = entry["name"]
            config.add_section(name)
            for key, value in entry.items():
                if key != "name" and value:
                    config.set(name, key, value)
        with open(lock_path, "w") as f:
            f.write("# fobos.lock — auto-generated by FoBiS.py fetch — do not edit by hand\n\n")
            config.write(f)
        self.print_n("Saved lock file to " + lock_path)

    def load_lock(self) -> dict[str, dict[str, str]]:
        """
        Read ``fobos.lock`` and return ``{name: {url, commit, sha256, ...}}``.

        Returns
        -------
        dict
        """
        lock_path = os.path.join(self.deps_dir, self.LOCK_FILE)
        if not os.path.exists(lock_path):
            return {}
        config = configparser.RawConfigParser()
        config.read(lock_path)
        result: dict[str, dict[str, str]] = {}
        for section in config.sections():
            result[section] = dict(config.items(section))
        return result

    def verify_lock(self, name: str, dep_dir: str, lock: dict[str, dict[str, str]]) -> bool:
        """
        Check that *dep_dir* HEAD matches the lockfile entry for *name*.

        Emits a warning on mismatch; does not abort.

        Parameters
        ----------
        name : str
        dep_dir : str
        lock : dict

        Returns
        -------
        bool
          True if HEAD matches lockfile commit (or name not in lock).
        """
        if name not in lock:
            return True
        locked_commit = lock[name].get("commit", "")
        if not locked_commit:
            return True
        sha_result = syswork("git -C " + dep_dir + " rev-parse HEAD")
        if sha_result[0] != 0:
            return True
        current = sha_result[1].strip()
        if current != locked_commit:
            self.print_w(
                f"Warning: dependency '{name}' HEAD ({current[:12]}) does not match "
                f"fobos.lock ({locked_commit[:12]}). Run 'fobis fetch --update' to refresh."
            )
            return False
        return True

    def load_config(self) -> dict[str, list[str]]:
        """
        Read the deps config file and return a dict with 'dependon' and 'src' lists.

        Returns
        -------
        dict
          'dependon' : list of fobos-path strings for use=fobos deps
          'src'      : list of directory paths for use=sources deps
          either key is absent when no entries of that type exist
        """
        config_path = os.path.join(self.deps_dir, self.DEPS_CONFIG_FILE)
        if not os.path.exists(config_path):
            return {}
        config = configparser.RawConfigParser()
        config.read(config_path)
        result = {}
        if config.has_option("deps", "dependon"):
            result["dependon"] = config.get("deps", "dependon").split()
        if config.has_option("deps", "src"):
            result["src"] = config.get("deps", "src").split()
        return result
