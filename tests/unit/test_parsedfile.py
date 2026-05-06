"""Unit tests for fobis.ParsedFile — uses tmp_path, no compiler needed."""

import pytest

from fobis.ParsedFile import ParsedFile


def _write(tmp_path, filename, content):
    """Write *content* to *filename* inside *tmp_path* and return the path."""
    p = tmp_path / filename
    p.write_text(content, encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# Basic attribute initialisation
# ---------------------------------------------------------------------------


def test_init_basename(tmp_path):
    f = _write(tmp_path, "foo.f90", "")
    pf = ParsedFile(name=f)
    assert pf.basename == "foo"


def test_init_extension(tmp_path):
    f = _write(tmp_path, "bar.F90", "")
    pf = ParsedFile(name=f)
    assert pf.extension == ".F90"


def test_init_flags_default_false(tmp_path):
    f = _write(tmp_path, "x.f90", "")
    pf = ParsedFile(name=f)
    assert not pf.program
    assert not pf.module
    assert not pf.submodule
    assert not pf.include


# ---------------------------------------------------------------------------
# program detection
# ---------------------------------------------------------------------------


def test_parse_detects_program(tmp_path):
    src = "program main\n  implicit none\nend program main\n"
    f = _write(tmp_path, "main.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    assert pf.program


def test_parse_detects_program_uppercase(tmp_path):
    src = "PROGRAM MAIN\nEND PROGRAM MAIN\n"
    f = _write(tmp_path, "main.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    assert pf.program


def test_parse_detects_program_with_leading_spaces(tmp_path):
    src = "   program foo\nend program foo\n"
    f = _write(tmp_path, "foo.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    assert pf.program


# ---------------------------------------------------------------------------
# module detection
# ---------------------------------------------------------------------------


def test_parse_detects_module(tmp_path):
    src = "module mymod\nimplicit none\nend module mymod\n"
    f = _write(tmp_path, "mymod.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    assert pf.module
    assert "mymod" in pf.module_names


def test_parse_module_name_case_insensitive(tmp_path):
    src = "MODULE MyMod\nEND MODULE MyMod\n"
    f = _write(tmp_path, "mymod.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    assert pf.module
    assert "MyMod" in pf.module_names


def test_parse_multiple_modules(tmp_path):
    src = "module mod_a\nend module mod_a\nmodule mod_b\nend module mod_b\n"
    f = _write(tmp_path, "mods.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    assert "mod_a" in pf.module_names
    assert "mod_b" in pf.module_names


# ---------------------------------------------------------------------------
# use statement extraction
# ---------------------------------------------------------------------------


def test_parse_use_extracts_dependency(tmp_path):
    src = "module user\n  use other_mod\nend module user\n"
    f = _write(tmp_path, "user.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name for d in pf.dependencies]
    assert "other_mod" in dep_names


def test_parse_use_with_colon_syntax(tmp_path):
    src = "module user\n  use, intrinsic :: iso_fortran_env\n  use mymod\nend module user\n"
    f = _write(tmp_path, "user.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name for d in pf.dependencies]
    # iso_fortran_env is intrinsic — must be filtered out
    assert not any("iso_fortran_env" in n.lower() for n in dep_names)
    assert "mymod" in dep_names


def test_parse_use_with_double_colon(tmp_path):
    src = "program p\n  use :: some_module\nend program p\n"
    f = _write(tmp_path, "p.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name for d in pf.dependencies]
    assert "some_module" in dep_names


def test_parse_use_only_extracts_module_name(tmp_path):
    src = "program p\n  use mymod, only: sub1, sub2\nend program p\n"
    f = _write(tmp_path, "p.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name for d in pf.dependencies]
    assert "mymod" in dep_names


# ---------------------------------------------------------------------------
# Intrinsic module filtering
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "intrinsic",
    [
        "iso_fortran_env",
        "ISO_FORTRAN_ENV",
        "iso_c_binding",
        "IEEE_EXCEPTIONS",
        "ieee_arithmetic",
        "ieee_features",
    ],
)
def test_parse_filters_intrinsic_modules(tmp_path, intrinsic):
    src = f"module m\n  use {intrinsic}\nend module m\n"
    f = _write(tmp_path, "m.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name.lower() for d in pf.dependencies]
    assert intrinsic.lower() not in dep_names


def test_parse_filters_mpi_module(tmp_path):
    src = "module m\n  use mpi\nend module m\n"
    f = _write(tmp_path, "m.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name.lower() for d in pf.dependencies]
    assert "mpi" not in dep_names


def test_parse_filters_omp_lib(tmp_path):
    src = "module m\n  use omp_lib\nend module m\n"
    f = _write(tmp_path, "m.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name.lower() for d in pf.dependencies]
    assert "omp_lib" not in dep_names


# ---------------------------------------------------------------------------
# submodule syntax
# ---------------------------------------------------------------------------


def test_parse_submodule_detected(tmp_path):
    src = "submodule (parent) child\nend submodule child\n"
    f = _write(tmp_path, "child.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    assert pf.submodule
    assert "child" in pf.submodule_names


def test_parse_submodule_adds_parent_dependency(tmp_path):
    src = "submodule (parent) child\nend submodule child\n"
    f = _write(tmp_path, "child.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name for d in pf.dependencies]
    assert "parent" in dep_names


# ---------------------------------------------------------------------------
# include statement extraction
# ---------------------------------------------------------------------------


def test_parse_include_dependency(tmp_path):
    src = 'program p\n  include "my_include.h"\nend program p\n'
    f = _write(tmp_path, "p.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name for d in pf.dependencies]
    assert "my_include.h" in dep_names


def test_parse_include_single_quotes(tmp_path):
    src = "program p\n  include 'defs.inc'\nend program p\n"
    f = _write(tmp_path, "p.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name for d in pf.dependencies]
    assert "defs.inc" in dep_names


# ---------------------------------------------------------------------------
# nomodlib detection
# ---------------------------------------------------------------------------


def test_parse_nomodlib_for_plain_f90(tmp_path):
    """A .f90 file that contains no program/module/submodule → nomodlib."""
    src = "subroutine foo()\nend subroutine foo\n"
    f = _write(tmp_path, "util.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    assert pf.nomodlib


def test_parse_not_nomodlib_when_module_present(tmp_path):
    src = "module mymod\nend module mymod\n"
    f = _write(tmp_path, "mymod.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    assert not pf.nomodlib


# ---------------------------------------------------------------------------
# Preprocessor trigger: _needs_preprocessing
# ---------------------------------------------------------------------------


def test_needs_preprocessing_uppercase_extensions():
    """Uppercase Fortran extensions are the standard 'needs cpp' signal."""
    from fobis.ParsedFile import _needs_preprocessing

    inc: list[str] = []
    assert _needs_preprocessing(".F90", inc) is True
    assert _needs_preprocessing(".F03", inc) is True
    assert _needs_preprocessing(".F08", inc) is True
    assert _needs_preprocessing(".F", inc) is True
    assert _needs_preprocessing(".FPP", inc) is True
    assert _needs_preprocessing(".F77", inc) is True  # digits don't break .isupper()


def test_needs_preprocessing_lowercase_extensions():
    """Lowercase Fortran extensions skip cpp by convention."""
    from fobis.ParsedFile import _needs_preprocessing

    inc: list[str] = []
    assert _needs_preprocessing(".f90", inc) is False
    assert _needs_preprocessing(".f", inc) is False
    assert _needs_preprocessing(".f03", inc) is False


def test_needs_preprocessing_mixed_case_skipped():
    """Mixed-case extensions (rare/non-conventional) are not auto-preprocessed."""
    from fobis.ParsedFile import _needs_preprocessing

    inc: list[str] = []
    assert _needs_preprocessing(".Fpp", inc) is False
    assert _needs_preprocessing(".F90x", inc) is False  # 'x' lowercase


def test_needs_preprocessing_inc_list_overrides():
    """An extension explicitly listed in `inc` always triggers preprocessing."""
    from fobis.ParsedFile import _needs_preprocessing

    assert _needs_preprocessing(".inc", [".inc"]) is True
    assert _needs_preprocessing(".h", [".h", ".H"]) is True
    # Lowercase included via inc list is also triggered.
    assert _needs_preprocessing(".f90", [".f90"]) is True


def test_needs_preprocessing_no_extension():
    """Files without an extension (e.g. 'README') never trigger cpp."""
    from fobis.ParsedFile import _needs_preprocessing

    assert _needs_preprocessing("", [".F90"]) is False
    assert _needs_preprocessing(".", [".F90"]) is False  # just a dot


# ---------------------------------------------------------------------------
# Preprocessor expansion: cpp macro `use MACRO_NAME` resolves before parsing
# ---------------------------------------------------------------------------


def test_parse_F90_expands_use_macro(tmp_path):
    """A `use MACRO_NAME` line where MACRO_NAME is a cpp macro must resolve.

    Without preprocessing the parser would record DEVMODULE as a phantom
    dependency module name; with preprocessing on .F90, cpp expands
    DEVMODULE to the real module name and the parser sees the expanded
    form.

    Avoid intrinsic Fortran module names (openacc, iso_c_binding, omp_lib,
    …) as the macro target — the parser filters those out so the test
    can't observe them in `dependencies`.  Use a project-local name.
    """
    import shutil

    if shutil.which("cpp") is None:
        pytest.skip("cpp not available in PATH")
    src = "#define DEVMODULE backend_acc\nmodule mymod\nuse :: DEVMODULE\nend module mymod\n"
    f = _write(tmp_path, "src.F90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name.lower() for d in pf.dependencies]
    # The macro got expanded — parser sees 'backend_acc', not 'devmodule'.
    assert "backend_acc" in dep_names
    assert "devmodule" not in dep_names


def test_parse_F90_expands_ifdef_guarded_use(tmp_path):
    """`#ifdef _OAC` / use ... / `#endif` is gated by cpp expansion."""
    import shutil

    if shutil.which("cpp") is None:
        pytest.skip("cpp not available in PATH")
    src = "module mymod\n#ifdef _OAC\nuse :: backend_acc\n#else\nuse :: backend_seq\n#endif\nend module mymod\n"
    f = _write(tmp_path, "src.F90", src)
    # With _OAC defined: backend_acc branch wins.
    pf = ParsedFile(name=f)
    pf.parse(preproc="-D_OAC")
    dep_names = [d.name.lower() for d in pf.dependencies]
    assert "backend_acc" in dep_names
    assert "backend_seq" not in dep_names

    # With _OAC undefined: backend_seq branch wins.
    pf2 = ParsedFile(name=f)
    pf2.parse()
    dep_names2 = [d.name.lower() for d in pf2.dependencies]
    assert "backend_seq" in dep_names2
    assert "backend_acc" not in dep_names2


def test_parse_lowercase_f90_skips_cpp(tmp_path):
    """Lowercase .f90 must NOT run cpp — preserves the standard convention.

    A `#define`-style line in a .f90 file is not preprocessed; the parser
    will see the raw `use :: MACRO_NAME` and record it as a dependency
    (which is what the user wants when they explicitly use lowercase to
    skip preprocessing).
    """
    src = "#define DEVMODULE openacc\nmodule mymod\nuse :: DEVMODULE\nend module mymod\n"
    f = _write(tmp_path, "src.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name.lower() for d in pf.dependencies]
    # cpp did NOT run → DEVMODULE remains the literal use target.
    assert any(name == "devmodule" for name in dep_names)
    # And no expansion to the real module happened.
    assert not any(name == "openacc" for name in dep_names)


# ---------------------------------------------------------------------------
# Compiler-specific intrinsic modules: cudafor (nvfortran), ifport (intel), ...
# ---------------------------------------------------------------------------


def test_is_compiler_intrinsic_module_nvfortran_cudafor():
    """`cudafor` is intrinsic to nvfortran but not to gnu."""
    from fobis.ParsedFile import _is_compiler_intrinsic_module

    assert _is_compiler_intrinsic_module("cudafor", "nvfortran") is True
    # Case-insensitive (Fortran identifiers).
    assert _is_compiler_intrinsic_module("CUDAFOR", "nvfortran") is True
    assert _is_compiler_intrinsic_module("CudaFor", "nvfortran") is True
    # Not recognised under gnu — gnu doesn't ship cudafor.
    assert _is_compiler_intrinsic_module("cudafor", "gnu") is False
    # Not a known compiler → no filtering.
    assert _is_compiler_intrinsic_module("cudafor", "") is False
    assert _is_compiler_intrinsic_module("cudafor", "unknown_compiler") is False


def test_is_compiler_intrinsic_module_pgi_inherits_cuda():
    """pgi (legacy NVIDIA toolchain) ships the same CUDA Fortran modules."""
    from fobis.ParsedFile import _is_compiler_intrinsic_module

    assert _is_compiler_intrinsic_module("cudafor", "pgi") is True
    assert _is_compiler_intrinsic_module("cublas", "pgi") is True


def test_is_compiler_intrinsic_module_intel_ifport():
    """Intel ships ifport as an intrinsic module."""
    from fobis.ParsedFile import _is_compiler_intrinsic_module

    assert _is_compiler_intrinsic_module("ifport", "intel") is True
    assert _is_compiler_intrinsic_module("ifport", "intel_nextgen") is True
    assert _is_compiler_intrinsic_module("ifport", "gnu") is False


def test_is_compiler_intrinsic_module_extra_user_list():
    """User-supplied `intrinsic_modules` filters regardless of compiler."""
    from fobis.ParsedFile import _is_compiler_intrinsic_module

    # Active compiler is gnu; user adds a project-specific helper to the list.
    assert _is_compiler_intrinsic_module("my_helper", "gnu", ["my_helper"]) is True
    # Case-insensitive against the user list too.
    assert _is_compiler_intrinsic_module("MY_HELPER", "gnu", ["my_helper"]) is True
    # Compiler builtins still apply when the user list doesn't match.
    assert _is_compiler_intrinsic_module("cudafor", "nvfortran", ["unrelated"]) is True


def test_parse_filters_cudafor_under_nvfortran(tmp_path):
    """Under nvfortran, `use cudafor` is silently filtered (not a dependency)."""
    src = "module m\n  use cudafor\nend module m\n"
    f = _write(tmp_path, "m.f90", src)
    pf = ParsedFile(name=f)
    pf.parse(compiler="nvfortran")
    dep_names = [d.name.lower() for d in pf.dependencies]
    assert "cudafor" not in dep_names


def test_parse_keeps_cudafor_under_gnu(tmp_path):
    """Under gnu, `use cudafor` stays as a dependency (not intrinsic to gnu).

    This is the right behaviour: switching compiler to gnu surfaces the
    fact that `cudafor` is unavailable, prompting the user to fix the code
    (typically with #ifdef guards) rather than silently producing a
    broken build.
    """
    src = "module m\n  use cudafor\nend module m\n"
    f = _write(tmp_path, "m.f90", src)
    pf = ParsedFile(name=f)
    pf.parse(compiler="gnu")
    dep_names = [d.name.lower() for d in pf.dependencies]
    assert "cudafor" in dep_names


def test_parse_filters_user_intrinsic_modules(tmp_path):
    """Fobos-declared `intrinsic_modules` are filtered regardless of compiler."""
    src = "module m\n  use vendor_helper\nend module m\n"
    f = _write(tmp_path, "m.f90", src)
    pf = ParsedFile(name=f)
    pf.parse(compiler="gnu", intrinsic_modules=["vendor_helper"])
    dep_names = [d.name.lower() for d in pf.dependencies]
    assert "vendor_helper" not in dep_names


def test_parse_compiler_default_is_no_filtering(tmp_path):
    """Backward compat: omitting `compiler=` preserves prior behaviour.

    cudafor remains a dependency because no compiler is named, so no
    compiler-specific filter applies.
    """
    src = "module m\n  use cudafor\nend module m\n"
    f = _write(tmp_path, "m.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()  # no compiler= argument
    dep_names = [d.name.lower() for d in pf.dependencies]
    assert "cudafor" in dep_names


# ---------------------------------------------------------------------------
# Unified intrinsic-module filter (refactor: legacy regexes → name set)
# ---------------------------------------------------------------------------


def test_is_intrinsic_module_universal_names():
    """Universal names are filtered regardless of compiler."""
    from fobis.ParsedFile import _is_intrinsic_module

    for name in (
        "iso_fortran_env",
        "iso_c_binding",
        "ieee_exceptions",
        "ieee_arithmetic",
        "ieee_features",
        "openacc",
        "omp_lib",
        "mpi",
    ):
        assert _is_intrinsic_module(name) is True, name
        assert _is_intrinsic_module(name.upper()) is True, name  # case-insensitive
        assert _is_intrinsic_module(name, compiler="gnu") is True, name
        assert _is_intrinsic_module(name, compiler="nvfortran") is True, name


def test_is_intrinsic_module_user_module_not_filtered():
    """A user-defined module that is not in any set must NOT be filtered."""
    from fobis.ParsedFile import _is_intrinsic_module

    assert _is_intrinsic_module("my_module") is False
    assert _is_intrinsic_module("my_module", compiler="nvfortran") is False


def test_parse_use_colon_syntax_iso_c_binding_now_filtered(tmp_path):
    """`use :: iso_c_binding` (colon syntax) is correctly filtered.

    Regression-fix coverage: the legacy regex required `\\s+` between
    `use` and the module name, so it missed `use :: iso_c_binding`.
    The unified name-based filter handles both syntaxes uniformly.
    """
    src = "module m\n  use :: iso_c_binding\nend module m\n"
    f = _write(tmp_path, "m.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name.lower() for d in pf.dependencies]
    assert "iso_c_binding" not in dep_names


def test_parse_use_my_openacc_helper_is_real_dependency(tmp_path):
    """`use my_openacc_helper` is a real dependency, not silenced.

    Regression-fix coverage: the legacy regex `(.*)openacc.*` over-matched
    any `use` line containing the substring "openacc", silently filtering
    user modules whose names happened to contain it.  The unified
    name-set filter checks exact name membership, so user modules with
    intrinsic-substring names are correctly tracked.
    """
    src = "module m\n  use my_openacc_helper\nend module m\n"
    f = _write(tmp_path, "m.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name.lower() for d in pf.dependencies]
    assert "my_openacc_helper" in dep_names


def test_parse_use_my_omp_lib_helper_is_real_dependency(tmp_path):
    """`use my_omp_lib_helper` — same pattern, different intrinsic name."""
    src = "module m\n  use my_omp_lib_helper\nend module m\n"
    f = _write(tmp_path, "m.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name.lower() for d in pf.dependencies]
    assert "my_omp_lib_helper" in dep_names


def test_parse_use_intrinsic_form_still_works(tmp_path):
    """`use, intrinsic :: NAME` (syntactic form) is still filtered.

    The single surviving regex matches this form regardless of which name
    follows.  Even a name that is NOT in the universal set should be
    filtered, because the user has explicitly declared it intrinsic.
    """
    src = "module m\n  use, intrinsic :: iso_fortran_env\n  use, intrinsic :: weird_unknown_intrinsic\nend module m\n"
    f = _write(tmp_path, "m.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name.lower() for d in pf.dependencies]
    # Both are filtered — the syntactic intrinsic form is name-agnostic.
    assert "iso_fortran_env" not in dep_names
    assert "weird_unknown_intrinsic" not in dep_names
