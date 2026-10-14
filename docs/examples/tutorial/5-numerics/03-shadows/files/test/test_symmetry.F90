!< Every rule integrates an odd function over a symmetric interval to zero.
program test_symmetry
!< Every rule integrates an odd function over a symmetric interval to zero.
use quad_rules,  only : R8P, midpoint, trapezoid, simpson
use polynomials, only : cubic
implicit none
real(R8P), parameter :: tolerance = 1.e-14_R8P !< Rounding allowance.
real(R8P), parameter :: exact = 0._R8P         !< The integral of x**3 over [-1, 1].

if (relative(midpoint(cubic, -1._R8P, 1._R8P, 4)) > tolerance) error stop 'midpoint is not symmetric'
if (relative(trapezoid(cubic, -1._R8P, 1._R8P, 4)) > tolerance) error stop 'trapezoid is not symmetric'
if (relative(simpson(cubic, -1._R8P, 1._R8P, 4)) > tolerance) error stop 'simpson is not symmetric'
print '(A)', 'zero for an odd function'

contains
   pure function relative(s) result(e)
   !< Relative error of an estimate.
   real(R8P), intent(in) :: s !< Estimate.
   real(R8P)             :: e !< Relative error.

   e = abs(s - exact) / abs(exact)
   endfunction relative
endprogram test_symmetry
