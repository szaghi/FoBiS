program check
use mixed, only: scaled
implicit none
if (scaled(2) /= 6) error stop 1
end program check
