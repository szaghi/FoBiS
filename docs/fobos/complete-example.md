# Complete fobos example

A single annotated file showing every recognised section and option.
Copy it as a starting point and delete what you do not need.

```ini
# ─────────────────────────────────────────────────────────────────────────────
# [include]  — optional directive; pulls in sibling fobos files before any
#              other processing.  Useful for splitting a large fobos by
#              concern, sharing config across repos, or layering machine-local
#              overrides on top of committed defaults.
#              Paths resolve relative to this file's directory (after ${ENV}
#              and ~ expansion).  Prefix with '?' to mark optional (silent
#              if the file is absent).  On conflict: parent wins; among
#              siblings, later includes override earlier ones.
#              By convention, included fragments use the `.fobos` extension
#              (any path works; convention helps editors and globbing).
# ─────────────────────────────────────────────────────────────────────────────
# [include]
# paths = templates.fobos                       ; required — error if missing
#         ?${HOME}/.fobis/local.fobos           ; optional — skipped if absent

# ─────────────────────────────────────────────────────────────────────────────
# [modes]  — list every named mode section defined below.
#            Run: fobis build --mode <name>
#            List: fobis build --lmodes
# ─────────────────────────────────────────────────────────────────────────────
[modes]
modes = debug release

# ─────────────────────────────────────────────────────────────────────────────
# [project]  — optional metadata; consumed by `fobis introspect --projectinfo`
#              and used to generate pkg-config files.
#              `version` may be a literal string or a path to a file that
#              contains the version string (relative to the git repo root).
# ─────────────────────────────────────────────────────────────────────────────
[project]
; short machine-readable name
name       = myproject
; or: src/version.inc
version    = 1.2.0
; one-line description
summary    = A modern Fortran solver library
authors    = Alice Smith
             Bob Jones                            ; one author per line
repository = https://github.com/example/myproject
website    = https://example.github.io/myproject
email      = alice@example.com
year       = 2026

# ─────────────────────────────────────────────────────────────────────────────
# [features]  — named compile-time option sets.
#   default  = features active when none are explicitly requested
#   All other keys: name = flags (routed to cflags/lflags automatically)
#   @-prefixed tokens reference other features (recursive composite expansion).
#   Well-known implicit names (openmp/omp, mpi, coarray, coverage, profile,
#   openmp_offload/omp_offload) do NOT need an entry here — they resolve
#   through the compiler table automatically.
# ─────────────────────────────────────────────────────────────────────────────
[features]
; active by default
default  = release mpi
; -D → cflags
release  = -O3 -DNDEBUG
; -fcheck=all → cflags
debug    = -g -O0 -fcheck=all
mpi      = -DUSE_MPI
; -I → cflags
hdf5     = -DUSE_HDF5 -I/opt/hdf5/include
netcdf   = -DUSE_NETCDF -I/opt/netcdf/include
; define only; use --features openmp for the compiler flag
omp_defs = -DUSE_OMP

# Composite features compose other features via @-references.
; activating prod pulls in 3 leaves
prod     = @release @mpi @hdf5
dev      = @debug @mpi

# ─────────────────────────────────────────────────────────────────────────────
# [feature:NAME]  — per-feature constraints (optional sibling sections).
#   flags     = optional; alternative to [features] NAME = ... (must not duplicate)
#   requires  = space-separated names auto-activated when this feature is active
#   conflicts = space-separated names that cannot coexist (hard error if both active)
# ─────────────────────────────────────────────────────────────────────────────
[feature:hdf5]
; activating hdf5 auto-activates mpi
requires = mpi

[feature:static]
; flags here instead of [features]
flags     = -static
; --features static,shared → exit 1
conflicts = shared

# ─────────────────────────────────────────────────────────────────────────────
# [feature-group:NAME]  — mutually-exclusive set of features (optional).
#   members = space-separated feature names in the group
#   default = optional; when set, auto-activated when no member is active
#             (omit default for at-most-one semantics)
# ─────────────────────────────────────────────────────────────────────────────
[feature-group:precision]
members = single double quad
; fills the group if empty
default = double

# ─────────────────────────────────────────────────────────────────────────────
# [varsets] + [varset:NAME]  — named bundles of $variable bindings selected
#   at invocation time via --varset.  Eliminates per-cluster mode duplication.
#   $variables in [varset:NAME] do NOT leak into the implicit global pool.
#   [varsets] default = NAME ...   — fobos-declared fallback (optional)
# ─────────────────────────────────────────────────────────────────────────────
[varsets]
; applied when --varset is omitted
default = local

[varset:local]
$HDF5_PREFIX = lib/hdf5/develop/nvf/26.1
$ARCH        = cc89

[varset:hpc1]
$HDF5_PREFIX = /opt/spack/.../hdf5-1.14.3
$ARCH        = cc80

# ─────────────────────────────────────────────────────────────────────────────
# [dependencies]  — GitHub-hosted build dependencies fetched by `fobis fetch`.
#   deps_dir = local directory for cloned repositories (default: .fobis_deps)
#   Each entry: name = URL [:: branch=X | tag=X | rev=X | semver=X]
#                          [:: mode=X] [:: use=sources|fobos] [:: dev]
#           or: name = path=DIR [:: mode=X] [:: use=sources|fobos] [:: dev]
# ─────────────────────────────────────────────────────────────────────────────
[dependencies]
; where to clone (same as --deps-dir)
deps_dir = .fobis_deps
penf     = https://github.com/szaghi/PENF :: tag=v1.5.0
stdlib   = https://github.com/fortran-lang/stdlib :: semver=>=0.5,<1.0 :: use=fobos :: mode=gnu
jsonfort = https://github.com/jacobwilliams/json-fortran :: branch=main :: use=fobos
; user/repo shorthand resolves to GitHub
utils    = szaghi/fortran-utils :: rev=a1b2c3d
; a local directory, relative to this fobos: no fetch, no pin
mylib    = path=../mylib

# ─────────────────────────────────────────────────────────────────────────────
# [externals]  — system library resolution. Each entry is `name = auto | /prefix`.
#   auto     → probe pkg-config / wrapper scripts (mpi, hdf5, netcdf, blas,
#              lapack, fftw/fftw3, openblas)
#   /prefix  → probe <prefix>/include and <prefix>/lib explicitly
#   Activate per mode with `externals = name1 name2` (see the mode section below).
# ─────────────────────────────────────────────────────────────────────────────
[externals]
; probe mpifort/mpif90 -show
mpi    = auto
; pkg-config hdf5_fortran or h5fc -show
hdf5   = auto
; explicit prefix: /opt/netcdf/{include,lib}
netcdf = /opt/netcdf

# ─────────────────────────────────────────────────────────────────────────────
# [test]  — defaults for `fobis test`.
# ─────────────────────────────────────────────────────────────────────────────
[test]
; directory scanned for test programs
test_dir = tests
; only run tests tagged ! fobis: suite=unit
suite    = unit
; seconds before a test is killed
timeout  = 120

# ─────────────────────────────────────────────────────────────────────────────
# [coverage]  — defaults for `fobis coverage`.
# ─────────────────────────────────────────────────────────────────────────────
[coverage]
; where HTML/XML report is written
output_dir = coverage/
; filter coverage to this directory
source_dir = src/
; exit 1 if line coverage < N %
fail_under = 75
; glob patterns to exclude (one per line)
exclude    = tests/*
             examples/*

# ─────────────────────────────────────────────────────────────────────────────
# Build mode sections — one section per named mode.
# All option names mirror the CLI long flags (without --).
# ─────────────────────────────────────────────────────────────────────────────

# ── shared template (inherited by debug and release via template = base) ──────
[base]
; gnu intel intel_nextgen nvfortran nag ibm amd pgi g95 custom
compiler               = gnu
; compiler executable (required for custom)
fc                     = gfortran
; module directory switch (required for custom)
modsw                  = -J
; source root (space-separated list)
src                    = ./src/
; where executables are placed
build_dir              = ./build/
; compiled object files
obj_dir                = ./obj/
; Fortran .mod interface files
mod_dir                = ./mod/
; external library search paths (space-sep)
lib_dir                = /usr/local/lib
; include file search paths (space-sep)
include                = /usr/local/include
; directories excluded from source scan
exclude_dirs           = ./vendor/
; do not recurse into subdirectories
disable_recursive_search = false
; specific source file to build
target                 = src/main.F90
; output executable name
output                 = myapp
; source files to skip (space-separated)
exclude                = src/scratch.F90
; external libraries (full paths)
libs                   = /opt/mylib/libfoo.a
; volatile libs — rebuild when changed
vlibs                  = /opt/mylib/libvolatile.a
; library names (passed as -l to linker)
ext_libs               = lapack blas
; volatile library names
ext_vlibs              = myvolatile
; interdependent fobos files (path:mode)
dependon               = ../otherlib/fobos:release
; include file extensions (space-sep)
inc                    = .inc .INC .h .H
; Fortran source extensions to scan
extensions             = .F90 .f90 .F .f
; compile all parsed sources, not just programs
build_all              = false
; build a library: static or shared
mklib                  = static
; archiver executable
ar                     = ar
; archiver flags
arflags                = -rcs
; ranlib executable; set to empty to skip
ranlib                 = ranlib
; use MPI compiler wrapper
mpi                    = false
; enable OpenMP
openmp                 = false
; enable OpenMP offload
openmp_offload         = false
; enable coarrays
coarray                = false
; coverage instrumentation (--coverage)
coverage               = false
; profiling instrumentation (-pg)
profile                = false
; force full rebuild when cflags change
cflags_heritage        = false
; save build info for `fobis install`
track_build            = false
; source preprocessor executable
preprocessor           = PreForM.py
; preprocessor macro flags
preproc                = -DSOME_MACRO
; extra flags passed to the preprocessor
preprocessor_args      = --output-dir .preproc
; omit -o from the preprocessor command
preprocessor_no_o      = false
; keep preprocessed sources in this dir
preprocessor_dir       = .preproc
; file extensions to preprocess
preprocessor_ext       = .pf .PF
; named flag preset: debug release asan coverage
build_profile          = debug
; space- or comma-separated features active in this mode
features               = release mpi
; named [varset:NAME] applied for this mode (see Varsets)
varset                 = local
; modules to skip from "unreachable" warnings (see Compilers)
intrinsic_modules      = hdf5 hdf5_hl
; disable src/source/app/ auto-detection
no_auto_discover       = false
; disable the build artifact cache
no_cache               = false
; override default cache directory
cache_dir              = .fobis_cache
; rule(s) to run before compilation
pre_build              = gen_version
; rule(s) to run after successful link
post_build             = run_tests
; entries from [externals] to apply
externals              = hdf5 netcdf
; generate a .pc file on build
pkgconfig              = false
; package name in the .pc file
pkgconfig_name         = myproject
; description in the .pc file
pkgconfig_desc         = My Fortran library
pkgconfig_url          = https://github.com/example/myproject
; Requires: line in the .pc file
pkgconfig_req          = hdf5
; Requires.private: line in the .pc file
pkgconfig_req_priv     = zlib
; coloured terminal output
colors                 = false
; write a build log file
log                    = false
; write a graphviz dependency graph
graph                  = false
; suppress informational output
quiet                  = false
; maximum diagnostic verbosity
verbose                = false
; parallel compile jobs
jobs                   = 4

# ── local variables — reused via $name substitution ──────────────────────────
$opt_flags             = -O2 -march=native        ; define once, reference as $opt_flags

# ── debug mode ───────────────────────────────────────────────────────────────
[debug]
; inherit all options from [base]
template               = base
cflags                 = -c -O0 -g -Wall -Wextra
; no extra link flags
lflags                 =
; prepends: -fcheck=all -fbacktrace -ffpe-trap=...
build_profile          = debug
build_dir              = ./build/debug/

# ── release mode ─────────────────────────────────────────────────────────────
[release]
template               = base
; $opt_flags substituted from variable above
cflags                 = -c $opt_flags
lflags                 =
; prepends: -O3 -funroll-loops
build_profile          = release
build_dir              = ./build/release/

# ─────────────────────────────────────────────────────────────────────────────
# [target.NAME]  — per-target overrides; built with --target-filter NAME.
#   source = source file for this target (required)
#   output = output binary name (required)
#   Any build option can be added to override the base mode.
# ─────────────────────────────────────────────────────────────────────────────
[target.solver]
source    = src/solver.F90
output    = solver
cflags    = -c -O3 -DSOLVER_STANDALONE

# ─────────────────────────────────────────────────────────────────────────────
# [example.NAME]  — same syntax as target.*; built with --examples.
# ─────────────────────────────────────────────────────────────────────────────
[example.demo]
source    = examples/demo.F90
output    = demo
build_dir = ./build/examples/

# ─────────────────────────────────────────────────────────────────────────────
# [rule-NAME]  — custom shell commands; run with `fobis rule --execute NAME`
#               or referenced by pre_build / post_build.
#   help     = one-line description shown by `fobis rule --list`
#   quiet    = suppress command echo
#   log      = write errors to rules_errors.log
#   rule1 … ruleN = shell commands (executed in alphabetical key order)
# ─────────────────────────────────────────────────────────────────────────────
[rule-gen_version]
help  = Generate src/version.inc from git tag
rule1 = git describe --tags --abbrev=0 > src/version.inc

[rule-run_tests]
help  = Run the test suite after a successful build
rule1 = ./build/release/test_suite --verbose
quiet = false
log   = true

[rule-docs]
help  = Build the VitePress documentation site
rule1 = npm run docs:build
```
