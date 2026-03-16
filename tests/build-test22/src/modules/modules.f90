module module1
  implicit none
  type :: foo1
    contains
      procedure, nopass :: print_what
  endtype foo1
  interface
    module subroutine print_what(message)
    character(len=*), intent(in) :: message
    endsubroutine print_what
  endinterface
endmodule module1

module module2
  use module1
  implicit none
  type :: foo2
    contains
      procedure, nopass :: print_where
  endtype foo2
  interface
    module subroutine print_where(message1, message2)
    character(len=*), intent(in) :: message1
    character(len=*), intent(in) :: message2
    endsubroutine print_where
  endinterface
endmodule module2
