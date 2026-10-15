"""
Profiles.py — Named build profiles with built-in compiler flag defaults.

Implements issue #176: named profiles (debug/release/asan/coverage) for each
supported compiler, activated via ``profile = debug`` in a fobos mode or
``--build-profile debug`` on the CLI.
"""

from __future__ import annotations

from collections.abc import Callable

# ---------------------------------------------------------------------------
# Profile flag table
# ---------------------------------------------------------------------------

# Every flag here is accepted by its compiler (tests/test_profiles.py compiles each profile with the compilers on PATH).
# Missing on purpose, measured: ifort ignores -fsanitize=address (warning #10006: an asan build without the sanitizer),
# ifx does not support -ip nor -prof-gen=srcpos (warning #10148), nvfortran rejects -fsanitize=address and --coverage
# ("Unknown switch").
PROFILES: dict[tuple[str, str], dict[str, str]] = {
    # GNU / gfortran
    ("gnu", "debug"): {
        "cflags": "-O0 -g -fcheck=all -fbacktrace -ffpe-trap=invalid,zero,overflow -Wall -Wextra",
        "lflags": "",
        "c_cflags": "-O0 -g -Wall -Wextra",
    },
    ("gnu", "release"): {
        "cflags": "-O3 -funroll-loops",
        "lflags": "",
        "c_cflags": "-O3 -funroll-loops",
    },
    ("gnu", "asan"): {
        "cflags": "-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer",
        "lflags": "-fsanitize=address,undefined",
        "c_cflags": "-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer",
    },
    ("gnu", "coverage"): {
        "cflags": "-O0 -g --coverage",
        "lflags": "--coverage",
        "c_cflags": "-O0 -g --coverage",
    },
    # Intel / ifort / ifx
    ("intel", "debug"): {
        "cflags": "-O0 -g -check all -traceback -fp-stack-check -warn all",
        "lflags": "",
        "c_cflags": "-O0 -g -traceback",
    },
    ("intel", "release"): {
        "cflags": "-O3 -ip -ipo",
        "lflags": "",
        "c_cflags": "-O3 -ipo",
    },
    ("intel", "coverage"): {
        "cflags": "-O0 -g -prof-gen=srcpos",
        "lflags": "-prof-gen=srcpos",
        "c_cflags": "-O0 -g",
    },
    ("intel_nextgen", "debug"): {
        "cflags": "-O0 -g -check all -traceback -warn all",
        "lflags": "",
        "c_cflags": "-O0 -g -traceback",
    },
    ("intel_nextgen", "release"): {
        "cflags": "-O3 -ipo",
        "lflags": "",
        "c_cflags": "-O3 -ipo",
    },
    ("intel_nextgen", "asan"): {
        "cflags": "-O1 -g -fsanitize=address",
        "lflags": "-fsanitize=address",
        "c_cflags": "-O1 -g -fsanitize=address",
    },
    # NVIDIA HPC / nvfortran
    ("nvfortran", "debug"): {
        "cflags": "-O0 -g -C -traceback -Minfo=all",
        "lflags": "",
        "c_cflags": "-O0 -g -traceback",
    },
    ("nvfortran", "release"): {
        "cflags": "-O4 -fast",
        "lflags": "",
        "c_cflags": "-O4 -fast",
    },
    # NAG
    ("nag", "debug"): {
        "cflags": "-O0 -g -C=all -u -gline",
        "lflags": "",
        "c_cflags": "-O0 -g",
    },
    ("nag", "release"): {
        "cflags": "-O4",
        "lflags": "",
        "c_cflags": "-O3",
    },
    # AMD / flang
    ("amd", "debug"): {
        "cflags": "-O0 -g -fcheck=all -fbacktrace -Wall",
        "lflags": "",
        "c_cflags": "-O0 -g",
    },
    ("amd", "release"): {
        "cflags": "-O3 -funroll-loops",
        "lflags": "",
        "c_cflags": "-O3",
    },
    # LFortran
    ("lfortran", "debug"): {
        "cflags": "-O0 -g",
        "lflags": "",
        "c_cflags": "-O0 -g",
    },
    ("lfortran", "release"): {
        "cflags": "-O3",
        "lflags": "",
        "c_cflags": "-O3",
    },
}

KNOWN_PROFILES = {"debug", "release", "asan", "coverage"}
KNOWN_COMPILERS = {"gnu", "intel", "intel_nextgen", "nvfortran", "nag", "amd", "lfortran"}
# compilers of another family: a profile missing from the table gives no flags, never gfortran's (a custom or unknown
# compiler still gets the gnu fallback)
OTHER_FAMILIES = {"intel", "intel_nextgen", "nvfortran", "pgi", "nag", "amd", "lfortran", "ibm", "g95"}


def get_profile_flags(
    compiler: str,
    profile: str,
    print_w: Callable[..., None] | None = None,
) -> dict[str, str]:
    """
    Return ``{'cflags': str, 'lflags': str, 'c_cflags': str}`` (``c_cflags``: for the ``.c`` sources) for the (compiler, profile) pair.

    A pair not in the table gives a warning and the ``gnu`` flags, except for a compiler of another family
    (``OTHER_FAMILIES``): a warning and no flags, gfortran's options are not another compiler's. Returns empty strings if
    ``profile`` is empty/None.

    Parameters
    ----------
    compiler : str
        Compiler name (e.g. 'gnu', 'intel', 'nvfortran').
    profile : str
        Profile name (e.g. 'debug', 'release', 'asan', 'coverage').
    print_w : callable, optional
        Warning printer function.

    Returns
    -------
    dict
        ``{'cflags': str, 'lflags': str, 'c_cflags': str}`` (``c_cflags``: for the ``.c`` sources)
    """
    if not profile:
        return {"cflags": "", "lflags": "", "c_cflags": ""}

    key = (compiler.lower(), profile.lower())
    if key in PROFILES:
        return dict(PROFILES[key])

    gnu_key = ("gnu", profile.lower())
    if gnu_key in PROFILES and compiler.lower() in OTHER_FAMILIES:
        if print_w:
            print_w(f"Warning: no '{profile}' profile for compiler '{compiler}': no extra flags applied.")
        return {"cflags": "", "lflags": "", "c_cflags": ""}
    if gnu_key in PROFILES:
        if print_w:
            print_w(
                f"Warning: no profile '{profile}' defined for compiler '{compiler}'; "
                f"falling back to gnu/{profile} flags."
            )
        return dict(PROFILES[gnu_key])

    # unknown profile entirely
    if print_w:
        print_w(
            f"Warning: unknown build profile '{profile}' for compiler '{compiler}'. "
            f"Known profiles: {', '.join(sorted(KNOWN_PROFILES))}. "
            "No extra flags applied."
        )
    return {"cflags": "", "lflags": "", "c_cflags": ""}


def list_profiles() -> str:
    """
    Return a formatted table of all known (compiler, profile) combinations.

    Returns
    -------
    str
        Multi-line string suitable for printing to stdout.
    """
    lines = [
        f"  {'compiler':<12} {'profile':<10} {'cflags'}",
        f"  {'--------':<12} {'-------':<10} {'------'}",
    ]
    for (compiler, profile), flags in sorted(PROFILES.items()):
        cflags = flags["cflags"]
        lflags = flags["lflags"]
        line = f"  {compiler:<12} {profile:<10} {cflags}"
        if lflags:
            line += f"  [link: {lflags}]"
        if flags.get("c_cflags"):
            line += f"  [C: {flags['c_cflags']}]"
        lines.append(line)
    return "\n".join(lines)
