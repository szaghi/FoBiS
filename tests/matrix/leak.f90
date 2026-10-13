program leak
implicit none
real, pointer :: p(:)
allocate(p(10))
p = 1.0
p => null()
print *, 'done'
end program leak
