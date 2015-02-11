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
  module procedure less_than_type_1
  module procedure less_than_type_2
  module procedure less_than_type_3
endinterface

contains
  elemental function less_than_type_1(self,to_compare) result(compare)
  type(type_1),intent(IN):: self
  integer(I4P),intent(IN):: to_compare
  logical::                 compare
  compare = (self%v<to_compare)
  endfunction less_than_type_1
  elemental function less_than_type_2(self,to_compare) result(compare)
  type(type_2),intent(IN):: self
  integer(I4P),intent(IN):: to_compare
  logical::                 compare
  compare = (self%v<to_compare)
  endfunction less_than_type_2
  elemental function less_than_type_3(self,to_compare) result(compare)
  type(type_3),intent(IN):: self
  integer(I4P),intent(IN):: to_compare
  logical::                 compare
  compare = (self%v<to_compare)
  endfunction less_than_type_3
endmodule types
