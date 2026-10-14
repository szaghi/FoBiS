!< The errors of both rules for 2, 4, ... 4096 intervals: the cases computed in parallel by OpenMP threads.
program sweep
!< The errors of both rules for 2, 4, ... 4096 intervals: the cases computed in parallel by OpenMP threads.
use quad_rules, only : R8P, trapezoid, simpson
use integrands, only : sine
!$ use omp_lib, only : omp_get_max_threads
implicit none
integer,   parameter :: cases = 12                !< Number of cases.
real(R8P), parameter :: pi = acos(-1._R8P)        !< Pi.
real(R8P)            :: error(2, cases)           !< Errors, trapezoid and Simpson, of each case.
integer              :: k                         !< Counter.
integer              :: n                         !< Number of intervals.

!$omp parallel do private(n)
do k = 1, cases
   n = 2 ** k
   error(1, k) = abs(trapezoid(sine, 0._R8P, pi, n) - 2._R8P)
   error(2, k) = abs(simpson(sine, 0._R8P, pi, n) - 2._R8P)
enddo
!$ print '(A, I0)', 'threads: ', omp_get_max_threads()
print '(A6, 2A18)', 'n', 'trapezoid error', 'simpson error'
do k = 1, cases
   print '(I6, 2ES18.4)', 2 ** k, error(:, k)
enddo
endprogram sweep
