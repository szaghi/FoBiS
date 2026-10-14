!< The area under x**2 on [0, 1], with the installed quad library.
program area
!< The area under x**2 on [0, 1], with the installed quad library.
use quad_rules, only : R8P, simpson
use curves,     only : parabola
implicit none

print '(A, F18.15)', 'area = ', simpson(parabola, 0._R8P, 1._R8P, 2)
endprogram area
