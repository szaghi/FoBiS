"""
_app.py — Typer application instance, arg normaliser, and namespace factory.
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

import argparse
import re
from typing import Annotated

import typer

# ---------------------------------------------------------------------------
# Argument normaliser — preserves backward compat with argparse-style options
# ---------------------------------------------------------------------------
_MULTI_CHAR_OPT = re.compile(r"^-[A-Za-z][A-Za-z0-9_-]+$")
_LONG_OPTIONS = None


def _long_options():
    """
    Return the names (without dashes) of the long options of all the commands.

    The set is built once, at the first call: the commands are all registered by then.
    """
    global _LONG_OPTIONS
    if _LONG_OPTIONS is None:
        names = set()

        def _collect(command):
            for param in command.params:
                for opt in list(param.opts) + list(param.secondary_opts):
                    if opt.startswith("--"):
                        names.add(opt[2:])
            for sub_command in getattr(command, "commands", {}).values():
                _collect(sub_command)

        _collect(typer.main.get_command(app))
        _LONG_OPTIONS = names
    return _LONG_OPTIONS


# options whose value may be omitted (the argparse ``nargs='?'`` of FoBiS 3.7 and earlier): alone, or followed by
# another option, they take this value
OPTIONAL_VALUES = {"--preprocessor": "PreForM.py"}


def _normalize_args(args):
    """
    Normalise FoBiS legacy single-dash long options for Click/Typer.

    Rules applied to each token:
    - Single-dash multi-char option (-compiler, -mode, -get_output_name)
      → double-dash with underscores turned to hyphens (--compiler, --mode, --get-output-name),
      only if it is the name of an option: a value starting with a dash (--preproc -DFOO,
      --cflags -O2) is left unchanged
    - Double-dash option with underscores (--build_dir, --cflags_heritage)
      → double-dash with hyphens (--build-dir, --cflags-heritage)
    - Single-char short options (-f, -m, -q), values, and negative numbers
      are left unchanged.
    - An option of ``OPTIONAL_VALUES`` given without its value (alone, or followed by another option) gets its
      default (``--preprocessor`` -> ``--preprocessor PreForM.py``, as in the argparse CLI).
    - What follows ``--`` belongs to the program (``fobis run``, ``fobis test``) and is left unchanged; for ``run``
      it becomes ``--program-arg=WORD`` options, else Click takes its first word for the TARGET_NAME argument.
    """
    result = []
    for index, arg in enumerate(args):
        if arg == "--":
            tail = args[index + 1 :]
            if result[:1] == ["run"]:
                return _optional_values(result) + [f"--program-arg={word}" for word in tail]
            return _optional_values(result) + args[index:]
        if _MULTI_CHAR_OPT.match(arg) and arg[1:].replace("_", "-") in _long_options():
            result.append("--" + arg[1:].replace("_", "-"))
        elif arg.startswith("--") and len(arg) > 2:
            if "=" in arg:
                opt, val = arg[2:].split("=", 1)
                result.append("--" + opt.replace("_", "-") + "=" + val)
            else:
                result.append("--" + arg[2:].replace("_", "-"))
        else:
            result.append(arg)
    return _optional_values(result)


def _optional_values(args):
    """Insert the default value of an ``OPTIONAL_VALUES`` option given without one."""
    result = []
    for index, arg in enumerate(args):
        result.append(arg)
        following = args[index + 1] if index + 1 < len(args) else None
        if arg in OPTIONAL_VALUES and (following is None or following.startswith("-")):
            result.append(OPTIONAL_VALUES[arg])
    return result


# ---------------------------------------------------------------------------
# Typer application
# ---------------------------------------------------------------------------
app = typer.Typer(
    name="fobis",
    help="a Fortran Building System",
    no_args_is_help=True,
    add_completion=True,
    rich_markup_mode=None,
)


def _version_callback(value: bool):
    if value:
        from .. import __version__
        from ..FoBiSConfig import __appname__

        typer.echo(f"{__appname__} {__version__}")
        raise typer.Exit()


@app.callback()
def _app_callback(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-v",
            help="Show version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
):
    ctx.ensure_object(dict)


# ---------------------------------------------------------------------------
# Namespace factory
# ---------------------------------------------------------------------------


def _ns(**kwargs) -> argparse.Namespace:
    """Build an argparse.Namespace — preserves the duck-type expected by all downstream code."""
    return argparse.Namespace(**kwargs)
