module kinds
!< Portable real kinds.
implicit none
private
public :: R8P
integer, parameter :: R8P = selected_real_kind(15, 307) !< 15 digits.
end module kinds
