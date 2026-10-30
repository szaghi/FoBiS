module curves
!< An integrand of the consumer's own.
use quad_rules, only : R8P
implicit none
contains
   pure function parabola(x) result(y)
   real(R8P), intent(in) :: x
   real(R8P)             :: y
   y = 3._R8P * x * x
   endfunction parabola
end module curves

program use_quad
!< A program outside the project, linked to quad through pkg-config.
use quad_rules, only : R8P, simpson
use curves,     only : parabola
implicit none
print '(F8.5)', simpson(parabola, 0._R8P, 1._R8P, 2)
end program use_quad
