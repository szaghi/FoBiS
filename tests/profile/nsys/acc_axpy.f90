program acc_axpy
use openacc
implicit none
integer, parameter :: n = 50000000
double precision, allocatable :: x(:), y(:)
double precision :: s
integer :: i, ndev
allocate(x(n), y(n))
ndev = acc_get_num_devices(acc_device_nvidia)
!$acc data create(x, y)
!$acc parallel loop
do i = 1, n
  x(i) = dble(i) / dble(n)
  y(i) = 1d0
end do
!$acc parallel loop
do i = 1, n
  y(i) = 2d0 * x(i) + y(i)
end do
s = 0d0
!$acc parallel loop reduction(+:s)
do i = 1, n
  s = s + y(i)
end do
!$acc end data
print '(a,i0)', 'devices = ', ndev
print '(a,es23.16)', 'checksum = ', s
end program acc_axpy
