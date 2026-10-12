program segv
use kernels
implicit none
real, pointer :: p(:) => null()
call fill(p, 100000)
print *, p(1)
end program segv
