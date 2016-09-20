submodule (module1) module1_implementation_what
  implicit none
  contains
    module subroutine print_what(message)
    character(len=*), intent(in) :: message
    print "(A)", message
    return
    endsubroutine print_what
endsubmodule module1_implementation_what

submodule (module2) module1_implementation_where
  implicit none
  contains
    module subroutine print_where(message1, message2)
    character(len=*), intent(in) :: message1
    character(len=*), intent(in) :: message2
    type(foo1) :: a_foo1
    call a_foo1%print_what(message=message1)
    print "(A)", message2
    return
    endsubroutine print_where
endsubmodule module1_implementation_where
