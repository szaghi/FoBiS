module kern
implicit none
contains
subroutine axpy(n, a, x, y)
integer, intent(in) :: n
real(8), intent(in) :: a, x(n)
real(8), intent(inout) :: y(n)
integer :: i
!$acc parallel loop
do i = 1, n
  y(i) = y(i) + a * x(i)
end do
end subroutine axpy
end module kern
