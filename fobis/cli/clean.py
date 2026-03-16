"""clean.py — FoBiS.py ``clean`` subcommand."""

import typer
from typing_extensions import Annotated

from ._app import _ns, app
from ._constants import __extensions_inc__, __extensions_parsed__
from ._options import *


@app.command("clean")
def cmd_clean(
    ctx: typer.Context,
    # fobos group
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    lmodes: LmodesOpt = False,
    print_fobos_template: PrintFobosTemplateOpt = False,
    # clean-specific
    only_obj: Annotated[bool, typer.Option("--only-obj", help="Clean only compiled objects and not built targets")] = False,
    only_target: Annotated[bool, typer.Option("--only-target", help="Clean only built targets and not compiled objects")] = False,
    # compiler group
    compiler: CompilerOpt = "gnu",
    fc: FcOpt = None,
    cflags: CflagsOpt = None,
    lflags: LflagsOpt = None,
    modsw: ModswOpt = None,
    mpi: MpiOpt = False,
    openmp: OpenmpOpt = False,
    openmp_offload: OpenmpOffloadOpt = False,
    coarray: CoarrayOpt = False,
    coverage: CoverageOpt = False,
    profile: ProfileOpt = False,
    mklib: MklibOpt = None,
    ar: ArOpt = "ar",
    arflags: ArflagsOpt = "-rcs",
    ranlib: RanlibOpt = "ranlib",
    cflags_heritage: CflagsHeritageOpt = False,
    track_build: TrackBuildOpt = False,
    # directories group
    src: SrcOpt = None,
    build_dir: BuildDirOpt = "./",
    obj_dir: ObjDirOpt = "./obj/",
    mod_dir: ModDirOpt = "./mod/",
    lib_dir: LibDirOpt = None,
    include: IncludeListOpt = None,
    exclude_dirs: ExcludeDirsOpt = None,
    disable_recursive_search: DisableRecursiveSearchOpt = False,
    # files group
    target: TargetOpt = None,
    output: OutputOpt = None,
    exclude: ExcludeOpt = None,
    libs: LibsOpt = None,
    vlibs: VlibsOpt = None,
    ext_libs: ExtLibsOpt = None,
    ext_vlibs: ExtVlibsOpt = None,
    dependon: DependonOpt = None,
    inc: IncOpt = None,
    extensions: ExtensionsOpt = None,
    build_all: BuildAllOpt = False,
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
    """Clean project: remove all OBJs and MODs files. Use carefully."""
    ctx.ensure_object(dict)
    if only_obj and only_target:
        typer.echo("Error: --only-obj and --only-target are mutually exclusive.", err=True)
        raise typer.Exit(1)
    ctx.obj["cliargs"] = _ns(
        which="clean",
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        lmodes=lmodes,
        print_fobos_template=print_fobos_template,
        only_obj=only_obj,
        only_target=only_target,
        compiler=compiler.lower(),
        fc=fc,
        cflags=cflags,
        lflags=lflags,
        modsw=modsw,
        mpi=mpi,
        openmp=openmp,
        openmp_offload=openmp_offload,
        coarray=coarray,
        coverage=coverage,
        profile=profile,
        mklib=mklib,
        ar=ar,
        arflags=arflags,
        ranlib=ranlib,
        cflags_heritage=cflags_heritage,
        track_build=track_build,
        src=src or ["./"],
        build_dir=build_dir,
        obj_dir=obj_dir,
        mod_dir=mod_dir,
        lib_dir=lib_dir or [],
        include=include or [],
        exclude_dirs=exclude_dirs or [],
        disable_recursive_search=disable_recursive_search,
        target=target,
        output=output,
        exclude=exclude or [],
        libs=libs or [],
        vlibs=vlibs or [],
        ext_libs=ext_libs or [],
        ext_vlibs=ext_vlibs or [],
        dependon=dependon or [],
        inc=inc or list(__extensions_inc__),
        extensions=extensions or list(__extensions_parsed__),
        build_all=build_all,
        force_compile=force_compile,
        colors=colors,
        log=log,
        graph=graph,
        quiet=quiet,
        verbose=verbose,
        jobs=jobs,
        makefile=makefile,
    )
