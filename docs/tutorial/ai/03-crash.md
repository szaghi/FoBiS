---
title: 3. Crashes, located
---

# 3. Crashes, located

`integrate` now starts from 5 intervals, an odd number: the debug build's check in `simpson` stops the program.
`fobis run --explain` reads the runtime's message and the backtrace and goes back to the sources:

<<< @/examples/output/6-ai/03/crash.txt{console}

No model again. The program stopped itself (`error stop`), the debug build (`-O0 -g`) makes its location
trustworthy, and the statement says why. FoBiS asks a model only when the facts leave something to explain,
and only when the location can be trusted. In an optimised build a backtrace can point to the wrong line, and the
explanation says so and names the mode to rerun in.

`fobis test --explain` does the same for every failed test.

::: tip What you learned
`fobis run --explain`, `fobis test --explain`, trusted and untrusted locations. Reference:
[runtime failures](/cookbook/ai#why-the-program-crashed).
:::

Next: [4. Questions about the code](./04-ask).
