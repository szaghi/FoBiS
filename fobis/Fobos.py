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
import contextlib
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
_DUAL_PHASE_FLAGS: frozenset[str] = frozenset(
    {
        "-fopenmp",  # gnu, opencoarrays-gnu, amd
        "-qopenmp",  # intel, intel_nextgen (cflags variant)
        "-fiopenmp",  # intel_nextgen (lflags variant)
        "-mp",  # nvfortran, pgi
        "-qsmp=omp",  # ibm
        "-openmp",  # nag
    }
)

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
    "openmp": "openmp",
    "omp": "openmp",  # short alias
    "mpi": "mpi",
    "coarray": "coarray",
    "coverage": "coverage",
    "profile": "profile",
    "openmp_offload": "openmp_offload",
    "omp_offload": "openmp_offload",  # short alias
}


# ---------------------------------------------------------------------------
# Feature expansion (issue #168 — composability)
# ---------------------------------------------------------------------------

_FEATURE_REF_PREFIX = "@"
_FEATURE_NEG_PREFIX = "-"
_FEATURE_MAX_DEPTH = 32

# Tier 2: per-feature metadata and exclusive groups live in dedicated
# sibling sections (mirrors the [mode-X], [rule-X] convention).
_FEATURE_SECTION_PREFIX = "feature:"
_FEATURE_GROUP_SECTION_PREFIX = "feature-group:"

# Varsets — named bundles of $variable bindings, applied at invocation
# time via --varset.  Variables defined inside a [varset:NAME] section
# are NOT auto-merged into the global pool; they apply only when the
# user (or a fobos-declared default) explicitly selects the varset.
_VARSET_SECTION_PREFIX = "varset:"

# Includes — a fobos may pull in sibling fobos files via the [include]
# section's `paths` key.  Resolution is a pre-processing pass that runs
# once at Fobos construction; downstream code sees a single merged config.
_INCLUDE_SECTION = "include"
_INCLUDE_OPTIONAL_PREFIX = "?"
_INCLUDE_MAX_DEPTH = 16


# Keys whose semantics are "an unordered list of names, contributed by every
# source that defines them" — these are token-merged across includes rather
# than overwritten with parent-wins / child-wins.  Tokens are deduped while
# preserving first-seen order.  Listed as (section, key) pairs.
_LIST_MERGED_KEYS: frozenset[tuple[str, str]] = frozenset(
    (
        ("modes", "modes"),
        ("features", "default"),
        ("varsets", "default"),
    )
)


def _merge_into(
    target: configparser.RawConfigParser,
    source: configparser.RawConfigParser,
    child_wins: bool,
) -> None:
    """
    Merge every section/key from ``source`` into ``target`` (key-level merge).

    When both parsers define the same ``[section] key``:
      * ``child_wins=True``  → ``source`` value overwrites ``target``
      * ``child_wins=False`` → ``target`` value is preserved (parent wins)

    Exception: a small set of *list-typed* keys (see ``_LIST_MERGED_KEYS``)
    are always **token-merged** regardless of ``child_wins`` — every source
    that declares them contributes its tokens, and the result is the union
    in first-seen order.  This handles enumeration keys like
    ``[modes] modes = ...`` where the obvious user intent is "the include
    contributes more modes", not "the include's modes get shadowed".

    The ``[include]`` section is never merged — it is a directive consumed
    during resolution.

    Parameters
    ----------
    target : configparser.RawConfigParser
        Parser receiving merged content.
    source : configparser.RawConfigParser
        Parser whose sections/keys are being merged in.
    child_wins : bool
        Conflict-resolution direction for non-list-merged keys.
    """
    for section in source.sections():
        if section == _INCLUDE_SECTION:
            continue
        if not target.has_section(section):
            target.add_section(section)
        for key, value in source.items(section):
            if (section, key) in _LIST_MERGED_KEYS and target.has_option(section, key):
                # Token-merge: union of (existing tokens) and (source tokens),
                # deduped, first-seen order preserved.
                existing = target.get(section, key).split()
                incoming = value.split()
                seen: set[str] = set()
                merged: list[str] = []
                for tok in [*existing, *incoming]:
                    if tok and tok not in seen:
                        seen.add(tok)
                        merged.append(tok)
                target.set(section, key, " ".join(merged))
            elif child_wins or not target.has_option(section, key):
                target.set(section, key, value)


def _resolve_includes(
    parser: configparser.RawConfigParser,
    base_path: str,
    print_w: Callable[[str], None] | None = None,
    case_insensitive: bool = False,
) -> None:
    """
    Expand ``[include] paths = ...`` directives recursively into ``parser``.

    Each path token is resolved relative to the *including* file's directory
    after ``${ENV}`` and ``~`` expansion (absolute paths are used as-is).
    A leading ``?`` marks an optional include; missing optional files are
    skipped silently, missing required files abort with ``sys.exit(1)``.

    Merge semantics (see ``_merge_into``):

      * Sibling includes are merged left-to-right with **last-write-wins**
        among themselves.
      * The collective result is then merged into the parent file with
        **parent-wins**.

    Cycles are detected via a per-walk visited set keyed on resolved real
    paths; the file currently being processed is also in the set so a self-
    include is reported.  Depth is capped at ``_INCLUDE_MAX_DEPTH``.

    The ``[include]`` section is removed from ``parser`` after expansion.

    Parameters
    ----------
    parser : configparser.RawConfigParser
        The fobos parser to expand in place.
    base_path : str
        Path of the fobos file ``parser`` was loaded from; used as the
        anchor for relative include paths and for cycle detection.
    print_w : callable | None
        Sink for error messages emitted before ``sys.exit(1)``.
    case_insensitive : bool
        If True, included parsers also use case-insensitive option keys.
    """

    def _emit(msg: str) -> None:
        if print_w is not None:
            print_w(msg)

    def _expand(target_parser: configparser.RawConfigParser, file_path: str, visited: set[str], depth: int) -> None:
        if depth >= _INCLUDE_MAX_DEPTH:
            _emit(f"Error: include depth exceeded ({_INCLUDE_MAX_DEPTH}) at '{file_path}'.  Likely a recursion bug.")
            sys.exit(1)
        if not target_parser.has_section(_INCLUDE_SECTION):
            return
        raw = (
            target_parser.get(_INCLUDE_SECTION, "paths", fallback="").strip()
            if target_parser.has_option(_INCLUDE_SECTION, "paths")
            else ""
        )
        # Build the sibling-collective: process tokens left-to-right, merging
        # each child into a fresh accumulator with child-wins semantics so
        # the rightmost sibling overrides earlier ones.
        collective = configparser.RawConfigParser()
        if not case_insensitive:
            collective.optionxform = str
        for raw_token in raw.split():
            token = raw_token.strip()
            if not token:
                continue
            optional = token.startswith(_INCLUDE_OPTIONAL_PREFIX)
            if optional:
                token = token[1:]
            if not token:
                continue
            expanded = os.path.expanduser(os.path.expandvars(token))
            if not os.path.isabs(expanded):
                expanded = os.path.join(os.path.dirname(file_path), expanded)
            if not os.path.exists(expanded):
                if optional:
                    continue
                _emit(
                    f"Error: cannot include '{raw_token}' (file not found at "
                    f"'{expanded}').  Use '?{raw_token.lstrip('?')}' to mark "
                    f"this include as optional."
                )
                sys.exit(1)
            real = os.path.realpath(expanded)
            if real in visited:
                trail = " -> ".join([*visited, real])
                _emit(f"Error: include cycle detected: {trail}.")
                sys.exit(1)
            child = configparser.RawConfigParser()
            if not case_insensitive:
                child.optionxform = str
            child.read(expanded)
            # Recurse into the child *before* merging it, so deeply-nested
            # includes are absorbed into ``child`` first.
            _expand(child, expanded, visited | {real}, depth + 1)
            _merge_into(collective, child, child_wins=True)
        # Drop the directive — it has no runtime semantics — then overlay
        # the sibling-collective into the parent with parent-wins.
        target_parser.remove_section(_INCLUDE_SECTION)
        _merge_into(target_parser, collective, child_wins=False)

    base_real = os.path.realpath(base_path)
    _expand(parser, base_path, {base_real}, 0)


def _expand_features(
    requested: list[str],
    features_map: dict[str, str],
    print_w: Callable[[str], None] | None = None,
) -> tuple[list[str], list[str]]:
    """
    Expand a list of requested feature tokens into a flat list of leaf names.

    A requested token may be:
      * a plain name (``release``)         — activated as a leaf, and any
                                             ``@``-references in its value
                                             are recursively expanded.
      * a negated name (``-release``)      — collected as a post-expansion drop
                                             (applied by the caller).

    Inside a feature's value (in ``[features]``) tokens with the ``@`` prefix
    reference another feature by name (recursive); other tokens are literal
    flags belonging to that leaf and are resolved later by the caller.

    Cycle detection uses a per-walk visited stack; re-entering a name on the
    stack emits a warning (via ``print_w``) and aborts that walk's recursion.
    Depth is capped at ``_FEATURE_MAX_DEPTH``.

    Parameters
    ----------
    requested : list[str]
        Ordered list of feature tokens (caller has already merged defaults
        and CLI input).  May contain ``-name`` negation tokens.
    features_map : dict[str, str]
        ``{name: flag_string}`` from ``[features]`` section.
    print_w : callable | None
        Warning sink; if None, warnings are suppressed (used by pure tests).

    Returns
    -------
    (positives, negatives) : tuple[list[str], list[str]]
        Leaf names to activate (insertion-ordered, deduped), and names the
        caller must remove from the active set after activation.
    """
    positives: list[str] = []
    negatives: list[str] = []

    def _warn(msg: str) -> None:
        if print_w is not None:
            print_w(msg)

    def _walk(name: str, stack: list[str]) -> None:
        if len(stack) >= _FEATURE_MAX_DEPTH:
            _warn(f"Warning: feature expansion depth exceeded ({_FEATURE_MAX_DEPTH}) at '{name}'. Aborting expansion.")
            return
        if name in stack:
            cycle = " -> ".join([*stack, name])
            _warn(f"Warning: feature cycle detected: {cycle}. Ignored.")
            return
        if name not in positives:
            positives.append(name)
        # If this name has a value in features_map, walk its @-references.
        value = features_map.get(name)
        if value is None:
            return
        for tok in value.split():
            if tok.startswith(_FEATURE_REF_PREFIX) and len(tok) > 1:
                _walk(tok[1:], [*stack, name])

    for tok in requested:
        if not tok:
            continue
        if tok.startswith(_FEATURE_NEG_PREFIX) and len(tok) > 1:
            target = tok[1:]
            if target not in negatives:
                negatives.append(target)
            continue
        # Plain (positive) request — strip leading '@' if user wrote it.
        name = tok[1:] if tok.startswith(_FEATURE_REF_PREFIX) else tok
        if not name:
            continue
        _walk(name, [])

    return positives, negatives


# ---------------------------------------------------------------------------
# Feature metadata (Tier 2: requires / conflicts / groups)
# ---------------------------------------------------------------------------


@dataclass
class FeatureMetadata:
    """Per-feature constraint metadata (issue #168 — Tier 2).

    A leaf feature can have its flag string defined either in ``[features]``
    (legacy form, no constraints) or in a dedicated ``[feature:NAME]`` block
    that may also declare ``requires`` and ``conflicts``.  Both forms produce
    a ``FeatureMetadata`` instance; the validation pipeline operates on this
    unified view rather than the raw ``[features]`` dict.
    """

    name: str
    flags: str = ""
    requires: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


@dataclass
class FeatureGroup:
    """Mutually-exclusive feature group (issue #168 — Tier 2).

    Declared as ``[feature-group:NAME]`` with:
      * ``members = a b c``  — list of feature names in the group
      * ``default = X``      — optional; when set, the group becomes
                               exactly-one (the default fills the group when
                               no member is explicitly active).  When absent,
                               the group is at-most-one (zero active is OK).
    """

    name: str
    members: list[str] = field(default_factory=list)
    default: str | None = None


def _apply_group_defaults(
    active: list[str],
    groups: dict[str, FeatureGroup],
    negated: list[str],
    print_w: Callable[[str], None] | None = None,
) -> list[str]:
    """
    For each group with a ``default`` declared, fill the group when no member
    is active.  A group whose default was explicitly negated by the user is
    left empty (negation expresses an intentional choice).

    Runs *after* composite expansion and ``_resolve_requires`` so that members
    pulled in via @-references or `requires` correctly suppress the default.

    Parameters
    ----------
    active : list[str]
        Active leaves after expansion / negation / requires-pull.
    groups : dict[str, FeatureGroup]
    negated : list[str]
        Names the user explicitly removed via ``--features -name``; if the
        group's default is among these, the group is left empty.
    print_w : callable | None
        Info sink for "filling group X with default Y" messages.

    Returns
    -------
    list[str]
        ``active`` with group defaults appended where applicable.
    """
    for group in groups.values():
        if group.default is None:
            continue
        if any(member in active for member in group.members):
            continue
        if group.default in negated:
            continue
        active.append(group.default)
        if print_w is not None:
            print_w(f"Activating '{group.default}' as default for feature-group '{group.name}'.")
    return active


def _check_groups(
    active: list[str],
    groups: dict[str, FeatureGroup],
    chain: dict[str, str],
) -> list[str]:
    """
    Verify that no feature-group has more than one active member.

    Parameters
    ----------
    active : list[str]
    groups : dict[str, FeatureGroup]
    chain : dict[str, str]
        ``{leaf: root_originator}`` for verbose messages.

    Returns
    -------
    list[str]
        Error messages, one per violated group.  Empty when no violations.
    """
    errors: list[str] = []
    for group in groups.values():
        active_members = [m for m in group.members if m in active]
        if len(active_members) <= 1:
            continue
        rendered = ", ".join(_format_origin(m, chain) for m in active_members)
        errors.append(
            f"Error: feature-group '{group.name}' is mutually-exclusive but "
            f"has {len(active_members)} active members: {rendered}.  "
            f"Activate exactly one."
        )
    return errors


def _format_origin(name: str, chain: dict[str, str]) -> str:
    """Render '`X`' or '`X` (required by `Y`)' depending on chain membership."""
    if name in chain:
        return f"'{name}' (required by '{chain[name]}')"
    return f"'{name}'"


def _check_conflicts(
    active: list[str],
    metadata: dict[str, FeatureMetadata],
    chain: dict[str, str],
    print_w: Callable[[str], None] | None = None,
) -> list[str]:
    """
    Detect ``[feature:X] conflicts = Y`` violations within the active set.

    Self-conflicts (``conflicts = X`` declared on feature ``X``) are tolerated
    as a warning — no abort.

    Parameters
    ----------
    active : list[str]
        Leaf names currently active.
    metadata : dict[str, FeatureMetadata]
    chain : dict[str, str]
        Map ``{leaf: root_originator}`` from ``_resolve_requires``.
    print_w : callable | None
        Warning sink for self-conflict warnings.

    Returns
    -------
    list[str]
        Error messages, one per detected conflict pair.  Empty list when no
        conflicts are present.  Caller should ``sys.exit(1)`` on non-empty.
    """
    errors: list[str] = []
    seen_pairs: set[tuple[str, str]] = set()

    def _warn(msg: str) -> None:
        if print_w is not None:
            print_w(msg)

    for leaf in active:
        meta = metadata.get(leaf)
        if meta is None:
            continue
        for other in meta.conflicts:
            if other == leaf:
                _warn(f"Warning: feature '{leaf}' declares itself as a conflict. Ignored.")
                continue
            if other not in active:
                continue
            # Canonicalise the pair so symmetric declarations don't duplicate.
            pair = (leaf, other) if leaf < other else (other, leaf)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            errors.append(
                f"Error: features {_format_origin(pair[0], chain)} and "
                f"{_format_origin(pair[1], chain)} conflict.  "
                f"Resolve in fobos or pass --features -{pair[0]} (or -{pair[1]}) to drop one side."
            )
    return errors


def _resolve_requires(
    active: list[str],
    metadata: dict[str, FeatureMetadata],
    print_w: Callable[[str], None] | None = None,
) -> tuple[list[str], dict[str, str]]:
    """
    Pull prerequisites declared via ``[feature:X] requires = ...``.

    A prerequisite that is not already active is appended to the active set
    and walked recursively (its own ``requires`` are resolved too).  A cycle
    in the requires graph is detected via a visited stack and emits a warning
    without entering an infinite loop.

    Parameters
    ----------
    active : list[str]
        Leaf names currently active (post-expansion, post-negation).
    metadata : dict[str, FeatureMetadata]
        Unified metadata view from ``Fobos.get_feature_metadata()``.
    print_w : callable | None
        Warning sink.

    Returns
    -------
    (active, chain) : tuple[list[str], dict[str, str]]
        ``active`` extended in place with auto-pulled prereqs (insertion-ordered);
        ``chain`` maps each auto-pulled leaf to its *root originator* — the
        leaf that started the requires-chain that pulled it in.  Used by
        downstream conflict messages to report "X (required by ROOT)" rather
        than "X (required by intermediate)".  Leaves already active before
        this pass are not in ``chain``.
    """
    chain: dict[str, str] = {}

    def _warn(msg: str) -> None:
        if print_w is not None:
            print_w(msg)

    def _walk(name: str, originator: str, stack: list[str]) -> None:
        if len(stack) >= _FEATURE_MAX_DEPTH:
            _warn(f"Warning: feature 'requires' depth exceeded ({_FEATURE_MAX_DEPTH}) at '{name}'. Aborting.")
            return
        meta = metadata.get(name)
        if meta is None:
            return
        for prereq in meta.requires:
            # Cycle detection runs *before* the "already-active" short-circuit
            # so mutual dependencies (a requires b; b requires a) surface as a
            # warning even though they don't cause infinite recursion.
            if prereq in stack or prereq == name:
                cycle = " -> ".join([*stack, name, prereq])
                _warn(f"Warning: feature 'requires' cycle detected: {cycle}. Ignored.")
                continue
            if prereq in active:
                continue
            active.append(prereq)
            chain[prereq] = originator
            _warn(f"Activating '{prereq}' required by '{originator}'.")
            _walk(prereq, originator, [*stack, name])

    # Iterate over a snapshot — `active` mutates during the walk.
    for leaf in list(active):
        _walk(leaf, leaf, [])

    return active, chain


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
            # Resolve [include] directives before any downstream processing.
            # No-op for fobos files without an [include] section.
            _resolve_includes(
                self.fobos,
                base_path=filename,
                print_w=self.print_w,
                case_insensitive=cliargs.fobos_case_insensitive,
            )
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
                # Token-level membership check.  Substring matching (the
                # legacy behaviour) lets `--mode prism` silently match
                # `prism-fnl-nvf` and pick the wrong mode.
                declared = self.fobos.get("modes", "modes").split()
                if mode in declared:
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

        ``[varset:NAME]`` sections are deliberately skipped: their bindings
        apply only when explicitly selected via ``--varset`` (or the fobos
        default), not as part of the implicit global pool.
        """
        if self.fobos:
            for section in self.fobos.sections():
                if section.startswith(_VARSET_SECTION_PREFIX):
                    continue
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

        The pattern uses a negative-lookahead ``(?![A-Za-z0-9_])`` so that a
        variable name that is a prefix of another (e.g. ``$HDF5`` vs
        ``$HDF5_PREFIX``) does not mangle the longer name's literal in the
        text being substituted.  Without the lookahead, ``re.sub('$HDF5', ...)``
        would match inside ``$HDF5_PREFIX`` and corrupt the value.
        """
        if self.fobos:
            if self.fobos.has_section(section):
                for item in self.fobos.items(section):
                    item_val = item[1]
                    for key, value in list(self.local_variables.items()):
                        pattern = re.escape(key) + r"(?![A-Za-z0-9_])"
                        item_val = re.sub(pattern, value, item_val)
                    self.fobos.set(section, item[0], item_val)
        return

    def _check_local_variables(self, cliargs=None):
        """
        Get and substitute the definition of local variables defined into any sections (modes).

        Resolution of varset overlay:

        * If ``cliargs.varset`` is set, the named varsets are applied in order
          (last-write-wins).  An explicit CLI choice overrides any fobos
          default — they do not stack.
        * Otherwise, if the fobos declares ``[varsets] default = NAME ...``,
          those varsets are applied as the implicit fallback.

        Parameters
        ----------
        cliargs : argparse.Namespace or None
            When not None, ``cliargs.varset`` is honoured.  Passing None keeps
            the legacy behaviour (no varset overlay).
        """
        if self.fobos:
            self._get_local_variables()
            varset_arg: str | None = None
            if cliargs is not None:
                varset_arg = getattr(cliargs, "varset", None) or None
            if varset_arg is None:
                # Fall back to fobos-declared default (if any).
                default_varsets = self._get_default_varsets()
                if default_varsets:
                    varset_arg = " ".join(default_varsets)
            if varset_arg:
                self._apply_varsets(varset_arg)
            if len(self.local_variables) > 0:
                self._substitute_local_variables_mode()
        return

    def _get_default_varsets(self) -> list[str]:
        """
        Return the list of varsets declared as the fobos default.

        Reads ``[varsets] default = a b c`` (space- or comma-separated).

        Returns
        -------
        list[str]
            Empty list when no ``[varsets]`` section exists or no default key is set.
        """
        if not self.fobos:
            return []
        if not self.fobos.has_section("varsets"):
            return []
        if not self.fobos.has_option("varsets", "default"):
            return []
        raw = self.fobos.get("varsets", "default")
        return [n.strip() for n in raw.replace(",", " ").split() if n.strip()]

    def _available_varsets(self) -> list[str]:
        """
        Return the names of all ``[varset:NAME]`` sections in the fobos.

        Returns
        -------
        list[str]
            Sorted list of varset names; empty if none are declared.
        """
        if not self.fobos:
            return []
        return sorted(
            section[len(_VARSET_SECTION_PREFIX) :]
            for section in self.fobos.sections()
            if section.startswith(_VARSET_SECTION_PREFIX)
        )

    def get_varsets_info(self) -> dict[str, Any]:
        """
        Return all ``[varset:NAME]`` sections and the declared default.

        Used by ``fobis introspect --varsets``.

        Returns
        -------
        dict
            ``{"default": [list of default varset names], "varsets": {name: {"$VAR": value, ...}}}``.
        """
        info: dict[str, Any] = {
            "default": self._get_default_varsets(),
            "varsets": {},
        }
        if not self.fobos:
            return info
        for section in self.fobos.sections():
            if not section.startswith(_VARSET_SECTION_PREFIX):
                continue
            name = section[len(_VARSET_SECTION_PREFIX) :]
            bindings: dict[str, str] = {}
            for key, value in self.fobos.items(section):
                if key.startswith("$"):
                    bindings[key] = value.replace("\n", " ").strip()
            info["varsets"][name] = bindings
        return info

    def _apply_varsets(self, varset_arg: str) -> None:
        """
        Overlay one or more ``[varset:NAME]`` sections onto self.local_variables.

        ``varset_arg`` is the raw CLI value: a comma- or space-separated list
        of varset names.  Each named varset is looked up and its ``$NAME``
        bindings merged into the global pool in order.  Later varsets
        override earlier ones for variables they both define
        (last-write-wins).

        A varset that does not exist aborts the build with a verbose error
        listing the available varsets.

        Parameters
        ----------
        varset_arg : str
            CLI value, e.g. ``"leonardo"`` or ``"leonardo,gpu-cc80"``.
        """
        names = [n.strip() for n in varset_arg.replace(",", " ").split() if n.strip()]
        if not names:
            return
        available = self._available_varsets()
        for name in names:
            section = f"{_VARSET_SECTION_PREFIX}{name}"
            if not self.fobos or not self.fobos.has_section(section):
                self.print_w(f"Error: varset '{name}' is not defined.")
                if available:
                    self.print_w(f"  Available varsets: {', '.join(available)}")
                else:
                    self.print_w("  (no [varset:*] sections in this fobos)")
                sys.exit(1)
            binding_count = 0
            for key, value in self.fobos.items(section):
                if not key.startswith("$"):
                    self.print_w(
                        f"Warning: varset '{name}' has key '{key}' without a "
                        f"leading '$' — ignored. Variable bindings must be of "
                        f"the form '$NAME = value'."
                    )
                    continue
                self.local_variables[key] = value.replace("\n", " ")
                binding_count += 1
            if binding_count == 0:
                self.print_w(
                    f"Warning: varset '{name}' defines no variables. Did you forget the '$' prefix on the keys?"
                )
        return

    # Keys handled by dedicated apply phases — never auto-copied from a mode
    # block onto cliargs (would otherwise clobber CLI input before the merge).
    _SKIP_AUTO_ATTRS: frozenset[str] = frozenset({"features", "no_default_features"})

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
                if item[0] in self._SKIP_AUTO_ATTRS:
                    continue
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
            self._check_local_variables(cliargs=cliargs)
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
                    self.print_w(f"Error: {attr} references rule '{rule_name}' which is not defined in the fobos file.")
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

    def get_scaffold_config(self) -> dict[str, Any]:
        """
        Parse the optional [scaffold] section and return scaffold parameters.

        These drive per-project rendering of templated scaffold artifacts (see
        the scaffold feature). All values are empty when the section or option
        is absent, so an unparametrised project renders the scaffold defaults
        unchanged.

        Returns
        -------
        dict
          dict with key 'apt_packages' (str): space-separated extra system
          packages to install in the CI build environment (e.g.
          'libopenmpi-dev openmpi-bin' or 'zlib1g-dev'). Empty string if unset.
        """
        config = {
            "apt_packages": "",
        }
        if self.fobos and self.fobos.has_section("scaffold"):
            if self.fobos.has_option("scaffold", "apt_packages"):
                config["apt_packages"] = self.fobos.get("scaffold", "apt_packages").strip()
        return config

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

    def _get_mode_features(self) -> list[str]:
        """
        Return the space-split list of features declared on the active mode.

        Reads ``features = a b c`` from ``[mode-X]`` (or the mode in use).
        Negation tokens (``-name``) are accepted here too and forwarded to
        the expander as part of the merged request stream.

        Returns
        -------
        list[str]
        """
        if not self.fobos or not self.mode:
            return []
        if not self.fobos.has_option(self.mode, "features"):
            return []
        return self.fobos.get(self.mode, "features").split()

    # ------------------------------------------------------------------
    # Tier 2 metadata readers (issue #168)
    # ------------------------------------------------------------------

    def get_feature_metadata(self) -> dict[str, FeatureMetadata]:
        """
        Return a unified ``{name: FeatureMetadata}`` view of all features.

        Sources (merged):
          * ``[features] name = ...``        — legacy flat form (flags only)
          * ``[feature:name] flags = ...``   — Tier 2 per-feature section
          * ``[feature:name] requires = ...`` and ``conflicts = ...``

        Both forms can coexist *only* when ``[features]`` provides the flag
        string and ``[feature:name]`` provides constraints (no ``flags`` key).
        Defining ``flags`` in both places is a hard error: the user has two
        sources of truth for the same feature's flags, which is always wrong.

        Returns
        -------
        dict[str, FeatureMetadata]
            Empty dict if no [features] section and no [feature:*] sections.

        Raises
        ------
        SystemExit
            If a feature's flags are declared in both [features] and
            [feature:NAME] flags = ... .  Exit code 1.
        """
        metadata: dict[str, FeatureMetadata] = {}
        if not self.fobos:
            return metadata

        # Step 1: seed from [features] (legacy form).
        for name, flags in self.get_features().items():
            metadata[name] = FeatureMetadata(name=name, flags=flags)

        # Step 2: merge [feature:NAME] sections.
        for section in self.fobos.sections():
            if not section.startswith(_FEATURE_SECTION_PREFIX):
                continue
            name = section[len(_FEATURE_SECTION_PREFIX) :].strip()
            if not name:
                continue
            section_flags = ""
            if self.fobos.has_option(section, "flags"):
                section_flags = self.fobos.get(section, "flags").strip()
            requires: list[str] = []
            if self.fobos.has_option(section, "requires"):
                requires = self.fobos.get(section, "requires").split()
            conflicts: list[str] = []
            if self.fobos.has_option(section, "conflicts"):
                conflicts = self.fobos.get(section, "conflicts").split()

            existing = metadata.get(name)
            if existing is None:
                metadata[name] = FeatureMetadata(
                    name=name,
                    flags=section_flags,
                    requires=requires,
                    conflicts=conflicts,
                )
                continue
            # Already present from [features]; allow merging metadata only,
            # not duplicate flag strings.
            if section_flags and existing.flags and section_flags != existing.flags:
                self.print_w(
                    f"Error: feature '{name}' has flags declared in both "
                    f"[features] and [feature:{name}].  Pick one source of truth."
                )
                sys.exit(1)
            if section_flags and not existing.flags:
                existing.flags = section_flags
            existing.requires = requires
            existing.conflicts = conflicts

        return metadata

    def get_feature_groups(self) -> dict[str, FeatureGroup]:
        """
        Return ``{name: FeatureGroup}`` from all ``[feature-group:NAME]`` sections.

        Returns
        -------
        dict[str, FeatureGroup]
            Empty dict if no group sections present.
        """
        groups: dict[str, FeatureGroup] = {}
        if not self.fobos:
            return groups
        for section in self.fobos.sections():
            if not section.startswith(_FEATURE_GROUP_SECTION_PREFIX):
                continue
            name = section[len(_FEATURE_GROUP_SECTION_PREFIX) :].strip()
            if not name:
                continue
            members: list[str] = []
            if self.fobos.has_option(section, "members"):
                members = self.fobos.get(section, "members").split()
            default: str | None = None
            if self.fobos.has_option(section, "default"):
                default_raw = self.fobos.get(section, "default").strip()
                default = default_raw or None
            groups[name] = FeatureGroup(name=name, members=members, default=default)
        return groups

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
        # Tier 2: unified view over [features] and [feature:NAME] sections.
        # For Step 1 the validation pipeline (requires/conflicts/groups) is
        # not yet wired in — we only use the .flags field to preserve
        # byte-identical behaviour for fobos files that don't use Tier 2.
        metadata = self.get_feature_metadata()
        features_map = {name: meta.flags for name, meta in metadata.items() if meta.flags}
        default_features = self.get_default_features() if (self.fobos and self.fobos.has_section("features")) else []

        no_default = getattr(cliargs, "no_default_features", False)
        requested_raw = getattr(cliargs, "features", "") or ""
        requested_names = [n.strip() for n in requested_raw.replace(",", " ").split() if n.strip()]

        # Warn when --features is given but there is no [features] section and
        # none of the *positive* requested names are implicit features.
        # (Negation tokens like '-coverage' are filters, not feature names.)
        if requested_names and not features_map:
            positives_only = [n for n in requested_names if not n.startswith(_FEATURE_NEG_PREFIX)]
            non_implicit = [n for n in positives_only if n not in _IMPLICIT_FEATURES]
            if non_implicit:
                self.print_w(
                    "Warning: --features given but fobos has no [features] section. "
                    f"Unknown feature(s): {', '.join(non_implicit)}. Ignored."
                )

        # Build requested set in resolution order:
        #   1. [features] default (unless --no-default-features)
        #   2. [mode-X] features = ...   (active mode)
        #   3. CLI --features ...
        # Each step appends names not already present; negation tokens flow
        # through to the expander, which collects them and the caller drops
        # the negated names from the active set after expansion.
        requested: list[str] = []
        if not no_default:
            requested.extend(default_features)
        for n in self._get_mode_features():
            if n not in requested:
                requested.append(n)
        for n in requested_names:
            if n not in requested:
                requested.append(n)

        # Expand composites and collect negations.
        active, negated = _expand_features(requested, features_map, self.print_w)
        # Warn on negation tokens that don't match any active feature — almost
        # always a typo; silent no-op would mask the mistake.
        if negated:
            unmatched = [n for n in negated if n not in active]
            for name in unmatched:
                self.print_w(f"Warning: --features negation '-{name}' does not match any active feature. Ignored.")
            # Apply negations: drop negated names from the active set.
            active = [n for n in active if n not in negated]

        # Tier 2: pull in `requires` prereqs (cycle-safe).  ``chain`` maps each
        # auto-pulled leaf to the root originator and is consumed by the
        # conflict-detection step.
        active, requires_chain = _resolve_requires(active, metadata, self.print_w)

        # Tier 2: feature-group defaults — fill any group with no active member
        # using the group's declared default (respecting explicit negation).
        groups = self.get_feature_groups()
        if groups:
            active = _apply_group_defaults(active, groups, negated, self.print_w)

        # Tier 2: detect [feature:X] conflicts violations.  Hard error: the
        # user declared an invariant; respecting it must not be optional.
        errors = _check_conflicts(active, metadata, requires_chain, self.print_w)
        # Tier 2: enforce feature-group mutual exclusivity.
        if groups:
            errors.extend(_check_groups(active, groups, requires_chain))
        if errors:
            for msg in errors:
                self.print_w(msg)
            sys.exit(1)

        # Resolve flags
        extra_cflags: list[str] = []
        extra_lflags: list[str] = []
        for feat in active:
            if feat in features_map:
                # Explicit definition wins — route raw flags by pattern.
                # @-prefixed tokens are references handled by _expand_features
                # and are skipped here (they are not flags).
                flag_str = features_map[feat]
                for tok in flag_str.split():
                    if tok.startswith(_FEATURE_REF_PREFIX):
                        continue
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
                known = sorted(features_map) + sorted(k for k in _IMPLICIT_FEATURES if k not in features_map)
                self.print_w(f"Warning: unknown feature '{feat}'. Known features: {', '.join(known)}. Ignored.")

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
                name = section[len(prefix) :]
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
            with contextlib.suppress(ValueError):
                config["fail_under"] = float(self.fobos.get("coverage", "fail_under"))
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
            with contextlib.suppress(ValueError):
                config["timeout"] = int(self.fobos.get("test", "timeout"))
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
