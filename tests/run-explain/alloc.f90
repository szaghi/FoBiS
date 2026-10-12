program alloc
implicit none
real, allocatable :: x(:)
allocate(x(10))
x = 1.0
allocate(x(20))
print *, size(x)
end program alloc
