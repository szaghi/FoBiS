module helper_mod
  implicit none
  private
  public :: helper_value
contains
  pure integer function helper_value()
    helper_value = 42
  end function helper_value
end module helper_mod
