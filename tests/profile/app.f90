program app
use work
implicit none
real(8), allocatable :: y(:)
integer :: step
allocate(y(200000))
y = 1.0d0
do step = 1, 5
  call heavy(size(y), y)
end do
print '(a,es24.16)', 'total = ', light(size(y), y)
end program app
