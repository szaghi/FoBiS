# Analysis & AI

FoBiS knows more about a Fortran project than any generic tool: every source file, the module dependency
graph, the build modes with their compiler, flags and `-D` defines, and the git history. The analysis
features use that knowledge in layers.

| Layer | What it does | Needs a model? | Commands |
|-------|--------------|----------------|----------|
| **Rules** | Deterministic checks of the sources: bug-prone, obsolescent and non-portable constructs, OpenMP/OpenACC/MPI defects | No | [`fobis lint`](/ai/lint) |
| **Knowledge** | Reference material distilled from the Fortran, MPI, OpenMP and OpenACC standards and from HPC practice, searchable and cited by rule explanations | No | [`fobis kb`](/ai/knowledge-packs) |
| **LLM assistance** | Generation and explanation on top of the two layers above, with open models run locally | Yes | [`fobis ask`](/ai/ask), [`fobis build --explain`](/ai/explain), [`fobis commit`](/advanced/commit), [`fobis llm`](/ai/models) |

## Trust tiers

A finding from a rule is reproducible: the same code always gives the same result, every rule has
documentation and test cases, and rule findings can fail a CI job. Anything produced by a language model
is advisory: it is labelled as such and never fails a build unless you explicitly ask for it.
[The AI design](/concepts/ai) explains how every model answer is grounded, cited and checked.

## Commands available today

| Job | Command |
|-----|---------|
| Find bug-prone and obsolescent constructs, data races and GPU/MPI pitfalls | [`fobis lint`](/ai/lint) |
| Read why a rule matters | `fobis lint --explain COR020`, or the [rule reference](/lint-rules/) |
| Look up a standard's rule or an HPC pitfall | [`fobis kb search "firstprivate associate"`](/ai/knowledge-packs) |
| Ask a question answered from the packs and your sources, with citations | [`fobis ask "..."`](/ai/ask) |
| Find out why a build failed: missing modules, unlinked objects, then a cited cause and fix | [`fobis build --explain`](/ai/explain) |
| Report findings only on the lines a commit or pull request changes (pre-commit, CI) | [`fobis review`](/ai/review) |
| Resolve merge, rebase or cherry-pick conflicts with compiled proposals, never touching git | [`fobis merge-assist`](/ai/merge-assist) |
| Generate a test program for a module's public procedures, kept only when it builds, runs and checks | [`fobis testgen`](/ai/testgen) |
| Have the LLM confirm or dismiss findings in their code, with citations | [`fobis lint --deep`](/ai/lint#review-with-the-llm-deep) |
| Find out why a program crashed, without trusting an optimised backtrace | [`fobis run --explain`, `fobis test --explain`](/ai/explain#runtime-failures) |
| Confirm GPU data movement and sequential loops with the compiler's own report | [`fobis lint --compiler-feedback build.log`](/ai/lint#compiler-feedback) |
| Let an AI agent lint, search the packs, build and test | [`fobis mcp`](/ai/mcp) |
| Write a Conventional Commits message for the staged changes | [`fobis commit`](/advanced/commit) |
| Run open models locally, managed by FoBiS | [`fobis llm runtime install`](/ai/runtime), [`fobis llm pull coder-7b`](/ai/models) |
