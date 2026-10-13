program w5
use hdf5
implicit none
integer(hid_t) :: file, space, dset, grp
integer :: err
integer(hsize_t) :: dims(2) = [3, 2]
real(8) :: rho(3, 2)
rho = reshape([1.0d0, 2.5d0, 3.0d0, 4.0d0, 5.0d0, 0.6d0], [3, 2])
call h5open_f(err)
call h5fcreate_f('sol.h5', H5F_ACC_TRUNC_F, file, err)
call h5gcreate_f(file, 'fields', grp, err)
call h5screate_simple_f(2, dims, space, err)
call h5dcreate_f(grp, 'rho', H5T_NATIVE_DOUBLE, space, dset, err)
call h5dwrite_f(dset, H5T_NATIVE_DOUBLE, rho, dims, err)
call h5dclose_f(dset, err); call h5sclose_f(space, err); call h5gclose_f(grp, err)
call h5fclose_f(file, err); call h5close_f(err)
end program w5
