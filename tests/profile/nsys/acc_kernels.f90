module acc_kernels
implicit none
contains
subroutine scale(n, a, f)
  integer, intent(in) :: n
  double precision, intent(inout) :: a(n)
  double precision, intent(in) :: f
  integer :: i
  !$acc parallel loop present(a)
  do i = 1, n
    a(i) = f * a(i)
  end do
end subroutine scale
subroutine shift(n, a)
  integer, intent(in) :: n
  double precision, intent(inout) :: a(n)
  call add_one()
contains
  subroutine add_one()
    integer :: i
    !$acc parallel loop present(a)
    do i = 1, n
      a(i) = a(i) + 1d0
    end do
  end subroutine add_one
end subroutine shift
end module acc_kernels
