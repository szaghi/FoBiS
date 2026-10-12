module semantic
use geometry, only : area
implicit none
contains
subroutine bad(n, x)
integer, intent(in) :: n
real, intent(in) :: x(n)
real :: total
n = 3
total = area(1, 2)
total = undeclared + 1.0
call scale_all(x, 2.0)
end subroutine bad
end module semantic
