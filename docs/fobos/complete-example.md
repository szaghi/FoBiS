# Complete fobos example

A single annotated file showing every recognised section and option.
Copy it as a starting point and delete what you do not need.

```ini
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
name       = myproject                            ; short machine-readable name
version    = 1.2.0                                ; or: src/version.inc
summary    = A modern Fortran solver library      ; one-line description
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
#   Well-known implicit names (openmp/omp, mpi, coarray, coverage, profile,
#   openmp_offload/omp_offload) do NOT need an entry here — they resolve
#   through the compiler table automatically.
# ─────────────────────────────────────────────────────────────────────────────
[features]
default  = mpi                                    ; active by default
mpi      = -DUSE_MPI                              ; -D → cflags
hdf5     = -DUSE_HDF5 -I/opt/hdf5/include        ; -I → cflags
netcdf   = -DUSE_NETCDF -I/opt/netcdf/include
omp_defs = -DUSE_OMP                              ; define only; use --features openmp for the compiler flag

# ─────────────────────────────────────────────────────────────────────────────
# [dependencies]  — GitHub-hosted build dependencies fetched by `fobis fetch`.
#   deps_dir = local directory for cloned repositories (default: .fobis_deps)
#   Each entry: name = URL [:: branch=X | tag=X | rev=X | semver=X]
#                          [:: mode=X] [:: use=sources|fobos]
# ─────────────────────────────────────────────────────────────────────────────
[dependencies]
deps_dir = .fobis_deps                            ; where to clone (same as --deps-dir)
penf     = https://github.com/szaghi/PENF :: tag=v1.5.0
stdlib   = https://github.com/fortran-lang/stdlib :: semver=>=0.5,<1.0 :: use=fobos :: mode=gnu
jsonfort = https://github.com/jacobwilliams/json-fortran :: branch=main :: use=fobos
utils    = szaghi/fortran-utils :: rev=a1b2c3d    ; user/repo shorthand resolves to GitHub

# ─────────────────────────────────────────────────────────────────────────────
# [externals]  — system library resolution via pkg-config or MPI auto-detect.
#   pkg-config = space-separated list of pkg-config package names
#   mpi-auto   = true → probe mpifort/mpif90 wrappers for compile+link flags
# ─────────────────────────────────────────────────────────────────────────────
[externals]
pkg-config = hdf5 netcdf                          ; runs `pkg-config --cflags --libs`
mpi-auto   = false                                ; set true to probe MPI wrappers

# ─────────────────────────────────────────────────────────────────────────────
# [test]  — defaults for `fobis test`.
# ─────────────────────────────────────────────────────────────────────────────
[test]
test_dir = tests                                  ; directory scanned for test programs
suite    = unit                                   ; only run tests tagged ! fobis: suite=unit
timeout  = 120                                    ; seconds before a test is killed
compiler = gnu                                    ; override compiler for test builds
cflags   = -c -O0 -g                             ; extra cflags for test compilation

# ─────────────────────────────────────────────────────────────────────────────
# [coverage]  — defaults for `fobis coverage`.
# ─────────────────────────────────────────────────────────────────────────────
[coverage]
output_dir = coverage/                            ; where HTML/XML report is written
source_dir = src/                                 ; filter coverage to this directory
fail_under = 75                                   ; exit 1 if line coverage < N %
exclude    = tests/*                              ; glob patterns to exclude (one per line)
             examples/*

# ─────────────────────────────────────────────────────────────────────────────
# Build mode sections — one section per named mode.
# All option names mirror the CLI long flags (without --).
# ─────────────────────────────────────────────────────────────────────────────

# ── shared template (inherited by debug and release via template = base) ──────
[base]
compiler               = gnu                      ; gnu intel intel_nextgen nvfortran nag ibm amd pgi g95 custom
fc                     = gfortran                 ; compiler executable (required for custom)
modsw                  = -J                       ; module directory switch (required for custom)
src                    = ./src/                   ; source root (space-separated list)
build_dir              = ./build/                 ; where executables are placed
obj_dir                = ./obj/                   ; compiled object files
mod_dir                = ./mod/                   ; Fortran .mod interface files
lib_dir                = /usr/local/lib           ; external library search paths (space-sep)
include                = /usr/local/include       ; include file search paths (space-sep)
exclude_dirs           = ./vendor/                ; directories excluded from source scan
disable_recursive_search = false                  ; do not recurse into subdirectories
target                 = src/main.F90             ; specific source file to build
output                 = myapp                    ; output executable name
exclude                = src/scratch.F90          ; source files to skip (space-separated)
libs                   = /opt/mylib/libfoo.a      ; external libraries (full paths)
vlibs                  = /opt/mylib/libvolatile.a ; volatile libs — rebuild when changed
ext_libs               = lapack blas              ; library names (passed as -l to linker)
ext_vlibs              = myvolatile               ; volatile library names
dependon               = ../otherlib/fobos:release ; interdependent fobos files (path:mode)
inc                    = .inc .INC .h .H          ; include file extensions (space-sep)
extensions             = .F90 .f90 .F .f          ; Fortran source extensions to scan
build_all              = false                    ; compile all parsed sources, not just programs
mklib                  = static                   ; build a library: static or shared
ar                     = ar                       ; archiver executable
arflags                = -rcs                     ; archiver flags
ranlib                 = ranlib                   ; ranlib executable; set to empty to skip
mpi                    = false                    ; use MPI compiler wrapper
openmp                 = false                    ; enable OpenMP
openmp_offload         = false                    ; enable OpenMP offload
coarray                = false                    ; enable coarrays
coverage               = false                    ; coverage instrumentation (--coverage)
profile                = false                    ; profiling instrumentation (-pg)
cflags_heritage        = false                    ; force full rebuild when cflags change
track_build            = false                    ; save build info for `fobis install`
preprocessor           = PreForM.py               ; source preprocessor executable
preproc                = -DSOME_MACRO             ; preprocessor macro flags
preprocessor_args      = --output-dir .preproc    ; extra flags passed to the preprocessor
preprocessor_no_o      = false                    ; omit -o from the preprocessor command
preprocessor_dir       = .preproc                 ; keep preprocessed sources in this dir
preprocessor_ext       = .pf .PF                  ; file extensions to preprocess
build_profile          = debug                    ; named flag preset: debug release asan coverage
features               =                          ; comma-separated features to activate
no_auto_discover       = false                    ; disable src/source/app/ auto-detection
no_cache               = false                    ; disable the build artifact cache
cache_dir              = .fobis_cache             ; override default cache directory
pre_build              = gen_version              ; rule(s) to run before compilation
post_build             = run_tests                ; rule(s) to run after successful link
externals              = hdf5 netcdf              ; entries from [externals] to apply
pkgconfig              = false                    ; generate a .pc file on build
pkgconfig_name         = myproject                ; package name in the .pc file
pkgconfig_desc         = My Fortran library       ; description in the .pc file
pkgconfig_url          = https://github.com/example/myproject
pkgconfig_req          = hdf5                     ; Requires: line in the .pc file
pkgconfig_req_priv     = zlib                     ; Requires.private: line in the .pc file
colors                 = false                    ; coloured terminal output
log                    = false                    ; write a build log file
graph                  = false                    ; write a graphviz dependency graph
quiet                  = false                    ; suppress informational output
verbose                = false                    ; maximum diagnostic verbosity
jobs                   = 4                        ; parallel compile jobs

# ── local variables — reused via $name substitution ──────────────────────────
$opt_flags             = -O2 -march=native        ; define once, reference as $opt_flags

# ── debug mode ───────────────────────────────────────────────────────────────
[debug]
template               = base                     ; inherit all options from [base]
cflags                 = -c -O0 -g -Wall -Wextra
lflags                 =                          ; no extra link flags
build_profile          = debug                    ; prepends: -fcheck=all -fbacktrace -ffpe-trap=...
build_dir              = ./build/debug/

# ── release mode ─────────────────────────────────────────────────────────────
[release]
template               = base
cflags                 = -c $opt_flags            ; $opt_flags substituted from variable above
lflags                 =
build_profile          = release                  ; prepends: -O3 -funroll-loops
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
