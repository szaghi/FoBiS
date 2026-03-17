implicit none
character(len=20), parameter :: greeting = 'Hello from nested_1!'
contains
  subroutine greet()
  implicit none
  print "(A)", greeting
  endsubroutine greet
