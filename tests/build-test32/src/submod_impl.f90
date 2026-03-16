! This submodule uses helper_mod exclusively - no other non-submodule
! file uses it.  Before the fix, helper_mod.o was compiled but dropped
! from the link command, producing an undefined-reference linker error.
submodule (parent_mod) impl
  use helper_mod
  implicit none
contains
  module subroutine compute(result)
    integer, intent(out) :: result
    result = helper_value()
  end subroutine compute
end submodule impl
