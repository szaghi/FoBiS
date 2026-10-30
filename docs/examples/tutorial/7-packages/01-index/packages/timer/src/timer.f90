module timer
!< Wall-clock timing.
use, intrinsic :: iso_fortran_env, only : int64, real64
implicit none
private
public :: seconds
contains
   function seconds() result(t)
   !< Seconds since an arbitrary start.
   real(real64)   :: t     !< Seconds.
   integer(int64) :: count !< Clock count.
   integer(int64) :: rate  !< Counts per second.
   call system_clock(count, rate)
   t = real(count, real64) / rate
   endfunction seconds
end module timer
