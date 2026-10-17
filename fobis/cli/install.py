"""install.py — FoBiS.py ``install`` subcommand."""

from typing import Annotated

import typer

from ._app import _ns, app
from ._options import *


@app.command("install")
def cmd_install(
    ctx: typer.Context,
    repo: Annotated[
        str | None, typer.Argument(help='GitHub repository: "user/repo" shorthand or full HTTPS URL')
    ] = None,
    # fobos group
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    lmodes: LmodesOpt = False,
    # directories group (install variant)
    build_dir: BuildDirOpt = None,
    prefix: Annotated[
        str, typer.Option("--prefix", "-p", help="Prefix path where built objects are installed [default: ./]")
    ] = "./",
    bin: Annotated[str | None, typer.Option("--bin", help="Sub-directory for executables [default: bin/]")] = None,
    lib: Annotated[str | None, typer.Option("--lib", help="Sub-directory for libraries [default: lib/]")] = None,
    include: Annotated[
        str | None, typer.Option("--include", help="Sub-directory for module files [default: include/]")
    ] = None,
    # GitHub install options
    branch: Annotated[
        str | None, typer.Option("--branch", help="Branch to check out when installing from GitHub")
    ] = None,
    tag: Annotated[str | None, typer.Option("--tag", help="Tag to check out when installing from GitHub")] = None,
    rev: Annotated[
        str | None, typer.Option("--rev", help="Commit revision to check out when installing from GitHub")
    ] = None,
    update: Annotated[
        bool, typer.Option("--update", help="Re-fetch (git pull) before building and installing")
    ] = False,
    no_build: Annotated[bool, typer.Option("--no-build", help="Clone only — skip building and installing")] = False,
    deps_dir: Annotated[
        str | None, typer.Option("--deps-dir", help="Directory for cloning GitHub repositories [default: ~/.fobis/]")
    ] = None,
    # fancy group
    force_compile: ForceCompileOpt = False,
    colors: ColorsOpt = False,
    log: LogOpt = False,
    graph: GraphOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    jobs: JobsOpt = 1,
    makefile: MakefileOpt = None,
):
    """Install previously built files, or clone+build+install a GitHub-hosted FoBiS project."""
    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _ns(
        which="install",
        repo=repo,
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        lmodes=lmodes,
        build_dir=build_dir or "./",
        build_dir_explicit=build_dir is not None,
        prefix=prefix,
        bin=bin or "bin/",
        lib=lib or "lib/",
        include=include or "include/",
        # given on the command line: they win over the mode's bin and lib keys
        install_explicit=[name for name, value in (("bin", bin), ("lib", lib), ("include", include)) if value],
        branch=branch,
        tag=tag,
        rev=rev,
        update=update,
        no_build=no_build,
        deps_dir=deps_dir,
        force_compile=force_compile,
        colors=colors,
        log=log,
        graph=graph,
        quiet=quiet,
        verbose=verbose,
        jobs=jobs,
        makefile=makefile,
    )
