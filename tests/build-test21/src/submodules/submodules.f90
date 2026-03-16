submodule (module1) module1_implementation_what
  implicit none
  contains
    module subroutine print_what(message)
    character(len=*), intent(in) :: message
    print "(A)", message
    return
    endsubroutine print_what
endsubmodule module1_implementation_what

submodule (module1) module1_implementation_where
  implicit none
  contains
    module subroutine print_where(message)
    character(len=*), intent(in) :: message
    print "(A)", message
    return
    endsubroutine print_where
endsubmodule module1_implementation_where
