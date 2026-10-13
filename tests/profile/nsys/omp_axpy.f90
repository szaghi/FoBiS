program omp_axpy
implicit none
integer, parameter :: n = 4000000
double precision, allocatable :: x(:), y(:)
double precision :: s
integer :: i
allocate(x(n), y(n))
x = 1d0; y = 2d0
!$omp target teams distribute parallel do map(to: x) map(tofrom: y)
do i = 1, n
  y(i) = y(i) + 3d0 * x(i)
end do
s = 0d0
!$omp target teams distribute parallel do reduction(+:s) map(to: y)
do i = 1, n
  s = s + y(i)
end do
print '(a,es23.16)', 'total = ', s
end program omp_axpy
