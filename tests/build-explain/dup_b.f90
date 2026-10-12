subroutine helper(x)
real, intent(inout) :: x
x = 3 * x
end subroutine helper
program dup
real :: y = 1.0
call helper(y)
print *, y
end program dup
