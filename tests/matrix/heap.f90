program heap
implicit none
real, allocatable :: a(:)
integer :: i, n
n = 10
allocate(a(n))
a = 0.0
call touch(a, n + 1)
print *, a(1)
contains
subroutine touch(x, m)
integer, intent(in) :: m
real, intent(inout) :: x(*)
integer :: k
do k = 1, m
  x(k) = 1.0
end do
end subroutine touch
end program heap
