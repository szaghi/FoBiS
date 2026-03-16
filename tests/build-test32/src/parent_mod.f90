! parent_mod does NOT use helper_mod; only the submodule does.
! This is the corner case that previously caused FoBiS to compile
! helper_mod.o but omit it from the link command.
module parent_mod
  implicit none
  interface
    module subroutine compute(result)
      integer, intent(out) :: result
    end subroutine compute
  end interface
end module parent_mod
