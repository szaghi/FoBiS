program length
!< A program of another lab member, linked to the installed vectors through pkg-config.
use kinds,   only : R8P
use vectors, only : norm
implicit none
print '(F6.3)', norm([1._R8P, 2._R8P, 2._R8P])
end program length
