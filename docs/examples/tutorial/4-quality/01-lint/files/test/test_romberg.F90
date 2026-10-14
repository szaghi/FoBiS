!< Romberg's method reaches 1e-10 on sin(x) over [0, pi].
program test_romberg
!< Romberg's method reaches 1e-10 on sin(x) over [0, pi].
use quad_rules, only : R8P
use integrands, only : sine
implicit none
real(R8P), external   :: romb               !< The legacy integrator.
real(R8P), parameter  :: pi = acos(-1._R8P) !< Pi.
real(R8P)             :: estimate           !< Its result.

estimate = romb(sine, 0._R8P, pi, 1.e-10_R8P)
print '(A, ES10.3)', 'romberg error: ', abs(estimate - 2._R8P)
if (abs(estimate - 2._R8P) > 1.e-9_R8P) error stop 'romberg did not converge'
endprogram test_romberg
