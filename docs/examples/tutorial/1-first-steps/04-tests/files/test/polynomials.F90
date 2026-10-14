!< Polynomials whose integrals are known exactly.
module polynomials
!< Polynomials whose integrals are known exactly.
use quad_rules, only : R8P
implicit none
private
public :: line, cubic

contains
   pure function line(x) result(y)
   !< 3x + 1, integral on [0, 2] = 8.
   real(R8P), intent(in) :: x !< Abscissa.
   real(R8P)             :: y !< Value.

   y = 3._R8P * x + 1._R8P
   endfunction line

   pure function cubic(x) result(y)
   !< x**3, integral on [0, 2] = 4.
   real(R8P), intent(in) :: x !< Abscissa.
   real(R8P)             :: y !< Value.

   y = x ** 3
   endfunction cubic
endmodule polynomials
