"""cache_cmd.py — FoBiS.py ``cache`` subcommand group.

Implements issue #172: list, clean, and inspect the build artifact cache.
"""

from __future__ import annotations

from typing import Annotated

import typer

# Create a sub-application for cache subcommands
cache_app = typer.Typer(name="cache", help="Manage the FoBiS build artifact cache.", no_args_is_help=True)


@cache_app.command("list")
def cmd_cache_list(
    cache_dir: Annotated[
        str | None,
        typer.Option("--cache-dir", help="Cache directory to inspect"),
    ] = None,
) -> None:
    """List all cached builds with metadata."""
    from ..Cache import BuildCache

    bc = BuildCache(cache_dir=cache_dir)
    entries = bc.list_entries()
    if entries:
        typer.echo(f"Cache directory: {bc.cache_dir}")
        typer.echo(bc.format_entry_table(entries))
    else:
        typer.echo(f"Cache is empty (or does not exist): {bc.cache_dir}")


@cache_app.command("clean")
def cmd_cache_clean(
    older_than: Annotated[
        int | None,
        typer.Option("--older-than", help="Delete entries older than N days"),
    ] = None,
    cache_dir: Annotated[
        str | None,
        typer.Option("--cache-dir", help="Cache directory to clean"),
    ] = None,
) -> None:
    """Purge stale cache entries."""
    from ..Cache import BuildCache

    bc = BuildCache(cache_dir=cache_dir)
    if older_than is not None:
        deleted = bc.evict_older_than(older_than)
        typer.echo(f"Deleted {deleted} cache entries older than {older_than} days.")
    else:
        import os
        import shutil

        if os.path.isdir(bc.cache_dir):
            shutil.rmtree(bc.cache_dir)
            typer.echo(f"Cache directory removed: {bc.cache_dir}")
        else:
            typer.echo("Cache directory does not exist.")


@cache_app.command("show")
def cmd_cache_show(
    dep_name: Annotated[str, typer.Argument(help="Dependency name to show cache status for")],
    cache_dir: Annotated[
        str | None,
        typer.Option("--cache-dir", help="Cache directory to inspect"),
    ] = None,
) -> None:
    """Show cache status for a specific dependency."""
    from ..Cache import BuildCache

    bc = BuildCache(cache_dir=cache_dir)
    entries = bc.list_entries()
    matching = [e for e in entries if e.dep_name == dep_name]
    if matching:
        typer.echo(bc.format_entry_table(matching))
    else:
        typer.echo(f"No cache entries found for dependency '{dep_name}'.")
