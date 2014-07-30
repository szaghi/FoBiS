module types
implicit none
! some precisions definitions
integer, parameter:: R8P = selected_real_kind(15,307)
integer, parameter:: R4P = selected_real_kind(6,37)
integer, parameter:: I4P = selected_int_kind(9)
! some derived types
type:: type_1
  real(R8P):: v
endtype type_1
type:: type_2
  real(R4P):: v
endtype type_2
type:: type_3
  integer(I4P):: v
endtype type_3
! generic interface
interface less_than
#ifdef LOOPLIST
  #PFM for i in [0,1,2]:
  module procedure less_than_type_$i
  #PFM endfor
#else
  #PFM for i in range(3):
  module procedure less_than_type_$i
  #PFM endfor
#endif
endinterface

contains
  #PFM for i in range(3):
  elemental function less_than_type_$i(self,to_compare) result(compare)
  type(type_$i),intent(IN):: self
  integer(I4P),intent(IN):: to_compare
  logical::                 compare
  compare = (self%v<to_compare)
  endfunction less_than_type_$i
  #PFM endfor
endmodule types

program simple_for_loop
use types
type(type_1):: one
type(type_2):: two
type(type_3):: three

one%v   = 1._R8P
two%v   = 2._R4P
three%v = 3_I4P

#ifndef CPPCHECK
if (less_than(one,  2)) print*,' Ok, generic inteface correct for type_1!'
if (less_than(two,  3)) print*,' Ok, generic inteface correct for type_2!'
if (less_than(three,4)) print*,' Ok, generic inteface correct for type_3!'
#else
print*,'No, PFM directives face with cpp ones!'
#endif
endprogram simple_for_loop
