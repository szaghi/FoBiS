module geometry
implicit none
private
public :: area, scale_all
contains
pure function area(r) result(a)
real, intent(in) :: r
real :: a
a = 3.14159 * r**2
end function area
subroutine scale_all(x, s)
real, intent(inout) :: x(:)
real, intent(in) :: s
x = x * s
end subroutine scale_all
end module geometry
