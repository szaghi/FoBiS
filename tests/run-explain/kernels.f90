module kernels
implicit none
contains
subroutine fill(p, n)
real, pointer :: p(:)
integer, intent(in) :: n
integer :: i
do i = 1, n
  p(i) = real(i)
end do
end subroutine fill

subroutine smooth(a, n)
real, intent(inout) :: a(:)
integer, intent(in) :: n
integer :: i
do i = 1, n
  a(i) = 0.5 * (a(i) + a(i + 1))
end do
end subroutine smooth
end module kernels
