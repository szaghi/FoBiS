eval "${DOCS_CLUSTER_SETUP:-}"
needs sbatch nvfortran nsys
quiet 'mkdir -p ~/.config/fobis && cp "$DOCS_CLUSTER_CONFIG" ~/.config/fobis/config.ini'
quiet "sed -i 's/^modes = debug release fast /modes = debug release fast gpu /' fobos"
quiet 'cat >> fobos <<"END"

[gpu]
help      = The OpenACC program, for an NVIDIA A30 (compute capability 8.0)
compiler  = nvfortran
cflags    = -c -O2 -acc -gpu=cc80
lflags    = -acc -gpu=cc80
src       = ./src/
build_dir = ./build/gpu/
target    = src/area_acc.F90

[case:gpu]
description = sin(x) over [0, pi] with 100 million intervals, on one GPU
target      = src/area_acc.F90
mode        = gpu
gpus        = 1
timeout     = 300
quantities  = stdout
tolerance   = trapezoid: rel 1e-12
END'
excerpt mode fobos '[gpu]'
excerpt case fobos '[case:gpu]'
measure guard 'fobis case run gpu'
measure run 'fobis case run gpu --runner slurm'
measure update 'fobis verify gpu --update --runner slurm'
measure verify 'fobis verify area --runner slurm'
measure nsys 'fobis profile gpu --tool nsys --runner slurm 2>/dev/null'
quiet "sed -i 's/^!\$acc update self(y)\$/!\$acc update self(y(0:0), y(n:n))/' src/area_acc.F90"
show fix 'grep -n "update self" src/area_acc.F90'
measure nsys-fixed 'fobis profile gpu --tool nsys --runner slurm 2>/dev/null'
measure verify-fixed 'fobis verify gpu --runner slurm'
