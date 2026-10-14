!< The curves whose areas we want.
module curves
!< The curves whose areas we want.
use quad_rules, only : R8P
implicit none
private
public :: parabola

contains
   pure function parabola(x) result(y)
   !< x**2.
   real(R8P), intent(in) :: x !< Abscissa.
   real(R8P)             :: y !< x**2.

   y = x * x
   endfunction parabola
endmodule curves
