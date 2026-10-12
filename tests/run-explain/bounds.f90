program bounds
use kernels
implicit none
real :: a(10)
a = 1.0
call smooth(a, 10)
print *, sum(a)
end program bounds
