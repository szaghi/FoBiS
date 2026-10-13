program bounds
implicit none
real :: a(5)
integer :: i, n
n = 6
a = 1.0
do i = 1, n
  a(i) = a(i) + 1.0
end do
print *, a(1)
end program bounds
