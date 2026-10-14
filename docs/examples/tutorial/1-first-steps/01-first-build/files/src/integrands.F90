!< Functions to integrate.
module integrands
!< Functions to integrate.
use quad_rules, only : R8P
implicit none
private
public :: sine

contains
   pure function sine(x) result(y)
   !< sin(x).
   real(R8P), intent(in) :: x !< Abscissa.
   real(R8P)             :: y !< sin(x).

   y = sin(x)
   endfunction sine
endmodule integrands
