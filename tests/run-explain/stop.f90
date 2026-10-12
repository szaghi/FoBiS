program stopper
implicit none
real :: rho
rho = -1.0
if (rho < 0.0) error stop 'negative density'
end program stopper
