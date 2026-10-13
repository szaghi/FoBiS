program acc_main
use acc_kernels
implicit none
integer, parameter :: n = 1000000
double precision, allocatable :: a(:)
allocate(a(n))
a = 1d0
!$acc data copy(a)
call scale(n, a, 2d0)
call shift(n, a)
!$acc end data
print '(a,es23.16)', 'sum = ', sum(a)
end program acc_main
