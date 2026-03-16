module introspective
!< Intropsective module main tests: testing doctests into the main module comments.
!<### Sum test
!<```fortran
!< print*, add(a=1, b=1)
!<```
!=> 2 <<<
!<### Multiply test
!<```fortran
!< integer :: c
!< call multiply(a=1, b=0, c=c)
!< print*, c
!<```
!=> 0 <<<
implicit none
private
public :: add, multiply
contains
  function add(a, b) result(c)
  !< Add two integers.
  !<
  !<### Introspective doctests
  !<```fortran
  !< print*, add(a=12, b=33)
  !<```
  !=> 45 <<<
  !<
  !<```fortran
  !< print*, add(a=-120, b=20)
  !<```
  !=> -100 <<<
  integer, intent(IN) :: a
  integer, intent(IN) :: b
  integer             :: c
  c = a + b
  endfunction add

  subroutine multiply(a, b, c)
  !< Multiply two integers.
  !<
  !<### Introspective doctests
  !<```fortran
  !< integer :: c
  !< call multiply(a=3, b=4, c=c)
  !< print*, c
  !<```
  !=> 12 <<<
  !<
  !<```fortran
  !< integer :: c
  !< call multiply(a=-2, b=16, c=c)
  !< print*, c
  !<```
  !=> -32 <<<
  integer, intent(IN)  :: a
  integer, intent(IN)  :: b
  integer, intent(OUT) :: c
  c = a * b
  endsubroutine multiply
endmodule introspective
