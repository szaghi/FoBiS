module vectors
!< Small vectors of reals.
use kinds, only : R8P
implicit none
private
public :: norm
contains
   pure function norm(v) result(n)
   !< Euclidean norm.
   real(R8P), intent(in) :: v(:) !< Vector.
   real(R8P)             :: n    !< Its norm.
   n = sqrt(sum(v * v))
   endfunction norm
end module vectors
