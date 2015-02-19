module library_1
use NesteD_1
implicit none
contains
  subroutine print_hello_world()
  implicit none
  print '(A)',hello_world
  endsubroutine print_hello_world
endmodule library_1
