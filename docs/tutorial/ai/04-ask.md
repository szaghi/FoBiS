---
title: 4. Questions about the code
---

# 4. Questions about the code

`fobis ask` answers from sources it retrieves: the knowledge packs shipped with FoBiS (the Fortran standard,
OpenMP, OpenACC, MPI, compilers, numerical practice) and, with `-p DIR`, the project's own units, each described by
its header, its documentation comment, its arguments, what it uses and calls:

::: details The model's input (`fobis ask --show-context`)
<<< @/examples/output/6-ai/04/context.txt{console}
:::

<<< @/examples/output/6-ai/04/ask.measured.txt{console}

The answer comes from the documentation comment of `test_exactness` ("Simpson cubics"), and says where.

![fobis ask -p src on the tutorial project, after a build --explain, with coder-7b run locally on the CPU](/gifs/13_llm_explain.gif)

*The question comes last in the recording. coder-7b on 6 CPU cores and no GPU; each answer takes about 45 s there, cut from the recording.*

## What a citation guarantees

A question the sources cannot answer:

<<< @/examples/output/6-ai/04/beyond.measured.txt{console}

Read the citations. The second and third statements are in their sources (nvfortran's GPU options, the
practice of keeping data on the device), but they do not answer the question. The first cites `simpson`'s entry,
which says nothing about run times. FoBiS guarantees that every statement cites a source that exists, and drops
the ones that do not. It cannot guarantee that the source says what the statement says: the citations are there
so that you can check.

::: warning
The order of the answer matters. Asked to declare first whether the sources suffice, coder-7b declined the
first question, whose answer is word for word in its first source. FoBiS asks for the statements first and the
verdict after: found while recording this chapter.
:::

::: tip What you learned
`fobis ask`, `-p`, `--show-context`, `--pack`, what citations do and do not guarantee. Reference:
[asking questions](/cookbook/ai#ask-about-the-code-and-the-standards), [knowledge packs](/cookbook/ai-setup#search-the-knowledge-packs).
:::

Next: [5. Generated tests](./05-testgen).
