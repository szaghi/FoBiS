---
title: 7. Commit messages
---

# 7. Commit messages

`area` prints the midpoint rule's result too:

<<< @/examples/output/6-ai/07/diff.txt{console}

Before any model, `fobis commit --show-facts` prints what FoBiS knows about the staged change: the scopes the
history of these files suggests, which lines are code, comments or directives, which procedures changed, whether
an interface changed:

<<< @/examples/output/6-ai/07/facts.txt{console}

The model writes the message from the diff and these facts, in the Conventional Commits form, and the scope is
restricted to the candidates:

<<< @/examples/output/6-ai/07/commit.measured.txt{console}

The scope is right and the description reads well, but the type is wrong: a program that prints a new result is
a `feat`, not a `refactor`. That is why `fobis commit` prints the message and commits nothing; `--apply` asks
before running `git commit`.

![fobis llm doctor and fobis commit with a local model](/gifs/12_llm_commit.gif)

::: tip What you learned
`fobis commit`, `--show-facts`, `--apply`. Reference: [commit messages](/cookbook/ai#commit-messages).
:::

Next: [8. Merge conflicts](./08-merge).
