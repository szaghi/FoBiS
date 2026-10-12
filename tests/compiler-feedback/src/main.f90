program main
use k, only: axpy, scan, omp_off
implicit none
real :: x(1000), y(1000), s
integer :: i
x = 1.0
y = 2.0
call axpy(1000, 2.0, x, y)
call scan(1000, y)
call omp_off(1000, y)
s = 0
do i = 1, 1000
  y(i) = sqrt(y(i)) * y(max(i-1,1))
end do
print *, sum(y)
end program main
