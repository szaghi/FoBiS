program main
use iso_c_binding, only : c_int
use iso_fortran_env, only : error_unit
implicit none
integer(c_int) :: tally
tally = this_image() ! this image's contribution
call co_sum(tally)
verify: block
  integer(c_int) :: image
  if (tally/=sum([(image,image=1,num_images())])) then
     write(error_unit,'(a,i5)') "Incorrect tally on image ",this_image()
     error stop
  end if
end block verify
! Wait for all images to pass the test
sync all
if (this_image()==1) print *,"Test passed"
end program
