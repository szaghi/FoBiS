# Knowledge packs

A knowledge pack is reference material FoBiS can search without a language model: distilled references
of the Fortran, OpenMP, OpenACC and MPI standards, lessons from HPC practice, the measured behaviour of the
Fortran compilers and of MPI and HDF5, and the numerical-assessment methods behind `fobis assess` and
`fobis bench` with their references. The linter cites pack sections in its rule explanations, `fobis assess`
names the section describing each family's method, and the LLM features (`fobis ask`, `--explain`, `--deep`)
ground their answers on them.

```bash
fobis kb list                                      # installed packs
fobis kb search "firstprivate associate copyin"    # best-matching sections
fobis kb show openacc:patterns#routine-for-device-callable-functions
fobis kb search "reduction" --pack openacc -k 3    # one pack, three results
```

```text
1. openacc:patterns#routine-for-device-callable-functions  (19.4)
   Patterns — OpenACC GPU offload idioms > routine for device-callable functions
   **When**: a kernel calls a helper function. **How**: annotate the function `#pragma acc routine seq`
   (or gang/worker/vector to match its internal parallelism). ...
```

Every section has a stable id, `pack:document#section`, which is what rule explanations cite
(`fobis lint --explain ACC006` lists the sections behind the rule).

## Shipped packs

| Pack | Content | Licence | Attribution |
|------|---------|---------|-------------|
| `fortran-std` | Fortran 2023 standard (ISO/IEC 1539-1:2023): distilled reference, own wording | CC-BY-4.0 | Stefano Zaghi |
| `openmp` | OpenMP API 6.0 with the November 2025 errata | CC-BY-4.0 | Stefano Zaghi; copying of the specification material by permission of the OpenMP Architecture Review Board |
| `openacc` | OpenACC API 3.4 | CC-BY-4.0 | Stefano Zaghi |
| `mpi` | MPI 5.0 | CC-BY-4.0 | Stefano Zaghi; copying of the standard material by permission of the University of Tennessee |
| `hpc-practice` | Fortran conventions and GPU/HPC pitfalls, many measured on production codes | CC-BY-4.0 | Stefano Zaghi |
| `compilers` | gfortran, ifx/ifort, nvfortran: default optimisation, runtime checks, floating-point models and FMA, precision promotion flags, stack use, module files, a comparison table | CC-BY-4.0 | Stefano Zaghi |
| `libraries` | MPI implementations (launchers, rank variables, compiler wrappers, modules, GPU awareness) and HDF5 from Fortran | CC-BY-4.0 | Stefano Zaghi |
| `numerics` | Assessing numerical error (significant digits, precision, rounding, compiler, parallel, inputs, refinement: Richardson, GCI), floating-point behaviour, tolerances, run-time measurement, with references | CC-BY-4.0 | Stefano Zaghi |

The `compilers`, `libraries` and `numerics` packs are written in the FoBiS repository (`kb-sources/`). Every
behaviour they describe was measured on small programs with the compiler or library named (versions in each
document), or is cited from the publication given in the `numerics` references; a test compiles a program with
every compiler flag the `compilers` pack names and fails if the compiler rejects it.

The standards packs are independent syntheses, not reproductions of the standards: the normative text
is the published standard. `fobis kb notice <pack>` prints each pack's licence, attribution, source
revision and full NOTICE, including the copyright notices the standards' licences require. When you
reuse pack content, keep that attribution (CC-BY-4.0).

## How retrieval works

Retrieval is lexical: no embeddings, no model. Technical questions name exact things (`firstprivate`,
`mpi_isend`, constraint `C1004`), and exact matching finds them better than semantic similarity does. Each
section is scored with BM25, with the words of its heading counting twice. A query term that is one of
the section's *symbols* (the directive, clause and routine names in its code spans, the constraint ids it
cites) adds a bonus. The whole corpus is about 800 sections, searched in milliseconds.

## Your own packs

Any markdown (notes, team conventions, a Claude skill directory) becomes a pack:

```bash
# Personal pack, for your own use only (no licence: never redistribute it)
fobis kb build ~/notes/gpu-lessons.md --name gpu-lessons --private

# A team pack committed with the project (in .fobis/kb/)
fobis kb build docs/conventions/ --name team --license CC-BY-4.0 --attribution "ACME HPC group" --project

# Install a pack built elsewhere; remove one
fobis kb add path/to/pack-dir
fobis kb remove gpu-lessons
```

The build keeps the content and drops what is addressed to an AI assistant: YAML front matter, sections
such as "How to Use This Skill", and lines telling the reader to consult a skill. Each section becomes a
searchable chunk; long sections are split at paragraph boundaries.

Packs are found in three places; on a name clash the narrowest wins:

| Scope | Directory | Use |
|-------|-----------|-----|
| project | `.fobis/kb/<name>/` | Conventions of one project, versioned with it |
| user | `~/.config/fobis/kb/<name>/` (`$XDG_CONFIG_HOME`) | Personal material |
| shipped | inside FoBiS | The packs above |

A pack directory holds `pack.ini` (name, version, title, licence, attribution, source), an optional
`NOTICE`, and `index.json` (the sections). `fobis kb build` refuses to build without a licence unless
`--private` is given.
