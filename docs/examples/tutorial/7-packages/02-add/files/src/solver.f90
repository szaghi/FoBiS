program solver
!< The length of a vector, with the lab's packages.
use kinds,   only : R8P
use vectors, only : norm
implicit none
print '(F6.3)', norm([3._R8P, 4._R8P])
end program solver
