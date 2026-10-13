# Profiling

"Where does the time go?" is the first question of any optimisation, and the answer an agent should not guess.
`fobis profile` runs a declared [case](/advanced/cases) under a profiler and returns the facts mapped to the
project's code: procedures (qualified, with their file and line) and source lines.

```bash
fobis profile sod                      # gprof: sampled time and call counts
fobis profile sod --tool callgrind     # instructions per function and per source line
fobis profile sod --json --top 20      # for scripts and agents
fobis profile sod --tool nsys --runner slurm   # GPU kernels and host-device transfers, on a compute node
```

## Tools

| Tool | Build | Measures | Strength | Limit |
|------|-------|----------|----------|-------|
| `gprof` (default) | the mode rebuilt with `-pg -g` (`-p` for Intel), objects apart | self time, sampled every 0.01 s; exact call counts | close to native speed; MPI ranks each give their own file | procedures the compiler inlined count in their caller; a run shorter than a sample measures no time |
| `callgrind` (valgrind) | the mode rebuilt with `-g` added (optimisation kept) | instructions executed, exactly, per function and per source line | inlined code keeps its own source lines, so the procedures it came from are found; deterministic | instructions, not time: memory stalls and vector width are not weighed; runs many times slower |
| `nsys` (Nsight Systems) | the mode's own build | GPU kernel time and launches; host-device copies (count, MB, time) per direction; OpenACC uploads and downloads per source line; per-rank kernel time | kernels map to the OpenACC/OpenMP directive that generated them; times of the real run | times, not hardware counters (no occupancy, no memory throughput); nvfortran kernel names only |

Both builds are [build variants](/advanced/assess) (the mode's own flags, objects in `.fobis/variant/`): the
mode's build directory is not touched. The program runs in the case's run directory, with its arguments, inputs,
ranks and threads; under callgrind valgrind wraps the program (after the MPI launcher).

**Mapping to the source.** Symbols are demangled (gfortran `__mod_MOD_proc`, ifx `mod_mp_proc_`, nvfortran
`mod_proc_`) and matched to the procedures of the mode's sources; callgrind's source lines are matched to their
innermost procedure — a line in module scope (an `end module` the compiler hangs generated code on) is reported
as such. Costs outside the analysed sources (the Fortran runtime, libc, libraries) are listed as *outside the
sources*, and the share of the total inside them is given.

**MPI.** With `gprof`, each rank writes its own `gmon.out.<pid>`; the profile sums them and also reports each
process's own total and the imbalance `max / mean` (1 = balanced).

**GPU (nsys).** The program runs under `nsys profile`, one report per process named after its MPI rank
(`SLURM_PROCID`, `OMPI_COMM_WORLD_RANK` or `PMI_RANK`); `nsys stats` then exports the kernel, memory-copy and
OpenACC summaries on the submitting host (nsys must be on the PATH there too). nvfortran names each device kernel
after its procedure's scopes and the line of its directive (OpenACC `prog_17_gpu` in a program,
`module_proc_17_gpu` in a module procedure, `host_internal_17_gpu` in an internal procedure, plus `..._gpu__red` for
a reduction's final step; OpenMP `nvkernel_<symbol>F1L9_2_`), so kernel time is reported at the directive. On a
production OpenACC code (2 ranks, 2 A30) 97% of the kernel time mapped this way; the rest was in a library outside
the analysed sources. GPU
cases usually need a compute node: use `--runner slurm` ([Running on a cluster](/advanced/scheduler)).

## Real runs

**Inlining, seen through the source lines.** A module procedure doing all the work, in the same file as the
program, built at `-O2`: the compiler inlines it, so a per-function profile sees only the main program. callgrind's
lines still find it:

```text
profile app (callgrind): 1,401,346,145 instructions, 100.0% in the mode's sources
  routines (self):
    100.0%  1,400,998,076 Ir  MAIN__ = app (work.f90:25)
  project procedures (by their source lines, inlined code included):
     99.9%  work::heavy
  hottest lines:
     57.1%  work.f90:10  y(i) = sqrt(y(i) + 1.0d-3 * y(i-1))
     42.8%  work.f90:9  do i = 2, n
  note: inlined by the compiler (no function of their own, found through their source lines): work::heavy, work::light, work::light::helper
```

**A real code.** FOODIE's integrator tester running the 5-stage SSP Runge-Kutta scheme on its oscillation test
(`fobis profile ssp54 --tool callgrind`), abridged:

```text
profile ssp54 (callgrind): 12,400,302 instructions, 21.1% in the mode's sources
  routines (self):
     18.2%  2,259,761 Ir  _int_free (outside the sources: runtime, libraries)
     13.8%  1,712,512 Ir  malloc (outside the sources: runtime, libraries)
             called by flap_command_line_arguments_group_t::add (src/third_party/FLAP/...:778): 5,765 calls, 11.18%
             called by flap_command_line_interface_t::add_group (src/third_party/FLAP/...:286): 4,304 calls, 7.92%
             called by flap_command_line_argument_t::same_name (src/third_party/FLAP/...:613): 18,008 calls, 6.24%
     11.9%  1,470,077 Ir  _int_malloc (outside the sources: runtime, libraries)
      9.6%  1,187,445 Ir  free (outside the sources: runtime, libraries)
             called by flap_command_line_argument_t::same_name (...): 18,008 calls, 12.34%
             called by foodie_integrator_runge_kutta_ssp::integrate (src/lib/foodie_integrator_runge_kutta_ssp.F90:177): 8,050 calls, 5.52%
             ...
  project procedures (by their source lines, inlined code included):
      4.7%  flap_command_line_argument_t::same_name
      ...
      2.1%  foodie_integrator_runge_kutta_ssp::integrate
  hottest lines:
      2.3%  src/third_party/FLAP/src/lib/flap_command_line_argument_t.F90:623  same = adjustl(name) == adjustl(token)
      1.1%  src/lib/foodie_integrator_runge_kutta_ssp.F90:191  self%stage(s) = self%stage(s) + (self%stage(ss) * (Dt * self%alph(s, ss)))
```

More than half of the instructions are memory management, and the callers of `malloc` and `free` say whose: for
the most part FLAP's command-line setup (an argument group grown one element at a time, `adjustl` temporaries in
name comparisons), then the integrator's stage arithmetic. In this short test, parsing the command line costs more
than the integration itself. A routine outside the sources is followed by the project procedures that call it
directly, with their call counts and the inclusive cost of those calls. The
gprof profile of the same run measured no time — the run is shorter than one sample — and says so; its call counts
(`assign_real` 3220, `integrand_add_real` 2415 ...) are still exact.

**Load imbalance.** Two MPI ranks, rank 1 given twice the work of rank 0:

```text
profile ranks (gprof): 0.69 s, 100.0% in the mode's sources
  processes: 0.24, 0.45 s (imbalance max/mean 1.30)
    100.0%  0.64 s  __w_MOD_spin = w::spin (src/w.f90:4), 2 calls
```

**GPU: the data movement, found by line.** An OpenACC loop with `copyin(x) copy(y)` inside a time loop (5
steps, 4 million doubles), profiled on a cluster node (NVIDIA A30, nvfortran 25.5) with
`fobis profile copy --tool nsys --runner slurm`:

```text
profile copy (nsys): 0.0007492 s in GPU kernels, 100.0% in the mode's sources
  kernels:
     79.3%  0.0005943 s  acc_copy_10_gpu = acc_copy (src/acc_copy.f90:10), 5 launches
     11.4%  8.534e-05 s  acc_copy_16_gpu = acc_copy (src/acc_copy.f90:16), 1 launches
      9.3%  6.954e-05 s  acc_copy_16_gpu__red = acc_copy (src/acc_copy.f90:16), 1 launches
  host-device transfers:
    Device-to-Host: 6 copies, 160 MB, 0.02582 s
    Host-to-Device: 11 copies, 352 MB, 0.03201 s
  transfers by source line (OpenACC):
    upload   0.02991 s  10 calls  src/acc_copy.f90:10  !$acc parallel loop copyin(x) copy(y)
    download 0.02695 s  5 calls  src/acc_copy.f90:14  end do
    upload   0.002977 s  2 calls  src/acc_copy.f90:16  !$acc parallel loop reduction(+:s)
    download 2.568e-05 s  1 calls  src/acc_copy.f90:20  print '(a,es23.16)', 'total = ', s
  note: host-device transfers 0.05783 s = 77.2 x the kernel time: the data movement dominates, keep the data on the device
  note: kernel and transfer times measured by Nsight Systems; no hardware counters (ncu not used)
```

The copies cost 77 times the kernels, and the lines say where: the `copy(y)` clause of line 10 re-uploads and
downloads `y` every step (the download is attributed to the loop's end, line 14). A `!$acc data` region around
the time loop removes them.

**GPU: per-rank time.** Two MPI ranks, one GPU each, the second holding twice the data:

```text
profile mpiacc (nsys): 9.402e-05 s in GPU kernels, 100.0% in the mode's sources
  processes: 2.653e-05, 6.749e-05 s (imbalance max/mean 1.44)
```

## Not supported

Nsight Compute (`ncu`: occupancy, memory throughput, roofline) needs access to the GPU performance counters,
which clusters often reserve to administrators; on the cluster FoBiS was tested on, `ncu` stopped with
`ERR_NVGPUCTRPERM`, so no genuine output could be read and the backend is not written. `perf` is not supported
yet either. The MCP server exposes the command as the `profile` tool. See
[JSON output](/advanced/json-output#fobis-profile-json).
