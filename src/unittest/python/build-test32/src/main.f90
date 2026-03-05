program main
  use parent_mod
  implicit none
  integer :: result
  call compute(result)
  if (result /= 42) stop 1
end program main
