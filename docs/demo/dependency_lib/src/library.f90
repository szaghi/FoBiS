module dep_lib
implicit none
contains
  subroutine dep_greet()
  implicit none
  print "(A)", 'Hello from dep_lib!'
  endsubroutine dep_greet
endmodule dep_lib
