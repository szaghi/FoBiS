# Analysis & AI

FoBiS knows more about a Fortran project than any generic tool: every source file, the module dependency
graph, the build modes with their compiler, flags and `-D` defines, and the git history. The analysis
features use that knowledge in layers.

| Layer | What it does | Needs a model? | Commands |
|-------|--------------|----------------|----------|
| **Rules** | Deterministic checks of the sources: bug-prone, obsolescent and non-portable constructs, OpenMP/OpenACC/MPI defects | No | [`fobis lint`](/ai/lint) |
| **Knowledge** | Reference material distilled from the Fortran, MPI, OpenMP and OpenACC standards and from HPC practice, searchable and cited by rule explanations | No | [`fobis kb`](/ai/knowledge-packs) |
| **LLM assistance** | Generation and explanation on top of the two layers above, with open models run locally | Yes | [`fobis commit`](/advanced/commit), [`fobis llm`](/ai/models) |

## Trust tiers

A finding from a rule is reproducible: the same code always gives the same result, every rule has
documentation and test cases, and rule findings can fail a CI job. Anything produced by a language model
is advisory: it is labelled as such and never fails a build unless you explicitly ask for it.

## Commands available today

| Job | Command |
|-----|---------|
| Find bug-prone and obsolescent constructs, data races and GPU/MPI pitfalls | [`fobis lint`](/ai/lint) |
| Read why a rule matters | `fobis lint --explain COR020`, or the [rule reference](/lint-rules/) |
| Look up a standard's rule or an HPC pitfall | [`fobis kb search "firstprivate associate"`](/ai/knowledge-packs) |
| Confirm GPU data movement and sequential loops with the compiler's own report | [`fobis lint --compiler-feedback build.log`](/ai/lint#compiler-feedback) |
| Let an AI agent lint, search the packs, build and test | [`fobis mcp`](/ai/mcp) |
| Write a Conventional Commits message for the staged changes | [`fobis commit`](/advanced/commit) |
| Download and manage open models for local use | [`fobis llm pull coder-7b`](/ai/models) |
