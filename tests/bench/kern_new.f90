module kern
implicit none
contains
subroutine axpy(n, a, x, y)
integer, intent(in) :: n
real(8), intent(in) :: a, x(n)
real(8), intent(inout) :: y(n)
integer :: i
!$acc kernels
do i = 2, n
  y(i) = y(i) + a * x(i) + 1.0d-30 * y(i-1)
end do
!$acc end kernels
end subroutine axpy
end module kern
