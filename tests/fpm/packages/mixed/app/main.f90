program main
use mixed, only: c_seconds, scaled
implicit none
#ifdef BASELINE
print '(A)', 'baseline'
#endif
print '(I0,1X,I0)', MIXED_SCALE, scaled(2)
if (c_seconds() < 0) error stop 1
end program main
