!< @@NAME@@: the library of the project.
module @@NAME@@
!< @@NAME@@: the library of the project.
use iso_fortran_env, only : real64
implicit none
private
public :: mean

contains
   pure function mean(values) result(average)
   !< Arithmetic mean of `values` (0 when there are none).
   real(real64), intent(in) :: values(:) !< The values.
   real(real64)             :: average   !< Their mean.

   average = 0._real64
   if (size(values) > 0) average = sum(values) / size(values)
   endfunction mean
endmodule @@NAME@@
