"""Tests for fobis.analysis — preprocessor conditionals, lexer, program units."""

from __future__ import annotations

import pytest

from fobis.analysis import build_units, lex, mask_strings, parse_defines, preprocess
from fobis.analysis.preprocessor import evaluate

# ── preprocessor ───────────────────────────────────────────────────────────────


def test_parse_defines_forms():
    defines = parse_defines("-c -O2 -DMPI -DN=4 -D DEBUG -UMPI -I/inc")
    assert defines == {"N": "4", "DEBUG": "1"}


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("defined(MPI)", True),
        ("defined MPI && !defined(GPU)", True),
        ("N > 2 && N <= 4", True),
        ("N == 3 || GPU", False),
        ("UNDEFINED_MACRO", False),
        ("(N + 1) * 2 == 10", True),
        ("LEVEL >= 2", True),
    ],
)
def test_evaluate(expr, expected):
    assert evaluate(expr, {"MPI": "1", "N": "4", "LEVEL": "N"}) is expected


def test_evaluate_rejects_garbage():
    with pytest.raises(ValueError):
        evaluate("N +", {"N": "1"})


def test_preprocess_branches_and_nesting():
    lines = [
        "#ifdef MPI",  # 1
        "a",  # 2 active
        "#  if N > 8",  # 3
        "b",  # 4 inactive
        "#  elif N > 2",  # 5
        "c",  # 6 active
        "#  else",  # 7
        "d",  # 8 inactive
        "#  endif",  # 9
        "#else",  # 10
        "e",  # 11 inactive
        "#endif",  # 12
        "f",  # 13 active
    ]
    active = preprocess(lines, {"MPI": "1", "N": "4"}).active
    assert [i + 1 for i, a in enumerate(active) if a] == [2, 6, 13]


def test_preprocess_define_undef_and_include():
    lines = ["#define X", "#ifdef X", "a", "#endif", "#undef X", "#ifdef X", "b", "#endif", '#include "h.inc"']
    result = preprocess(lines)
    assert [i + 1 for i, a in enumerate(result.active) if a] == [3]
    assert result.includes == [(9, "h.inc")]


def test_preprocess_unevaluable_condition_is_assumed_true_with_warning():
    result = preprocess(["#if FOO(1)", "a", "#endif"])
    assert result.active[1]
    assert result.warnings and "assumed true" in result.warnings[0][1]


def test_preprocess_continued_directive():
    lines = ["#if defined(A) || \\", "    defined(B)", "x", "#endif"]
    assert preprocess(lines, {"B": "1"}).active == [False, False, True, False]


# ── lexer: free form ───────────────────────────────────────────────────────────


def test_mask_strings_blanks_literal_contents():
    assert mask_strings("Print *, 'Don''t ! here', \"x;y\"") == "print *, '             ', \"   \""


def test_free_form_continuation_comments_and_semicolons():
    src = lex(
        "x = 1 + &   ! first\n    & 2 ; y = 'a;b' ! trailing\n! a comment line\n10 continue\n",
        "f.f90",
    )
    assert [(s.text, s.line, s.end_line, s.label) for s in src.statements] == [
        ("x = 1 +  2", 1, 2, None),  # the blanks before '&' and after the leading '&' are both kept
        ("y = 'a;b'", 1, 2, None),
        ("continue", 4, 4, "10"),
    ]


def test_free_form_string_continued_across_lines():
    src = lex("s = 'abc&\n      &def'\n", "f.f90")
    assert src.statements[0].text == "s = 'abcdef'"


def test_comment_line_inside_continuation_is_skipped():
    src = lex("call f(a, &\n! note\n  b)\n", "f.f90")
    assert src.statements[0].text.replace(" ", "") == "callf(a,b)"


def test_free_form_directives():
    src = lex(
        "!$omp parallel do private(i) &\n!$omp& shared(a)\ndo i = 1, n\n!$acc kernels\n!$ x = omp_get_num_threads()\n",
        "f.f90",
    )
    kinds = [(s.sentinel, s.masked) for s in src.statements]
    assert kinds == [("omp", "parallel do private(i)  shared(a)"), (None, "do i = 1, n"), ("acc", "kernels")]


def test_openmp_conditional_compilation_lines():
    src = lex("!$ x = omp_get_num_threads()\n", "f.f90", openmp=True)
    assert [s.text for s in src.statements] == ["x = omp_get_num_threads()"]


def test_preprocessor_selects_compiled_code():
    text = "#ifdef MPI\nuse mpi_f08\n#else\nuse serial\n#endif\n"
    assert [s.text for s in lex(text, "f.F90").statements] == ["use serial"]
    assert [s.text for s in lex(text, "f.F90", defines={"MPI": "1"}).statements] == ["use mpi_f08"]


def test_suppression_comments():
    src = lex("x = 1 ! fobis: ignore[COR020, OBS001] kept on purpose\n! fobis: ignore[COR010]\ny = 2\n", "f.f90")
    first, second = src.suppressions
    assert (first.line, first.rules, first.reason, first.own_line) == (
        1,
        ("COR020", "OBS001"),
        "kept on purpose",
        False,
    )
    assert (second.line, second.rules, second.reason, second.own_line) == (2, ("COR010",), "", True)


def test_fortran_include_line_recorded():
    src = lex("include 'mpif.h'\n#include \"omp_lib.h\"\n", "f.F90")
    assert src.includes == [(1, "mpif.h"), (2, "omp_lib.h")]


# ── lexer: fixed form ──────────────────────────────────────────────────────────


def test_fixed_form_comments_labels_continuation():
    text = (
        "C     a comment\n"
        "      INTEGER I,\n"
        "     &        J\n"
        "*     another\n"
        "   10 CONTINUE\n"
        "      X = 1                                                             SEQ00001\n"
    )
    src = lex(text, "f.f")
    assert src.fixed_form
    assert [(s.masked, s.line, s.end_line, s.label) for s in src.statements] == [
        ("integer i,        j", 2, 3, None),
        ("continue", 5, 5, "10"),
        ("x = 1", 6, 6, None),
    ]


def test_fixed_form_directives():
    src = lex("C$OMP PARALLEL\nC$OMP&PRIVATE(I)\n      X = 1\n", "f.f")
    assert [(s.sentinel, s.masked) for s in src.statements] == [("omp", "parallel private(i)"), (None, "x = 1")]


def test_form_inferred_from_extension():
    assert lex("", "a.F").fixed_form
    assert not lex("", "a.F90").fixed_form


# ── units ──────────────────────────────────────────────────────────────────────

_MODULE = """\
module m
use, intrinsic :: iso_fortran_env, only: rk => real64
implicit none
private
type :: t
  integer :: a = 1
contains
  procedure :: p
end type t
abstract interface
  subroutine cb(x)
    real :: x
  end subroutine cb
end interface
contains
  pure function f(x, y) result(z)
    real(rk), intent(in) :: x
    real(rk) :: y, z
    integer :: cnt = 0
    character(len=*), parameter :: s = 'a'
    real, pointer :: q(:) => null()
    z = x + y
  end function f
  subroutine g(a, n, *)
    integer, intent(in) :: n
    dimension a(n, *)
    intent(inout) :: a
    save
  end
end module m
"""


def _units(text: str, path: str = "m.f90"):
    return build_units(lex(text, path))


def test_unit_tree_and_kinds():
    units = _units(_MODULE)
    assert [(u.kind, u.name) for u in units.walk()] == [
        ("module", "m"),
        ("interface", ""),
        ("subroutine", "cb"),
        ("function", "f"),
        ("subroutine", "g"),
    ]
    module = units.units[0]
    assert module.implicit_none and module.default_access == "private"
    assert module.uses[0].module == "iso_fortran_env" and module.uses[0].only and module.uses[0].nature == "intrinsic"
    assert "a" not in module.decls  # derived-type components are not module variables


def test_unit_procedure_facts():
    units = {u.name: u for u in _units(_MODULE).walk()}
    f = units["f"]
    assert (f.args, f.result, f.prefixes) == (["x", "y"], "z", {"pure"})
    assert f.decls["x"].attrs == {"intent": "in"}
    assert f.decls["cnt"].init == "0"
    assert f.decls["s"].attrs == {"parameter": ""}
    assert f.decls["q"].pointer_init and f.decls["q"].dims == ":"
    g = units["g"]
    assert g.args == ["a", "n"]  # alternate return '*' dropped
    assert g.decls["a"].dims == "n,*" and g.decls["a"].attrs["intent"] == "inout"
    assert g.save_all
    assert units["cb"].is_interface_body and not units["cb"].implicit_none


def test_header_prefix_forms():
    text = (
        "module m\ncontains\n"
        "  elemental real(kind=8) function a(x)\n  end function\n"
        "  type(foo_t) function b() result(r)\n  end function\n"
        "  recursive module subroutine c(x) bind(c, name='c')\n  end subroutine\n"
        "  character(len=*) function d(s)\n  end function\n"
        "end module m\n"
    )
    found = {u.name: (u.kind, sorted(u.prefixes), u.result) for u in _units(text).walk() if u.kind != "module"}
    assert found == {
        "a": ("function", ["elemental", "real"], "a"),
        "b": ("function", ["type"], "r"),
        "c": ("subroutine", ["module", "recursive"], None),
        "d": ("function", ["character"], "d"),
    }


def test_external_procedures_programs_and_fragments():
    units = _units("subroutine ext(x)\nend\nprogram p\nend program p\n").units
    assert [(u.kind, u.name, u.is_external) for u in units] == [("subroutine", "ext", True), ("program", "p", False)]
    fragment = _units("x = 1\n", "piece.inc").units[0]
    assert fragment.kind == "fragment"


def test_end_constructs_do_not_close_units():
    text = "subroutine s()\ndo i = 1, 2\nend do\nif (x) then\nend if\nblock\nend block\nx = 1\nend subroutine s\n"
    unit = _units(text).units[0]
    assert unit.end_line == 9
    assert unit.statements[-1].masked == "x = 1"


def test_submodule_and_separate_module_procedure():
    text = "submodule (parent) child\ncontains\n  module procedure work\n  end procedure work\nend submodule child\n"
    assert [(u.kind, u.name) for u in _units(text).walk()] == [("submodule", "child"), ("module procedure", "work")]


def test_macro_typed_declaration_is_recognised():
    unit = _units("subroutine s(q)\nVARTYPE(KKP), intent(in) :: q(:)\nend subroutine\n").units[0]
    assert unit.decls["q"].attrs["intent"] == "in"


def test_implicit_statements():
    units = _units(
        "program a\nimplicit none (type, external)\nend program\n"
        "program b\nimplicit double precision (a-h, o-z)\nend program\n"
    ).units
    assert units[0].implicit_none and units[0].implicit_none_external
    assert not units[1].implicit_none and len(units[1].implicit_mappings) == 1
