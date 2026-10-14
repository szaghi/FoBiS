!< Integrate sin(x) over [0, pi], whose exact value is 2, with more and more intervals.
program integrate
!< Integrate sin(x) over [0, pi], whose exact value is 2, with more and more intervals.
use quad_rules, only : R8P, trapezoid, simpson
use integrands, only : sine
implicit none
real(R8P), parameter :: pi = acos(-1._R8P) !< Pi.
integer              :: n                  !< Number of intervals.

print '(A6, 2A18)', 'n', 'trapezoid error', 'simpson error'
n = 4
do while (n <= 64)
   print '(I6, 2ES18.4)', n, abs(trapezoid(sine, 0._R8P, pi, n) - 2._R8P), abs(simpson(sine, 0._R8P, pi, n) - 2._R8P)
   n = 2 * n
enddo
endprogram integrate
