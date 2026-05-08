module nested_1
implicit none
character(len=12), parameter :: hello_world = 'Hello World!'
contains
  subroutine print_hello_world()
  implicit none
  print "(A)", hello_world
  endsubroutine print_hello_world
endmodule nested_1
