program solver
!< The length of a vector, clamped, and its unit in upper case: packages built by FoBiS, fpm and CMake.
use kinds,   only : R8P
use vectors, only : norm
use strings, only : upper
use cmath,   only : clamp
implicit none
print '(F6.3,1X,A)', clamp(norm([3._R8P, 4._R8P]), 0._R8P, 4._R8P), upper('metres')
end program solver
