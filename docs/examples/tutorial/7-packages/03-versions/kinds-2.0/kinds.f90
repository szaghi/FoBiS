module kinds
!< Portable real kinds. 2.0.0: the kinds are named after their digits.
implicit none
private
public :: RK6, RK15
integer, parameter :: RK6  = selected_real_kind(6, 37)   !< 6 digits.
integer, parameter :: RK15 = selected_real_kind(15, 307) !< 15 digits.
end module kinds
