---
title: 5. Generated tests
---

# 5. Generated tests

`fobis testgen MODULE` writes a test program for a module's public procedures. Without a model it gives a
skeleton: the program, the declarations of every argument, and the calls. FoBiS builds it in a scratch copy of
the project before showing it, so what you see compiles:

<<< @/examples/output/6-ai/05/skeleton.txt{console}

With the model, the skeleton is the starting point. The model fills in inputs and checks, and FoBiS builds and runs
the program in the scratch copy. It refuses a program that does not compile, fails, or checks nothing, and sends
the compiler's errors or the failing check back, for up to three more attempts:

<<< @/examples/output/6-ai/05/testgen.measured.txt{console}

Accepted at the first attempt: the nodes `±0.774596669241483` (that is `±sqrt(3/5)`) and `0` and the weights
`5/9`, `8/9`, `5/9` are those of the 3-point Gauss-Legendre rule, and the program passed against the real
implementation. "Review it before committing" is meant: a test checks what the model believed. Here the values
can be checked against any table; for a procedure without a known answer, the checks may only repeat what the
code does. `--apply` writes the program to the test directory, never over an existing file.

::: tip What you learned
`fobis testgen`, `--skeleton`, `--context`, `--apply`, what an accepted test proves. Reference:
[test generation](/ai/testgen).
:::

Next: [6. A second reader for a change](./06-review).
