!< Each rule integrates exactly the polynomials of its degree: trapezoid lines, Simpson cubics.
program test_exactness
!< Each rule integrates exactly the polynomials of its degree: trapezoid lines, Simpson cubics.
use quad_rules,  only : R8P, trapezoid, simpson
use polynomials, only : line, cubic
implicit none
real(R8P), parameter :: tolerance = 1.e-14_R8P !< Rounding allowance.

if (abs(trapezoid(line, 0._R8P, 2._R8P, 3) - 8._R8P) > tolerance) error stop 'trapezoid is not exact on a line'
if (abs(simpson(cubic, 0._R8P, 2._R8P, 2) - 4._R8P) > tolerance) error stop 'simpson is not exact on a cubic'
print '(A)', 'exact on polynomials of its degree'
endprogram test_exactness
