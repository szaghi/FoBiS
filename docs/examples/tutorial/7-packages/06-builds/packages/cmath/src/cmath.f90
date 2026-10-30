module cmath
!< A clamp, built with CMake.
use, intrinsic :: iso_fortran_env, only : real64
implicit none
private
public :: clamp
contains
   elemental function clamp(x, low, high) result(y)
   !< x limited to [low, high].
   real(real64), intent(in) :: x, low, high !< Value and bounds.
   real(real64)             :: y            !< Clamped value.
   y = min(max(x, low), high)
   endfunction clamp
end module cmath
