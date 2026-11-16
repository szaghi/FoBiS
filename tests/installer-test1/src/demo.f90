!< The library of the installer tests (GH #217).
module demo
implicit none
private
public :: answer

contains
   pure function answer() result(a)
   !< The answer.
   integer :: a !< The answer.

   a = 42
   endfunction answer
endmodule demo
