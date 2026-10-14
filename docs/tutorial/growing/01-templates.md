---
title: 1. Templates and variables
---

# 1. Templates and variables

The fobos of [First steps](../first-steps/05-dependencies) repeats itself: `compiler = gnu` five times, the program's
file three times, `-O2` three times. Each copy is a place to forget when something changes. Two fobos features remove
the copies:

- a **template** is a section whose keys a mode inherits with `template = NAME`; a template can itself use a template;
- a **variable** is a key starting with `$`, in any section, replaced wherever `$NAME` appears.

<<< @/examples/tutorial/2-growing/01-templates/files/fobos{ini}

`[template-library]` builds on `[template-gnu]` and adds what both libraries share; each library mode keeps only what
is its own. A mode's own keys win over the template's.

The modes are the same:

<<< @/examples/output/2-growing/01/lmodes.txt{console}

and resolve to the same options: `introspect` shows what a mode ends up with, after templates and variables:

<<< @/examples/output/2-growing/01/options.txt{console}

Since the flags did not change, the objects of the previous chapters are still up to date:

<<< @/examples/output/2-growing/01/release.txt{console}

<<< @/examples/output/2-growing/01/static.txt{console}

::: tip What you learned
Templates (`template = NAME`, chained), `$variables`, and `fobis introspect` to see the result. Reference:
[templates](/fobos/templates), [variables](/fobos/variables), [`introspect`](/reference/introspect).
:::

Next: [2. Build profiles and features](./02-profiles).
