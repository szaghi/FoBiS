module module1
  implicit none
  interface
    module subroutine print_what(message)
    character(len=*), intent(in) :: message
    endsubroutine print_what
    module subroutine print_where(message)
    character(len=*), intent(in) :: message
    endsubroutine print_where
  endinterface
endmodule module1
