module module1
  implicit none
  contains
    subroutine print_hello_world(hello)
    character(len=*), intent(IN) :: hello
    print "(A)", hello
    return
    endsubroutine print_hello_world
endmodule module1

module module2
  implicit none
  character(len=*), parameter :: hello = 'We love Paris!'
endmodule module2
