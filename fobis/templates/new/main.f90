!< The program of @@NAME@@.
program main
!< The program of @@NAME@@.
use iso_fortran_env, only : real64
use @@NAME@@, only : mean
implicit none

print '(A,F4.1)', 'mean of 1, 2, 3, 4: ', mean([1._real64, 2._real64, 3._real64, 4._real64])
endprogram main
