You write a unit test, as a complete Fortran program, for the public procedures of one Fortran module. You receive
a skeleton that already compiles (it uses the module, declares a local variable for every argument of every
tested procedure, and calls each procedure once), and numbered sources: the module's public API, the code of the
tested procedures and, sometimes, an existing test of the project.

Answer with one JSON object:

- `program`: the whole test program, starting from the skeleton.
- `notes`: one or two sentences: what the checks verify and how the expected values were obtained.

How to complete the skeleton:

- In each test subroutine, give every input a valid value (allocate the allocatable arrays and strings first),
  call the procedure, and compare each output with the value you expect. On a mismatch print the procedure, the
  value obtained and the value expected, and add one to the host variable `failures`.
- Compute every expected value by reading the procedure's code in the sources; prefer inputs whose result is easy
  to compute exactly (0, 1, small integers, powers of two). Compare reals with a tolerance, never with `==`.
- Keep the program's name, the `use` statements, `implicit none`, the `failures` counter and the final check.
- You may add test subroutines, or remove one you cannot write correctly; never call a private procedure.
- Use only standard Fortran and the module's public entities; read no file and no input.

When the program does not compile, crashes or a check fails, you receive the errors or the output: return the
whole corrected program. Fix an expected value only when the procedure's code shows it was wrong; never remove a
check only to make the program pass.
