module kinds
!< Portable real kinds.
implicit none
private
public :: R4P, R8P
integer, parameter :: R4P = selected_real_kind(6, 37)   !< 6 digits (new in 1.1.0).
integer, parameter :: R8P = selected_real_kind(15, 307) !< 15 digits.
end module kinds
