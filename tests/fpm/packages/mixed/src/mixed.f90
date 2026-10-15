module mixed
use iso_c_binding, only: c_double
use tools, only: tool_scale
implicit none
private
public :: c_seconds, scaled

interface
  function c_seconds() bind(c, name="c_seconds") result(t)
    import :: c_double
    real(c_double) :: t
  end function
end interface

contains

pure integer function scaled(i)
  integer, intent(in) :: i
  scaled = tool_scale * i
end function scaled
end module mixed
