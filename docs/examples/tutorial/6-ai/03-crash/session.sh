quiet 'git reset -q --hard'
quiet "sed -i 's/^n = 4\$/n = 5/' src/integrate.F90"
quiet 'fobis build --quiet'
export GFORTRAN_UNBUFFERED_ALL=1  # the program's output in order with its error messages
show crash 'fobis run --no-build --explain'
