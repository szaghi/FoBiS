module mod1
  integer :: i = 1
end module

module mymod
  use mod1
contains
  subroutine print_hello()
    print *, "hello ", i
  end subroutine
end module
