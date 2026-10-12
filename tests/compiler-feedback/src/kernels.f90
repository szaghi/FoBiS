module k
implicit none
contains
subroutine axpy(n, a, x, y)
  integer, intent(in) :: n
  real, intent(in) :: a, x(n)
  real, intent(inout) :: y(n)
  integer :: i
  !$acc parallel loop
  do i = 1, n
    y(i) = y(i) + a * x(i)
  end do
end subroutine axpy
subroutine scan(n, y)
  integer, intent(in) :: n
  real, intent(inout) :: y(n)
  integer :: i
  !$acc kernels
  do i = 2, n
    y(i) = y(i) + y(i-1)
  end do
  !$acc end kernels
end subroutine scan
subroutine omp_off(n, y)
  integer, intent(in) :: n
  real, intent(inout) :: y(n)
  integer :: i
  real :: t
  !$omp target teams distribute parallel do
  do i = 1, n
    t = y(i) * 2
    y(i) = t
  end do
end subroutine omp_off
end module k
