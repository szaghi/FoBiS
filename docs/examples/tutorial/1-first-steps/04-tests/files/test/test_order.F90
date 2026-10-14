!< Halving the interval width divides the error by 2**p: p = 2 for the trapezoid rule, 4 for Simpson's.
program test_order
!< Halving the interval width divides the error by 2**p: p = 2 for the trapezoid rule, 4 for Simpson's.
use quad_rules, only : R8P, trapezoid, simpson
use integrands, only : sine
implicit none
real(R8P), parameter :: pi = acos(-1._R8P) !< Pi.
real(R8P)            :: p_trapezoid        !< Observed order, trapezoid.
real(R8P)            :: p_simpson          !< Observed order, Simpson.

p_trapezoid = log(abs(trapezoid(sine, 0._R8P, pi, 16) - 2._R8P) / abs(trapezoid(sine, 0._R8P, pi, 32) - 2._R8P)) / log(2._R8P)
p_simpson = log(abs(simpson(sine, 0._R8P, pi, 16) - 2._R8P) / abs(simpson(sine, 0._R8P, pi, 32) - 2._R8P)) / log(2._R8P)
print '(A, F6.3, A, F6.3)', 'observed orders: trapezoid ', p_trapezoid, ', simpson ', p_simpson
if (abs(p_trapezoid - 2._R8P) > 0.01_R8P) error stop 'trapezoid is not second order'
if (abs(p_simpson - 4._R8P) > 0.01_R8P) error stop 'simpson is not fourth order'
endprogram test_order
