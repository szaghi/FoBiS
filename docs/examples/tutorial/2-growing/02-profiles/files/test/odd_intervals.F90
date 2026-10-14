!< Simpson's rule with an odd number of intervals: wrong without a word, unless the checks are built in.
program odd_intervals
!< Simpson's rule with an odd number of intervals: wrong without a word, unless the checks are built in.
use quad_rules,  only : R8P, simpson
use polynomials, only : cubic
implicit none

print '(A, F10.6)', 'integral of x**3 on [0, 2] (exact 4): ', simpson(cubic, 0._R8P, 2._R8P, 3)
endprogram odd_intervals
