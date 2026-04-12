#!/usr/bin/env python
# File: /home/stefano/python/FoBiS/src/main/python/fobis/Fobos.py
# Author: Stefano Zaghi <stefano.zaghi@gmail.com>
# Date: 28.08.2017
# Last Modified Date: 28.08.2017
# Last Modified By: Stefano Zaghi <stefano.zaghi@gmail.com>
"""
fobos.py, module definition of fobos class.
This is a class aimed at fobos file handling.
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
import os
import re
import sys
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from .utils import check_results, print_fake, syswork

# ---------------------------------------------------------------------------
# Feature flag routing
# ---------------------------------------------------------------------------
# Flags that belong to both the compilation phase (cflags) and the linking
# phase (lflags).  Every supported compiler uses the same flag for both phases
# (confirmed from Compiler.py _openmp table), so duplicating into both is
# correct.  The only exception is intel_nextgen, which uses -qopenmp for
# cflags and -fiopenmp for lflags; both are included here so either one
# written in a feature value lands in both phases.
_DUAL_PHASE_FLAGS: frozenset[str] = frozenset({
    "-fopenmp",   # gnu, opencoarrays-gnu, amd
    "-qopenmp",   # intel, intel_nextgen (cflags variant)
    "-fiopenmp",  # intel_nextgen (lflags variant)
    "-mp",        # nvfortran, pgi
    "-qsmp=omp",  # ibm
    "-openmp",    # nag
})

# ---------------------------------------------------------------------------
# Implicit (well-known) features
# ---------------------------------------------------------------------------
# These names are resolved through the compiler's existing capability flags
# rather than raw flag strings in [features].  An explicit [features] entry
# with the same name always takes precedence — implicit resolution is the
# fallback when no explicit definition is found.
#
# Activating an implicit feature is equivalent to passing the corresponding
# CLI flag (e.g. --features openmp  ≡  --openmp), with one difference: it
# does NOT add a preprocessor define.  Add a separate explicit feature for
# that if needed (e.g. [features] omp_defs = -DUSE_OMP).
_IMPLICIT_FEATURES: dict[str, str] = {
    "openmp":        "openmp",
    "omp":           "openmp",        # short alias
    "mpi":           "mpi",
    "coarray":       "coarray",
    "coverage":      "coverage",
    "profile":       "profile",
    "openmp_offload": "openmp_offload",
    "omp_offload":   "openmp_offload", # short alias
}


# ---------------------------------------------------------------------------
# DepNode dataclass for fobis tree
# ---------------------------------------------------------------------------


@dataclass
class DepNode:
    """Node in the inter-project dependency tree (issue #167)."""

    name: str
    spec: str
    fetched: bool
    has_fobos: bool
    children: list["DepNode"] = field(default_factory=list)
    duplicate: bool = False
    version: str = ""


def render_tree(nodes: list[DepNode], prefix: str = "") -> str:
    """
    Render a list of DepNode objects as an ASCII dependency tree.

    Parameters
    ----------
    nodes : list[DepNode]
    prefix : str
        Indentation prefix for recursive calls.

    Returns
    -------
    str
    """
    lines: list[str] = []
    for i, node in enumerate(nodes):
        is_last = i == len(nodes) - 1
        connector = "└── " if is_last else "├── "
        child_prefix = prefix + ("    " if is_last else "│   ")

        label = node.name
        if node.version:
            label += f" {node.version}"
        if node.spec:
            label += f" ({node.spec})"
        if node.duplicate:
            label += " (*) [already shown]"
        elif not node.fetched:
            label += " [not fetched — run fobis fetch]"
        elif not node.has_fobos:
            label += " [no fobos — cannot read transitive deps]"

        lines.append(prefix + connector + label)
        if node.children and not node.duplicate:
            lines.append(render_tree(node.children, child_prefix))
    return "\n".join(l for l in lines if l)


class Fobos:
    """
    Fobos is an object that handles fobos file, its attributes and methods.
    """

    def __init__(
        self,
        cliargs: Any,
        print_n: Callable[..., None] | None = None,
        print_w: Callable[..., None] | None = None,
    ) -> None:
        """
        Parameters
        ----------
        cliargs : argparse object
        print_n : {None}
          function for printing normal message
        print_w : {None}
          function for printing emphized warning message
        """
        if print_n is None:
            self.print_n = print_fake
        else:
            self.print_n = print_n

        if print_w is None:
            self.print_w = print_fake
        else:
            self.print_w = print_w

        self.fobos = None
        self.mode = None
        self.local_variables = {}
        if cliargs.fobos:
            filename = cliargs.fobos
        else:
            filename = "fobos"
        if os.path.exists(filename):
            self.fobos = configparser.RawConfigParser()
            if not cliargs.fobos_case_insensitive:
                self.fobos.optionxform = str  # case sensitive
            self.fobos.read(filename)
            self._set_cliargs(cliargs=cliargs)
        return

    def _check_mode(self, mode):
        """
        Function for checking the presence of the selected mode into the set defined inside the fobos.

        Parameters
        ----------
        mode : str
          name of the selcted mode
        """
        if self.fobos:
            if self.fobos.has_option("modes", "modes"):
                if mode in self.fobos.get("modes", "modes"):
                    self.mode = mode
                else:
                    self.print_w('Error: the mode "' + mode + '" is not defined into the fobos file.')
                    self.modes_list()
                    sys.exit(1)
            else:
                self.print_w('Error: fobos file has not "modes" section.')
                sys.exit(1)
        return

    def _set_mode(self, mode=None):
        """
        Function for setting the selected mode.

        Parameters
        ----------
        mode : {None}
          selected mode
        """
        if self.fobos:
            if mode:
                self._check_mode(mode=mode)
            else:
                if self.fobos.has_option("modes", "modes"):
                    self.mode = self.fobos.get("modes", "modes").split()[0]  # first mode selected
                else:
                    if self.fobos.has_section("default"):
                        self.mode = "default"
                    else:
                        self.print_w('Warning: fobos file has not "modes" section neither "default" one')
        return

    def _check_template(self):
        """
        Check and apply template sections.

        Each mode may specify one or more template names as a space-separated
        list.  Templates are applied left-to-right: the mode itself always
        wins, and earlier templates take precedence over later ones.
        Template-of-template inheritance is expanded depth-first.
        Circular references are detected and cause an error.
        """
        if not self.fobos:
            return

        def _template_names(section):
            if self.fobos.has_option(section, "template"):
                return self.fobos.get(section, "template").split()
            return []

        def _resolve(section, visiting):
            """Return ordered list of template names to apply for section."""
            if section in visiting:
                self.print_w('Error: circular template reference detected involving "' + section + '"')
                sys.exit(1)
            visiting = visiting | {section}
            resolved = []
            for name in _template_names(section):
                if not self.fobos.has_section(name):
                    self.print_w('Error: mode "' + section + '" uses template "' + name + '" that is NOT defined')
                    sys.exit(1)
                if name not in resolved:
                    resolved.append(name)
                for sub in _resolve(name, visiting):
                    if sub not in resolved:
                        resolved.append(sub)
            return resolved

        for section in self.fobos.sections():
            if not self.fobos.has_option(section, "template"):
                continue
            for template in _resolve(section, set()):
                for item in self.fobos.items(template):
                    if item[0] == "template":
                        continue
                    if not self.fobos.has_option(section, item[0]):
                        self.fobos.set(section, item[0], item[1])
        return

    def _get_local_variables(self):
        """
        Get the definition of local variables defined into any sections (modes).
        """
        if self.fobos:
            for section in self.fobos.sections():
                for item in self.fobos.items(section):
                    if item[0].startswith("$"):
                        self.local_variables[item[0]] = item[1].replace("\n", " ")
        return

    def _substitute_local_variables_mode(self):
        """
        Substitute the definition of local variables defined into the mode (section) selected.
        """
        if self.fobos and self.mode:
            self._substitute_local_variables_section(section=self.mode)
        return

    def _substitute_local_variables_section(self, section):
        """
        Substitute the definition of local variables defined into a section.
        """
        if self.fobos:
            if self.fobos.has_section(section):
                for item in self.fobos.items(section):
                    item_val = item[1]
                    for key, value in list(self.local_variables.items()):
                        item_val = re.sub(re.escape(key), value, item_val)
                        # item_val = re.sub(r"(?!" + re.escape(key) + r"[aZ_-])\s*" + re.escape(key) + r"\s*", value, item_val)
                    self.fobos.set(section, item[0], item_val)
        return

    def _check_local_variables(self):
        """
        Get and substitute the definition of local variables defined into any sections (modes).
        """
        if self.fobos:
            self._get_local_variables()
            if len(self.local_variables) > 0:
                self._substitute_local_variables_mode()
        return

    def _set_cliargs_attributes(self, cliargs, cliargs_dict):
        """
        Set attributes of cliargs from fobos options.

        Parameters
        ----------
        cliargs : argparse object
        cliargs_dict : argparse object attributes dictionary
        """
        if self.mode:
            for item in self.fobos.items(self.mode):
                if item[0] in cliargs_dict:
                    if isinstance(cliargs_dict[item[0]], bool):
                        setattr(cliargs, item[0], self.fobos.getboolean(self.mode, item[0]))
                    elif isinstance(cliargs_dict[item[0]], int):
                        setattr(cliargs, item[0], int(item[1]))
                    elif isinstance(cliargs_dict[item[0]], list):
                        setattr(cliargs, item[0], item[1].split())
                    else:
                        setattr(cliargs, item[0], item[1])
        return

    @staticmethod
    def _check_cliargs_cflags(cliargs, cliargs_dict):
        """
        Method for setting attribute of cliargs.

        Parameters
        ----------
        cliargs : argparse object
        cliargs_dict : argparse object attributes dictionary
        """
        for item in cliargs_dict:
            if item in ["cflags", "lflags", "preproc"]:
                val_cli = cliargs_dict[item]
                val_fobos = getattr(cliargs, item)
                if item == "cflags":
                    if val_cli == "-c":
                        match = re.search(r"(-c\s+|-c$)", val_fobos)
                        if match:
                            val_cli = ""  # avoid multiple -c flags
                if val_fobos and val_cli:
                    setattr(cliargs, item, val_fobos + " " + val_cli)
        return

    def _set_cliargs(self, cliargs):
        """
        Set cliargs from fobos options.

        Parameters
        ----------
        cliargs : argparse object
        """
        if self.fobos:
            cliargs_dict = deepcopy(cliargs.__dict__)
            self._set_mode(mode=cliargs.mode)
            self._check_template()
            self._check_local_variables()
            self._set_cliargs_attributes(cliargs=cliargs, cliargs_dict=cliargs_dict)
            self._check_cliargs_cflags(cliargs=cliargs, cliargs_dict=cliargs_dict)
            # Apply build profile flags (prepended so user flags win)
            self._apply_build_profile(cliargs)
            # Apply feature flags (appended after profile)
            self._apply_features(cliargs)
            # Apply external library detection
            self._apply_externals(cliargs)
            # Validate pre_build / post_build rule names
            self._validate_lifecycle_hooks(cliargs)
        return

    def _validate_lifecycle_hooks(self, cliargs: Any) -> None:
        """
        Verify that rule names in pre_build / post_build exist in the fobos file.

        Exits with code 1 if any named rule is undefined.

        Parameters
        ----------
        cliargs : argparse.Namespace
        """
        if not self.fobos or not self.mode:
            return
        for attr in ("pre_build", "post_build"):
            rules = getattr(cliargs, attr, None) or []
            if isinstance(rules, str):
                rules = rules.split()
            for rule_name in rules:
                section = "rule-" + rule_name
                if not self.fobos.has_section(section):
                    self.print_w(
                        f"Error: {attr} references rule '{rule_name}' "
                        f"which is not defined in the fobos file."
                    )
                    sys.exit(1)

    def get(self, option: str, mode: str | None = None, toprint: bool = True) -> str | None:
        """
        Get options defined into the fobos file.

        Parameters
        ----------
        option : str
          option name
        mode : {None}
          eventual mode name
        toprint : {True}
          return of the value: if toprint==False the value is return otherwise is printed to stdout
        """
        value = ""
        if self.fobos:
            self._set_mode(mode=mode)
            if self.fobos.has_option(self.mode, option):
                value = self.fobos.get(self.mode, option)
        if toprint:
            # self.print_w(value)
            print(value)
            return
        else:
            return value

    def get_output_name(self, mode: str | None = None, toprint: bool = True) -> str | None:
        """
        Method for building the output name accordingly to the fobos options.

        Parameters
        ----------
        mode : {None}
          eventual mode name
        toprint : {True}
          return of the value: if toprint==False the value is return otherwise is printed to stdout
        """
        output = ""
        build_dir = self.get(option="build_dir", mode=mode, toprint=False)
        mklib = self.get(option="mklib", mode=mode, toprint=False)
        if self.fobos:
            self._set_mode(mode=mode)
            if self.fobos.has_option(self.mode, "output"):
                output = self.fobos.get(self.mode, "output")
                output = os.path.normpath(os.path.join(build_dir, output))
            elif self.fobos.has_option(self.mode, "target"):
                output = self.fobos.get(self.mode, "target")
                output = os.path.splitext(os.path.basename(output))[0]
                if mklib.lower() == "shared":
                    output = output + ".so"
                elif mklib.lower() == "static":
                    output = output + ".a"
                output = os.path.normpath(os.path.join(build_dir, output))
        if toprint:
            # self.print_w(output)
            print(output)
            return
        else:
            return output

    def modes_list(self) -> None:
        """List defined modes."""
        if self.fobos:
            self.print_n("The fobos file defines the following modes:")
            if self.fobos.has_option("modes", "modes"):
                modes = self.fobos.get("modes", "modes").split()
                for mode in modes:
                    if self.fobos.has_section(mode):
                        if self.fobos.has_option(mode, "help"):
                            helpmsg = self.fobos.get(mode, "help")
                        else:
                            helpmsg = ""
                        self.print_n('  - "' + mode + '" ' + helpmsg)
            else:
                self.print_w("Error: no modes are defined into the fobos file!")
                sys.exit(1)
        sys.exit(0)
        return

    def get_project_info(self) -> dict[str, Any]:
        """
        Parse [project] section and return project metadata.

        Returns
        -------
        dict
          dict with keys 'name' (str), 'authors' (list of str),
          'version' (str, raw value as written in fobos — not resolved),
          'summary' (str), 'repository' (str), 'website' (str), 'email' (str),
          and 'year' (str).
          All values are empty/empty-list if the section or option is absent.
        """
        info = {
            "name": "",
            "authors": [],
            "version": "",
            "summary": "",
            "repository": "",
            "website": "",
            "email": "",
            "year": "",
        }
        if self.fobos and self.fobos.has_section("project"):
            if self.fobos.has_option("project", "name"):
                info["name"] = self.fobos.get("project", "name").strip()
            if self.fobos.has_option("project", "authors"):
                raw = self.fobos.get("project", "authors")
                info["authors"] = [a.strip() for a in raw.splitlines() if a.strip()]
            if self.fobos.has_option("project", "version"):
                info["version"] = self.fobos.get("project", "version").strip()
            if self.fobos.has_option("project", "summary"):
                info["summary"] = self.fobos.get("project", "summary").strip()
            if self.fobos.has_option("project", "repository"):
                info["repository"] = self.fobos.get("project", "repository").strip()
            if self.fobos.has_option("project", "website"):
                info["website"] = self.fobos.get("project", "website").strip()
            if self.fobos.has_option("project", "email"):
                info["email"] = self.fobos.get("project", "email").strip()
            if self.fobos.has_option("project", "year"):
                info["year"] = self.fobos.get("project", "year").strip()
        return info

    def get_version(self) -> str:
        """
        Resolve the project version from [project] and/or git tags.

        Resolution steps
        ----------------
        1. Read 'version' from [project] in fobos.  If the value is a
           file path (relative to the git repository root), the version
           string is read from that file.
        2. Query the most recent git tag via ``git describe --tags --abbrev=0``.
        3. If both sources provide a version and they disagree, emit a
           warning with a suggested fix.
        4. Return the fobos version when available; fall back to the git
           tag; return '' when neither source is determinable.

        Returns
        -------
        str
          Resolved version string, or '' if not determinable.
        """
        fobos_version = ""
        if self.fobos and self.fobos.has_section("project"):
            if self.fobos.has_option("project", "version"):
                raw = self.fobos.get("project", "version").strip()
                # try to resolve as a file path relative to the git repo root
                git_root_result = syswork("git rev-parse --show-toplevel")
                if git_root_result[0] == 0:
                    candidate = os.path.join(git_root_result[1].strip(), raw)
                    if os.path.isfile(candidate):
                        with open(candidate) as ver_file:
                            fobos_version = ver_file.read().strip()
                    else:
                        fobos_version = raw
                else:
                    fobos_version = raw  # not inside a git repo; treat as literal
                if fobos_version and not fobos_version.startswith("v"):
                    fobos_version = "v" + fobos_version

        # query the most recent git tag
        git_version = ""
        git_result = syswork("git describe --tags --abbrev=0")
        if git_result[0] == 0:
            git_version = git_result[1].strip()

        # warn on mismatch
        if fobos_version and git_version and fobos_version != git_version:
            git_version_v = git_version if git_version.startswith("v") else "v" + git_version
            self.print_w("Warning: project version mismatch!")
            self.print_w("  fobos [project] version : " + fobos_version)
            self.print_w("  git tag version         : " + git_version)
            self.print_w("  To fix, either:")
            self.print_w("    - update fobos: set  version = " + git_version_v + "  under [project]")
            self.print_w("    - create a matching tag: git tag " + fobos_version + " && git push --tags")

        return fobos_version or git_version

    def get_dependencies(self) -> dict[str, str]:
        """
        Parse [dependencies] section and return dict of {name: spec_string}.

        Returns
        -------
        dict
          mapping of dependency name to its spec string, or empty dict if no section
        """
        deps = {}
        if self.fobos and self.fobos.has_section("dependencies"):
            for name, spec in self.fobos.items("dependencies"):
                if name == "deps_dir":
                    continue
                deps[name] = spec
        return deps

    def get_deps_dir(self, default: str = ".fobis_deps") -> str:
        """
        Read deps_dir from [dependencies] section of fobos.

        Parameters
        ----------
        default : str
          value returned when the option is absent [default: '.fobis_deps']

        Returns
        -------
        str
          deps_dir value from fobos, or default if not set
        """
        if self.fobos and self.fobos.has_section("dependencies"):
            if self.fobos.has_option("dependencies", "deps_dir"):
                return self.fobos.get("dependencies", "deps_dir").strip()
        return default

    # ------------------------------------------------------------------
    # Feature flags (issue #168)
    # ------------------------------------------------------------------

    def get_features(self) -> dict[str, str]:
        """
        Return ``{feature_name: flag_string}`` from ``[features]`` section.

        The reserved ``default`` key is excluded from the returned dict.

        Returns
        -------
        dict[str, str]
            Empty dict if the section is absent.
        """
        features: dict[str, str] = {}
        if self.fobos and self.fobos.has_section("features"):
            for name, value in self.fobos.items("features"):
                if name.lower() != "default":
                    features[name] = value.strip()
        return features

    def get_default_features(self) -> list[str]:
        """
        Return the space-split list of default features from ``[features] default``.

        Returns
        -------
        list[str]
        """
        if self.fobos and self.fobos.has_section("features"):
            if self.fobos.has_option("features", "default"):
                return self.fobos.get("features", "default").split()
        return []

    def _apply_features(self, cliargs: Any) -> None:
        """
        Resolve active features and append their flags to cliargs.

        Resolution order for each active feature name:

        1. Explicit definition in ``[features]`` section — raw flags, routed
           to cflags/lflags by pattern.
        2. Implicit (well-known) feature in ``_IMPLICIT_FEATURES`` — activates
           the corresponding compiler capability flag (e.g. openmp → sets
           ``cliargs.openmp = True``), which Compiler handles per-compiler.
        3. Neither → warning emitted, feature ignored.

        Called from ``_set_cliargs`` after ``_set_cliargs_attributes``.

        Parameters
        ----------
        cliargs : argparse.Namespace
        """
        features_map = self.get_features() if (self.fobos and self.fobos.has_section("features")) else {}
        default_features = self.get_default_features() if (self.fobos and self.fobos.has_section("features")) else []

        no_default = getattr(cliargs, "no_default_features", False)
        requested_raw = getattr(cliargs, "features", "") or ""
        requested_names = [n.strip() for n in requested_raw.replace(",", " ").split() if n.strip()]

        # Warn when --features is given but there is no [features] section and
        # none of the requested names are implicit features.
        if requested_names and not features_map:
            non_implicit = [n for n in requested_names if n not in _IMPLICIT_FEATURES]
            if non_implicit:
                self.print_w(
                    "Warning: --features given but fobos has no [features] section. "
                    f"Unknown feature(s): {', '.join(non_implicit)}. Ignored."
                )

        # Build active set
        active: list[str] = []
        if not no_default:
            active.extend(default_features)
        for n in requested_names:
            if n not in active:
                active.append(n)

        # Resolve flags
        extra_cflags: list[str] = []
        extra_lflags: list[str] = []
        for feat in active:
            if feat in features_map:
                # Explicit definition wins — route raw flags by pattern.
                flag_str = features_map[feat]
                for tok in flag_str.split():
                    if tok in _DUAL_PHASE_FLAGS:
                        extra_cflags.append(tok)
                        extra_lflags.append(tok)
                    elif tok.startswith("-l") or tok.startswith("-L") or tok.startswith("-Wl"):
                        extra_lflags.append(tok)
                    else:
                        extra_cflags.append(tok)
            elif feat in _IMPLICIT_FEATURES:
                # Implicit feature — delegate to the compiler capability system.
                attr = _IMPLICIT_FEATURES[feat]
                setattr(cliargs, attr, True)
            else:
                known = sorted(features_map) + sorted(
                    k for k in _IMPLICIT_FEATURES if k not in features_map
                )
                self.print_w(
                    f"Warning: unknown feature '{feat}'. "
                    f"Known features: {', '.join(known)}. Ignored."
                )

        if extra_cflags:
            existing = getattr(cliargs, "cflags", "") or ""
            cliargs.cflags = (existing + " " + " ".join(extra_cflags)).strip()
        if extra_lflags:
            existing = getattr(cliargs, "lflags", "") or ""
            cliargs.lflags = (existing + " " + " ".join(extra_lflags)).strip()

        cliargs.active_features = active if active else []

    # ------------------------------------------------------------------
    # Build profiles (issue #176)
    # ------------------------------------------------------------------

    def _apply_build_profile(self, cliargs: Any) -> None:
        """
        Apply built-in build profile flags (debug/release/asan/coverage).

        Prepends profile flags so user cflags/lflags override them.

        Parameters
        ----------
        cliargs : argparse.Namespace
        """
        build_profile = getattr(cliargs, "build_profile", "") or ""
        if not build_profile:
            return
        from .Profiles import get_profile_flags

        compiler = getattr(cliargs, "compiler", "gnu") or "gnu"
        flags = get_profile_flags(compiler, build_profile, print_w=self.print_w)
        if flags["cflags"]:
            existing = getattr(cliargs, "cflags", "") or ""
            cliargs.cflags = (flags["cflags"] + " " + existing).strip()
        if flags["lflags"]:
            existing = getattr(cliargs, "lflags", "") or ""
            cliargs.lflags = (flags["lflags"] + " " + existing).strip()

    # ------------------------------------------------------------------
    # External library detection (issue #169)
    # ------------------------------------------------------------------

    def get_externals_map(self) -> dict[str, str]:
        """
        Return ``{name: spec}`` from ``[externals]`` section.

        Returns
        -------
        dict[str, str]
            Empty dict if section absent.
        """
        ext: dict[str, str] = {}
        if self.fobos and self.fobos.has_section("externals"):
            for name, spec in self.fobos.items("externals"):
                ext[name] = spec.strip()
        return ext

    def _apply_externals(self, cliargs: Any) -> None:
        """
        Probe and apply external system library flags to cliargs.

        Reads ``externals = name1 name2`` from the active mode and resolves
        each entry via the ``[externals]`` section.

        Parameters
        ----------
        cliargs : argparse.Namespace
        """
        if not self.fobos or not self.mode:
            return
        if not self.fobos.has_option(self.mode, "externals"):
            return
        active_names = self.fobos.get(self.mode, "externals").split()
        if not active_names:
            return
        externals_map = self.get_externals_map()
        from .Externals import ExternalResolver

        resolver = ExternalResolver(print_n=self.print_n, print_w=self.print_w)
        flags = resolver.resolve_all(active_names, externals_map)
        if flags.cflags:
            existing = getattr(cliargs, "cflags", "") or ""
            cliargs.cflags = (existing + " " + flags.cflags).strip()
        if flags.lflags:
            existing = getattr(cliargs, "lflags", "") or ""
            cliargs.lflags = (existing + " " + flags.lflags).strip()
        if flags.includes:
            cliargs.include = list(getattr(cliargs, "include", []) or []) + flags.includes
        if flags.lib_dirs:
            cliargs.lib_dir = list(getattr(cliargs, "lib_dir", []) or []) + flags.lib_dirs

    # ------------------------------------------------------------------
    # Multiple targets (issue #175)
    # ------------------------------------------------------------------

    def get_targets(self, section_prefix: str = "target") -> list[dict[str, Any]]:
        """
        Return list of target dicts from ``[target.NAME]`` sections.

        Parameters
        ----------
        section_prefix : str
            Section prefix to search for (``'target'`` or ``'example'``).

        Returns
        -------
        list[dict]
            Each dict: ``{'name': str, 'source': str, 'output': str, **overrides}``
        """
        targets: list[dict[str, Any]] = []
        if not self.fobos:
            return targets
        prefix = section_prefix + "."
        for section in self.fobos.sections():
            if section.lower().startswith(prefix.lower()):
                name = section[len(prefix):]
                target_dict: dict[str, Any] = {"name": name}
                for key, value in self.fobos.items(section):
                    if key == "source":
                        target_dict["source"] = value.strip()
                    elif key == "output":
                        target_dict["output"] = value.strip()
                    else:
                        target_dict[key] = value.strip()
                targets.append(target_dict)
        return targets

    # ------------------------------------------------------------------
    # Dependency tree (issue #167)
    # ------------------------------------------------------------------

    def get_dep_tree(
        self,
        deps_dir: str,
        depth: int = 0,
        max_depth: int | None = None,
        visited: set[str] | None = None,
        dedupe: bool = True,
    ) -> list[DepNode]:
        """
        Recursively build the inter-project dependency tree.

        Parameters
        ----------
        deps_dir : str
        depth : int
        max_depth : int or None
        visited : set, optional
        dedupe : bool

        Returns
        -------
        list[DepNode]
        """
        if visited is None:
            visited = set()
        if max_depth is not None and depth >= max_depth:
            return []
        deps = self.get_dependencies()
        nodes: list[DepNode] = []
        for name, spec in deps.items():
            dep_dir = os.path.join(deps_dir, name)
            fetched = os.path.isdir(dep_dir)
            fobos_file = os.path.join(dep_dir, "fobos")
            has_fobos = fetched and os.path.isfile(fobos_file)

            # version from spec (tag/branch/semver)
            version = ""
            for part in spec.split("::"):
                part = part.strip()
                for key in ("tag", "semver", "branch", "rev"):
                    if part.startswith(key + "="):
                        version = part.split("=", 1)[1]
                        break

            # deduplication key
            dedup_key = spec.split("::")[0].strip() + "#" + name

            if dedup_key in visited:
                node = DepNode(
                    name=name,
                    spec=spec,
                    fetched=fetched,
                    has_fobos=has_fobos,
                    version=version,
                    duplicate=True,
                )
                nodes.append(node)
                continue

            if dedupe:
                visited.add(dedup_key)

            children: list[DepNode] = []
            if has_fobos:
                try:
                    import argparse
                    dummy_args = argparse.Namespace(
                        fobos=fobos_file,
                        fobos_case_insensitive=False,
                        mode=None,
                    )
                    child_fobos = Fobos(cliargs=dummy_args)
                    child_version = child_fobos.get_version() or version
                    children = child_fobos.get_dep_tree(
                        deps_dir=deps_dir,
                        depth=depth + 1,
                        max_depth=max_depth,
                        visited=visited,
                        dedupe=dedupe,
                    )
                except Exception:
                    child_version = version
            else:
                child_version = version

            node = DepNode(
                name=name,
                spec=spec,
                fetched=fetched,
                has_fobos=has_fobos,
                version=child_version if has_fobos else version,
                children=children,
                duplicate=False,
            )
            nodes.append(node)
        return nodes

    # ------------------------------------------------------------------
    # pkg-config spec (issue #179)
    # ------------------------------------------------------------------

    def get_pkgconfig_spec(self) -> Any | None:
        """
        Return a PkgConfigSpec built from fobos options, or None if disabled.

        Returns
        -------
        PkgConfigSpec or None
        """
        if not self.fobos or not self.mode:
            return None
        if not self.fobos.has_option(self.mode, "pkgconfig"):
            return None
        enabled = self.fobos.getboolean(self.mode, "pkgconfig", fallback=False)
        if not enabled:
            return None
        from .PkgConfig import PkgConfigSpec

        proj = self.get_project_info()
        name = (
            self.fobos.get(self.mode, "pkgconfig_name").strip()
            if self.fobos.has_option(self.mode, "pkgconfig_name")
            else proj.get("name", "")
        )
        description = (
            self.fobos.get(self.mode, "pkgconfig_desc").strip()
            if self.fobos.has_option(self.mode, "pkgconfig_desc")
            else proj.get("summary", "")
        )
        url = (
            self.fobos.get(self.mode, "pkgconfig_url").strip()
            if self.fobos.has_option(self.mode, "pkgconfig_url")
            else proj.get("repository", "")
        )
        requires = (
            self.fobos.get(self.mode, "pkgconfig_req").strip()
            if self.fobos.has_option(self.mode, "pkgconfig_req")
            else ""
        )
        requires_priv = (
            self.fobos.get(self.mode, "pkgconfig_req_priv").strip()
            if self.fobos.has_option(self.mode, "pkgconfig_req_priv")
            else ""
        )
        version = self.get_version()
        return PkgConfigSpec(
            name=name,
            version=version,
            description=description,
            url=url,
            requires=requires,
            requires_priv=requires_priv,
        )

    # ------------------------------------------------------------------
    # Coverage config (issue #180)
    # ------------------------------------------------------------------

    def get_coverage_config(self) -> dict[str, Any]:
        """
        Read the optional ``[coverage]`` section and return config dict.

        Returns
        -------
        dict
            Keys: ``format`` (list[str]), ``output_dir`` (str),
            ``exclude`` (list[str]), ``fail_under`` (float or None).
        """
        config: dict[str, Any] = {
            "format": ["html"],
            "output_dir": "coverage",
            "exclude": [],
            "fail_under": None,
        }
        if not self.fobos or not self.fobos.has_section("coverage"):
            return config
        if self.fobos.has_option("coverage", "format"):
            config["format"] = self.fobos.get("coverage", "format").split()
        if self.fobos.has_option("coverage", "output_dir"):
            config["output_dir"] = self.fobos.get("coverage", "output_dir").strip()
        if self.fobos.has_option("coverage", "exclude"):
            config["exclude"] = self.fobos.get("coverage", "exclude").split()
        if self.fobos.has_option("coverage", "fail_under"):
            try:
                config["fail_under"] = float(self.fobos.get("coverage", "fail_under"))
            except ValueError:
                pass
        return config

    # ------------------------------------------------------------------
    # Test config (issue #173)
    # ------------------------------------------------------------------

    def get_test_config(self) -> dict[str, Any]:
        """
        Read the optional ``[test]`` section and return test config dict.

        Returns
        -------
        dict
            Keys: ``test_dir``, ``suite``, ``timeout``, ``compiler``, ``cflags``.
        """
        config: dict[str, Any] = {
            "test_dir": "test",
            "suite": "",
            "timeout": 60,
            "compiler": "",
            "cflags": "",
        }
        if not self.fobos or not self.fobos.has_section("test"):
            return config
        for key in ("test_dir", "suite", "compiler", "cflags"):
            if self.fobos.has_option("test", key):
                config[key] = self.fobos.get("test", key).strip()
        if self.fobos.has_option("test", "timeout"):
            try:
                config["timeout"] = int(self.fobos.get("test", "timeout"))
            except ValueError:
                pass
        return config

    def rules_list(self, quiet: bool = False) -> None:
        """
        Function for listing defined rules.

        Parameters
        ----------
        quiet : {False}
          less verbose outputs than default
        """
        if self.fobos:
            self.print_n("The fobos file defines the following rules:")
            for rule in self.fobos.sections():
                if rule.startswith("rule-"):
                    if self.fobos.has_option(rule, "help"):
                        helpmsg = self.fobos.get(rule, "help")
                    else:
                        helpmsg = ""
                    self.print_n('  - "' + rule.split("rule-")[1] + '" ' + helpmsg)
                    if self.fobos.has_option(rule, "quiet"):
                        quiet = self.fobos.getboolean(rule, "quiet")
                    for rul in self.fobos.options(rule):
                        if rul.startswith("rule"):
                            if not quiet:
                                self.print_n("       Command => " + self.fobos.get(rule, rul))
        sys.exit(0)
        return

    def rule_execute(self, rule: str, quiet: bool = False, log: bool = False) -> None:
        """
        Function for executing selected rule.

        Parameters
        ----------
        rule : str
          rule name
        quiet : {False}
          less verbose outputs than default
        log : {False}
          bool for activate errors log saving
        """
        if self.fobos:
            self.print_n('Executing rule "' + rule + '"')
            rule_name = "rule-" + rule
            if self.fobos.has_section(rule_name):
                self._get_local_variables()
                self._substitute_local_variables_section(section=rule_name)
                results = []
                quiet = False
                log = False
                if self.fobos.has_option(rule_name, "quiet"):
                    quiet = self.fobos.getboolean(rule_name, "quiet")
                if self.fobos.has_option(rule_name, "log"):
                    log = self.fobos.getboolean(rule_name, "log")
                for rul in self.fobos.options(rule_name):
                    if rul.startswith("rule"):
                        if not quiet:
                            self.print_n("   Command => " + self.fobos.get(rule_name, rul))
                        result = syswork(self.fobos.get(rule_name, rul))
                        results.append(result)
                if log:
                    check_results(results=results, log="rules_errors.log", print_w=self.print_w)
                else:
                    check_results(results=results, print_w=self.print_w)
            else:
                self.print_w('Error: the rule "' + rule + '" is not defined into the fobos file. Defined rules are:')
                self.rules_list(quiet=quiet)
                sys.exit(1)
        return
