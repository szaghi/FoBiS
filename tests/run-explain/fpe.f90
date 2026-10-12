program fpe
implicit none
real :: zero, y
read(*, *) zero
y = 1.0 / zero
print *, y
end program fpe
