"""build.py — FoBiS.py ``build`` subcommand."""

from typing import Annotated

import typer

from ._app import _ns, app
from ._constants import __extensions_inc__, __extensions_parsed__
from ._options import *


@app.command("build")
def cmd_build(
    ctx: typer.Context,
    # fobos group
    fobos: FobosOpt = None,
    fobos_case_insensitive: FciOpt = False,
    mode: ModeOpt = None,
    lmodes: LmodesOpt = False,
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
    # preprocessor group
    preprocessor: PreprocessorOpt = None,
    preproc: PreprocOpt = None,
    preprocessor_args: PreprocessorArgsOpt = "",
    preprocessor_no_o: PreprocessorNoOOpt = False,
    preprocessor_dir: PreprocessorDirOpt = None,
    preprocessor_ext: PreprocessorExtOpt = None,
    # fancy group
    force_compile: ForceCompileOpt = False,
    colors: ColorsOpt = False,
    log: LogOpt = False,
    graph: GraphOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    jobs: JobsOpt = 1,
    makefile: MakefileOpt = None,
    json_output: JsonOpt = False,
    # --- new options (issues #165-#180) ---
    build_profile: Annotated[
        str | None,
        typer.Option(
            "--build-profile",
            help="Named build profile: debug, release, asan, coverage",
        ),
    ] = None,
    features: Annotated[
        str | None,
        typer.Option(
            "--features",
            help="Comma-separated list of feature flags to activate (defined in [features] section)",
        ),
    ] = None,
    no_default_features: Annotated[
        bool,
        typer.Option(
            "--no-default-features",
            help="Disable the default feature set defined in [features] default",
        ),
    ] = False,
    pre_build: Annotated[
        list[str] | None,
        typer.Option(
            "--pre-build",
            help="Rule(s) to execute before compilation (defined in [rule-X] sections)",
        ),
    ] = None,
    post_build: Annotated[
        list[str] | None,
        typer.Option(
            "--post-build",
            help="Rule(s) to execute after successful linking (defined in [rule-X] sections)",
        ),
    ] = None,
    no_auto_discover: Annotated[
        bool,
        typer.Option(
            "--no-auto-discover",
            help="Disable convention-based source directory auto-discovery",
        ),
    ] = False,
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Disable the build artifact cache"),
    ] = False,
    cache_dir: Annotated[
        str | None,
        typer.Option("--cache-dir", help="Override the default cache directory"),
    ] = None,
    list_profiles: Annotated[
        bool,
        typer.Option("--list-profiles", help="Print all known build profile flag sets and exit"),
    ] = False,
    examples: Annotated[
        bool,
        typer.Option("--examples", help="Also build [[example.*]] sections"),
    ] = False,
    target_filter: Annotated[
        str | None,
        typer.Option(
            "--target-filter", help="Build only the named target(s) from [[target.*]] sections (comma-separated)"
        ),
    ] = None,
):
    """Build all programs found or specific target(s)."""
    if list_profiles:
        from ..Profiles import list_profiles as _list_profiles

        typer.echo(_list_profiles())
        raise typer.Exit()

    ctx.ensure_object(dict)
    ctx.obj["cliargs"] = _ns(
        which="build",
        fobos=fobos,
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
        lmodes=lmodes,
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
        build_profile=build_profile or "",
        features=features or "",
        no_default_features=no_default_features,
        pre_build=pre_build or [],
        post_build=post_build or [],
        no_auto_discover=no_auto_discover,
        no_cache=no_cache,
        cache_dir=cache_dir,
        examples=examples,
        target_filter=[t.strip() for t in (target_filter or "").split(",") if t.strip()],
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
        preprocessor=preprocessor,
        preproc=preproc,
        preprocessor_args=preprocessor_args,
        preprocessor_no_o=preprocessor_no_o,
        preprocessor_dir=preprocessor_dir,
        preprocessor_ext=preprocessor_ext or [],
        force_compile=force_compile,
        colors=colors,
        log=log,
        graph=graph,
        quiet=quiet,
        verbose=verbose,
        jobs=jobs,
        makefile=makefile,
        json_output=json_output,
        active_features=[],
    )
