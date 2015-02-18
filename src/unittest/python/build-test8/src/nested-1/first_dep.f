      subroutine print_hello_world()
      implicit none
      character(len=12), parameter:: hello_world='Hello World!'
      print "(A)",hello_world
      return
      endsubroutine print_hello_world
