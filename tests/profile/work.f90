module work
implicit none
contains
subroutine heavy(n, y)
integer, intent(in) :: n
real(8), intent(inout) :: y(n)
integer :: i, k
do k = 1, 200
  do i = 2, n
    y(i) = sqrt(y(i) + 1.0d-3 * y(i-1))
  end do
end do
end subroutine heavy
real(8) function light(n, y)
integer, intent(in) :: n
real(8), intent(in) :: y(n)
light = sum(y) + helper(y(1))
contains
real(8) function helper(a)
real(8), intent(in) :: a
helper = 2 * a
end function helper
end function light
end module work
program app
use work
implicit none
real(8), allocatable :: y(:)
integer :: step
allocate(y(200000))
y = 1.0d0
do step = 1, 5
  call heavy(size(y), y)
end do
print '(a,es24.16)', 'total = ', light(size(y), y)
end program app
