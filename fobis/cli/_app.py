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

import typer
from typing_extensions import Annotated

# ---------------------------------------------------------------------------
# Argument normaliser — preserves backward compat with argparse-style options
# ---------------------------------------------------------------------------
_MULTI_CHAR_OPT = re.compile(r"^-[A-Za-z][A-Za-z0-9_-]+$")


def _normalize_args(args):
    """
    Normalise FoBiS legacy single-dash long options for Click/Typer.

    Rules applied to each token:
    - Single-dash multi-char option (-compiler, -mode, -get_output_name)
      → double-dash with underscores turned to hyphens (--compiler, --mode, --get-output-name)
    - Double-dash option with underscores (--build_dir, --cflags_heritage)
      → double-dash with hyphens (--build-dir, --cflags-heritage)
    - Single-char short options (-f, -m, -q), values, and negative numbers
      are left unchanged.
    """
    result = []
    for arg in args:
        if _MULTI_CHAR_OPT.match(arg):
            result.append("--" + arg[1:].replace("_", "-"))
        elif arg.startswith("--") and len(arg) > 2:
            if "=" in arg:
                opt, val = arg[2:].split("=", 1)
                result.append("--" + opt.replace("_", "-") + "=" + val)
            else:
                result.append("--" + arg[2:].replace("_", "-"))
        else:
            result.append(arg)
    return result


# ---------------------------------------------------------------------------
# Typer application
# ---------------------------------------------------------------------------
app = typer.Typer(
    name="FoBiS.py",
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
