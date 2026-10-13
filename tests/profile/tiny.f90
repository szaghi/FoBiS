module tiny_m
implicit none
contains
integer function twice(i)
integer, intent(in) :: i
twice = 2 * i
end function twice
end module tiny_m
