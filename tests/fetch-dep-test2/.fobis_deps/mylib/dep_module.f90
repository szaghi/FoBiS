module dep_module
  implicit none
contains
  subroutine dep_greet()
    print '(A)', 'hello from dep_module'
  end subroutine dep_greet
end module dep_module
