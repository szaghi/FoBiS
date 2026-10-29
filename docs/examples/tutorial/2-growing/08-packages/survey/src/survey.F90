!< A survey of quad's rules, using quad as a package added by name.
program survey
!< A survey of quad's rules, using quad as a package added by name.
use integrands, only : sine
use quad_rules, only : R8P, simpson, trapezoid
implicit none

real(R8P), parameter :: pi = acos(-1._R8P)

print '(A, F18.15)', 'trapezoid = ', trapezoid(sine, 0._R8P, pi, 64)
print '(A, F18.15)', 'simpson   = ', simpson(sine, 0._R8P, pi, 8)
endprogram survey
