!< A test of @@NAME@@: `fobis test` runs every program of test/, a non-zero exit status is a failure.
program test_@@NAME@@
!< A test of @@NAME@@: `fobis test` runs every program of test/, a non-zero exit status is a failure.
use iso_fortran_env, only : real64
use @@NAME@@, only : mean
implicit none

if (abs(mean([1._real64, 2._real64, 3._real64]) - 2._real64) > 1.e-15_real64) error stop 'mean of 1, 2, 3 is not 2'
if (abs(mean([real(real64) ::])) > 0._real64) error stop 'mean of nothing is not 0'
print '(A)', 'mean: ok'
endprogram test_@@NAME@@
