program acc_copy
implicit none
integer, parameter :: n = 4000000, steps = 5
double precision, allocatable :: x(:), y(:)
double precision :: s
integer :: i, k
allocate(x(n), y(n))
x = 1d0; y = 0d0
do k = 1, steps
  !$acc parallel loop copyin(x) copy(y)
  do i = 1, n
    y(i) = y(i) + 0.5d0 * x(i)
  end do
end do
s = 0d0
!$acc parallel loop reduction(+:s)
do i = 1, n
  s = s + y(i)
end do
print '(a,es23.16)', 'total = ', s
end program acc_copy
