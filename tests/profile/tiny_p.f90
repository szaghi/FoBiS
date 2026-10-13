program tiny
use tiny_m
implicit none
integer :: i, s
s = 0
do i = 1, 1000
  s = s + twice(i)
end do
print *, s
end program tiny
