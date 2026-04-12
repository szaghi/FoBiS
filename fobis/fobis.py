#!/usr/bin/env python
"""
FoBiS.py, Fortran Building System
"""

# Copyright (C) 2015  Stefano Zaghi
#
# This file is part of FoBiS.py.
#
# FoBiS.py is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# FoBiS.py is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with FoBiS.py. If not, see <http://www.gnu.org/licenses/>.
# modules loading
import configparser
import os
import shutil
import sys

from .Builder import Builder
from .Cleaner import Cleaner
from .FoBiSConfig import FoBiSConfig
from .Gcov import Gcov, _mermaid_pie
from .ParsedFile import ParsedFile
from .utils import dependency_hiearchy, remove_other_main, safe_mkdir, syswork


def main():
    """
    Main function.
    """
    # Typer/Click completion runs by setting _<PROG>_COMPLETE in the environment,
    # or by passing --install-completion / --show-completion.
    # FoBiSConfig uses CliRunner which isolates os.environ, so the completion env
    # var is never forwarded and tab-completion silently produces no output.
    # Detect both cases here and invoke the Typer app directly.
    _completion_flags = frozenset({"--install-completion", "--show-completion"})
    _prog = os.path.basename(sys.argv[0]).upper().replace(".", "_").replace("-", "_")
    if os.environ.get(f"_{_prog}_COMPLETE") or _completion_flags.intersection(sys.argv[1:]):
        from .cli import app as _app

        _app()
        return
    run_fobis()
    sys.exit(0)


def run_fobis(fake_args=None):
    """
    Run FoBiS accordingly to the user configuration.

    Parameters
    ----------
    fake_args : list
      list containing fake CLAs for using without CLI
    """
    configuration = FoBiSConfig(fake_args=fake_args)
    if configuration.cliargs.which == "rule":
        run_fobis_rule(configuration)
    else:
        if configuration.cliargs.lmodes:
            configuration.fobos.modes_list()
            sys.exit(0)
        _json = getattr(configuration.cliargs, "json_output", False)
        if configuration.cliargs.which == "clean":
            run_fobis_clean_json(configuration) if _json else run_fobis_clean(configuration)
        if configuration.cliargs.which == "build":
            run_fobis_build_json(configuration) if _json else run_fobis_build(configuration)
        if configuration.cliargs.which == "install":
            run_fobis_install(configuration)
        if configuration.cliargs.which == "doctests":
            run_fobis_doctests(configuration)
        if configuration.cliargs.which == "fetch":
            run_fobis_fetch_json(configuration) if _json else run_fobis_fetch(configuration)
        if configuration.cliargs.which == "scaffold":
            run_fobis_scaffold(configuration)
        if configuration.cliargs.which == "commit":
            run_fobis_commit(configuration)
        if configuration.cliargs.which == "tree":
            run_fobis_tree(configuration)
        if configuration.cliargs.which == "run":
            run_fobis_run(configuration)
        if configuration.cliargs.which == "check":
            run_fobis_check(configuration)
        if configuration.cliargs.which == "test":
            run_fobis_test(configuration)
        if configuration.cliargs.which == "introspect":
            run_fobis_introspect(configuration)
        if configuration.cliargs.which == "coverage":
            run_fobis_coverage(configuration)
    return


class _JsonCollector:
    """No-op buffering sinks for print_n / print_w callbacks used in JSON output mode."""

    def __init__(self):
        self.messages: list[str] = []
        self.warnings: list[str] = []

    def print_n(self, message: str = "") -> None:
        self.messages.append(message)

    def print_w(self, message: str = "") -> None:
        self.warnings.append(message)


def _obj_files(directory: str) -> set[str]:
    """Return the set of .o file paths under *directory*."""
    result: set[str] = set()
    if os.path.exists(directory):
        for root, _, files in os.walk(directory):
            for f in files:
                if f.endswith(".o"):
                    result.add(os.path.join(root, f))
    return result


def _all_files(directory: str) -> set[str]:
    """Return all file paths under *directory*."""
    result: set[str] = set()
    if os.path.exists(directory):
        for root, _, files in os.walk(directory):
            for f in files:
                result.add(os.path.join(root, f))
    return result


def run_fobis_build_json(configuration):
    """Run FoBiS build and emit a structured JSON result to stdout.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    import io
    import json

    collector = _JsonCollector()
    configuration.print_b = collector.print_n
    configuration.print_r = collector.print_w

    obj_dir = os.path.normpath(os.path.join(configuration.cliargs.build_dir, configuration.cliargs.obj_dir))
    pre_objects = _obj_files(obj_dir)

    old_stderr = sys.stderr
    sys.stderr = io.StringIO()
    exit_code = 0
    try:
        run_fobis_build(configuration)
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else 1
    finally:
        stderr_text = sys.stderr.getvalue()
        sys.stderr = old_stderr

    post_objects = _obj_files(obj_dir)
    objects_compiled = len(post_objects - pre_objects)

    errors = list(collector.warnings)
    if stderr_text.strip():
        errors.extend(stderr_text.strip().splitlines())

    result = {
        "status": "ok" if exit_code == 0 else "error",
        "target": configuration.cliargs.target or "all",
        "objects_compiled": objects_compiled,
        "errors": errors,
    }
    print(json.dumps(result, indent=2))
    if exit_code != 0:
        sys.exit(exit_code)


def run_fobis_clean_json(configuration):
    """Run FoBiS clean and emit a structured JSON result to stdout.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    import json

    obj_dir = os.path.normpath(os.path.join(configuration.cliargs.build_dir, configuration.cliargs.obj_dir))
    mod_dir = os.path.normpath(os.path.join(configuration.cliargs.build_dir, configuration.cliargs.mod_dir))
    pre_files = _all_files(obj_dir) | _all_files(mod_dir)

    collector = _JsonCollector()
    configuration.print_r = collector.print_w

    exit_code = 0
    try:
        run_fobis_clean(configuration)
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else 1

    post_files = _all_files(obj_dir) | _all_files(mod_dir)
    removed = sorted(pre_files - post_files)

    result = {
        "status": "ok" if exit_code == 0 else "error",
        "removed": removed,
        "errors": list(collector.warnings),
    }
    print(json.dumps(result, indent=2))
    if exit_code != 0:
        sys.exit(exit_code)


def run_fobis_fetch_json(configuration):
    """Run FoBiS fetch and emit a structured JSON result to stdout.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    import io
    import json

    from .Fetcher import Fetcher

    collector = _JsonCollector()

    old_stderr = sys.stderr
    sys.stderr = io.StringIO()
    exit_code = 0
    deps_info: list[dict] = []
    try:
        deps_dir = configuration.cliargs.deps_dir or configuration.fobos.get_deps_dir()
        fetcher = Fetcher(deps_dir=deps_dir, print_n=collector.print_n, print_w=collector.print_w)
        deps = configuration.fobos.get_dependencies()
        if deps:
            for name, spec in deps.items():
                parsed = fetcher.parse_dep_spec(spec)
                use_mode = parsed.get("use", "sources")
                dep_path, _commit = fetcher.fetch(
                    name,
                    parsed["url"],
                    branch=parsed.get("branch"),
                    tag=parsed.get("tag"),
                    rev=parsed.get("rev"),
                    update=configuration.cliargs.update,
                )
                if not configuration.cliargs.no_build and use_mode == "fobos":
                    fetcher.build_dep(name, dep_path, mode=parsed.get("mode"))
                deps_info.append({"name": name, "path": dep_path, "use": use_mode})
            fetcher.save_config(deps_info)
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else 1
    finally:
        stderr_text = sys.stderr.getvalue()
        sys.stderr = old_stderr

    errors = list(collector.warnings)
    if stderr_text.strip():
        errors.extend(stderr_text.strip().splitlines())

    result = {
        "status": "ok" if exit_code == 0 else "error",
        "deps_dir": str(getattr(configuration.cliargs, "deps_dir", None) or configuration.fobos.get_deps_dir()),
        "dependencies": deps_info,
        "errors": errors,
    }
    print(json.dumps(result, indent=2))
    if exit_code != 0:
        sys.exit(exit_code)


def run_fobis_fetch(configuration):
    """
    Run FoBiS in fetch mode: clone/update and optionally build GitHub dependencies.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    from .Fetcher import Fetcher

    deps_dir = configuration.cliargs.deps_dir or configuration.fobos.get_deps_dir()
    frozen = getattr(configuration.cliargs, "frozen", False)
    fetcher = Fetcher(deps_dir=deps_dir, print_n=configuration.print_b, print_w=configuration.print_r)
    deps = configuration.fobos.get_dependencies()
    if not deps:
        configuration.print_r("No [dependencies] section found in fobos file")
        return

    # Load existing lock file for frozen mode or verification
    lock = fetcher.load_lock()

    if frozen and not lock:
        configuration.print_r(
            "Error: --frozen requires fobos.lock to be present but none was found. "
            "Run 'fobis fetch' first to generate it."
        )
        sys.exit(1)

    deps_info = []
    lock_entries = []
    for name, spec in deps.items():
        parsed = fetcher.parse_dep_spec(spec)
        use_mode = parsed.get("use", "sources")

        # Semver resolution
        if "semver" in parsed:
            constraint = parsed["semver"]
            # In frozen mode: use locked resolved tag
            if frozen and name in lock and lock[name].get("resolved"):
                resolved_tag = lock[name]["resolved"]
                configuration.print_b(f"[frozen] {name}: using locked resolved tag {resolved_tag}")
                parsed["tag"] = resolved_tag
            elif not configuration.cliargs.update and name in lock and lock[name].get("resolved"):
                parsed["tag"] = lock[name]["resolved"]
            else:
                resolved_tag = fetcher.resolve_semver(name, parsed["url"], constraint)
                parsed["tag"] = resolved_tag

        # Frozen mode: pin to lockfile commit
        frozen_commit = None
        if frozen and name in lock:
            frozen_commit = lock[name].get("commit")

        dep_path, commit_sha = fetcher.fetch(
            name,
            parsed["url"],
            branch=parsed.get("branch"),
            tag=parsed.get("tag"),
            rev=parsed.get("rev"),
            update=configuration.cliargs.update,
            frozen_commit=frozen_commit,
        )

        # Verify against lockfile (non-frozen: warn only)
        if lock and not frozen:
            fetcher.verify_lock(name, dep_path, lock)

        if not configuration.cliargs.no_build and use_mode == "fobos":
            fetcher.build_dep(name, dep_path, mode=parsed.get("mode"))

        deps_info.append({"name": name, "path": dep_path, "mode": parsed.get("mode", ""), "use": use_mode})

        # Build lock entry
        lock_entry: dict[str, str] = {
            "name": name,
            "url": parsed["url"],
            "commit": commit_sha,
            "sha256": fetcher._compute_sha256(dep_path),
        }
        for pin_key in ("branch", "tag", "rev", "semver"):
            if pin_key in parsed:
                lock_entry[pin_key] = parsed[pin_key]
        if "semver" in parsed and parsed.get("tag"):
            lock_entry["resolved"] = parsed["tag"]
        lock_entries.append(lock_entry)

    fetcher.save_config(deps_info)
    # Write / update lock file (not in frozen mode)
    if not frozen:
        fetcher.save_lock(lock_entries)


def run_fobis_commit(configuration):
    """
    Run FoBiS in commit mode: generate a Conventional Commits message via local LLM.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    import subprocess

    from .Commit import generate
    from .UserConfig import UserConfig

    cliargs = configuration.cliargs
    ucfg = UserConfig(path=getattr(cliargs, "config", None))

    if getattr(cliargs, "init_config", False):
        ucfg.create_default()
        configuration.print_b(f"Config file created: {ucfg.path}")
        return

    if getattr(cliargs, "show_config", False):
        configuration.print_b(ucfg.show())
        return

    # CLI flags override config file values
    backend = getattr(cliargs, "backend", None) or ucfg.llm_backend
    url = getattr(cliargs, "url", None) or ucfg.llm_url
    model = getattr(cliargs, "model", None) or ucfg.llm_model
    max_diff = getattr(cliargs, "max_diff", None) or ucfg.llm_max_diff_chars
    refine_passes_cli = getattr(cliargs, "refine_passes", None)
    refine_passes = refine_passes_cli if refine_passes_cli is not None else ucfg.llm_refine_passes

    message = generate(
        backend=backend,
        url=url,
        model=model,
        max_diff_chars=max_diff,
        refine_passes=refine_passes,
        print_n=configuration.print_b,
        print_w=configuration.print_r,
    )

    configuration.print_b("")
    configuration.print_b(message)

    if getattr(cliargs, "apply", False):
        configuration.print_b("")
        answer = input("Commit with this message? [y/N] ").strip().lower()
        if answer == "y":
            subprocess.run(["git", "commit", "-m", message])
        else:
            configuration.print_r("Aborted.")


def run_fobis_scaffold(configuration):
    """
    Run FoBiS in scaffold mode: manage project boilerplate templates.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    from .Scaffolder import Scaffolder, get_project_vars

    project_vars = get_project_vars(fobos=configuration.fobos)
    scaffolder = Scaffolder(
        project_vars=project_vars,
        print_n=configuration.print_b,
        print_w=configuration.print_r,
    )
    action = configuration.cliargs.action
    if action == "status":
        scaffolder.status(
            files_glob=configuration.cliargs.files,
            strict=configuration.cliargs.strict,
        )
    elif action == "sync":
        scaffolder.sync(
            dry_run=configuration.cliargs.dry_run,
            yes=configuration.cliargs.yes,
            files_glob=configuration.cliargs.files,
        )
    elif action == "init":
        scaffolder.init(yes=configuration.cliargs.yes)
    elif action == "list":
        scaffolder.list_files()
    else:
        configuration.print_r(f"Unknown scaffold action: {action}")
        sys.exit(1)


def run_fobis_build(configuration):
    """
    Run FoBiS in build mode.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    from copy import deepcopy

    fobos = configuration.fobos
    cliargs = configuration.cliargs

    # Print active features if any
    active_features = getattr(cliargs, "active_features", [])
    if active_features:
        configuration.print_b("Active features: " + ", ".join(active_features))

    # Check for multi-target [[target.*]] sections
    multi_targets = fobos.get_targets("target") if fobos.fobos else []
    example_targets = fobos.get_targets("example") if fobos.fobos else []
    examples_flag = getattr(cliargs, "examples", False)
    target_filter = getattr(cliargs, "target_filter", [])

    if multi_targets:
        # Validate: mode-level 'target' and [[target.*]] sections are mutually exclusive
        if cliargs.target and multi_targets:
            configuration.print_r(
                "Error: fobos has both a mode-level 'target' key and [[target.*]] sections. "
                "They are mutually exclusive."
            )
            sys.exit(1)

        all_build_targets = list(multi_targets)
        if examples_flag:
            all_build_targets += example_targets

        if target_filter:
            all_build_targets = [t for t in all_build_targets if t["name"] in target_filter]
            if not all_build_targets:
                configuration.print_r(f"Error: no targets match filter {target_filter}")
                sys.exit(1)

        # Scan source files once for all targets
        pfiles_all = parse_files(configuration=configuration)
        for t_dict in all_build_targets:
            t_cliargs = _cliargs_for_target(cliargs, t_dict)
            t_builder = Builder(cliargs=t_cliargs, print_n=configuration.print_b, print_w=configuration.print_r)
            dependency_hiearchy(
                builder=t_builder,
                pfiles=pfiles_all,
                print_w=configuration.print_r,
                force_compile=t_cliargs.force_compile,
            )
            nomodlibs = build_nomodlibs(
                configuration=configuration, pfiles=pfiles_all, builder=t_builder
            )
            submodules = build_submodules(
                configuration=configuration, pfiles=pfiles_all, builder=t_builder
            )
            # pre_build hooks
            pre_rules = getattr(t_cliargs, "pre_build", []) or []
            if isinstance(pre_rules, str):
                pre_rules = pre_rules.split()
            for rule_name in pre_rules:
                fobos.rule_execute(rule_name)

            source = t_dict.get("source") or t_dict.get("target", "")
            for pfile in pfiles_all:
                if os.path.basename(pfile.name) == os.path.basename(source):
                    build_pfile(
                        configuration=configuration,
                        pfile=pfile,
                        pfiles=pfiles_all,
                        nomodlibs=nomodlibs,
                        submodules=submodules,
                        builder=t_builder,
                    )
                    # post_build hooks
                    post_rules = getattr(t_cliargs, "post_build", []) or []
                    if isinstance(post_rules, str):
                        post_rules = post_rules.split()
                    for rule_name in post_rules:
                        fobos.rule_execute(rule_name)
                    break
        return

    # Standard (single-target) build path
    builder = Builder(cliargs=cliargs, print_n=configuration.print_b, print_w=configuration.print_r)
    pfiles = parse_files(configuration=configuration)
    dependency_hiearchy(
        builder=builder, pfiles=pfiles, print_w=configuration.print_r, force_compile=cliargs.force_compile
    )
    if cliargs.makefile:
        save_makefile(configuration=configuration, pfiles=pfiles, builder=builder)
        return
    nomodlibs = build_nomodlibs(configuration=configuration, pfiles=pfiles, builder=builder)
    submodules = build_submodules(configuration=configuration, pfiles=pfiles, builder=builder)

    # Execute pre_build lifecycle hooks
    pre_rules = getattr(cliargs, "pre_build", []) or []
    if isinstance(pre_rules, str):
        pre_rules = pre_rules.split()
    for rule_name in pre_rules:
        fobos.rule_execute(rule_name)

    build_succeeded = False
    # building target or all programs found
    for pfile in pfiles:
        if cliargs.build_all:
            build_pfile(
                configuration=configuration,
                pfile=pfile,
                pfiles=pfiles,
                nomodlibs=nomodlibs,
                submodules=submodules,
                builder=builder,
            )
            build_succeeded = True
        else:
            if cliargs.target:
                if os.path.basename(cliargs.target) == os.path.basename(pfile.name):
                    build_pfile(
                        configuration=configuration,
                        pfile=pfile,
                        pfiles=pfiles,
                        nomodlibs=nomodlibs,
                        submodules=submodules,
                        builder=builder,
                    )
                    build_succeeded = True
            else:
                if pfile.program:
                    build_pfile(
                        configuration=configuration,
                        pfile=pfile,
                        pfiles=pfiles,
                        nomodlibs=nomodlibs,
                        submodules=submodules,
                        builder=builder,
                    )
                    build_succeeded = True

    # Execute post_build lifecycle hooks (only on success)
    if build_succeeded:
        post_rules = getattr(cliargs, "post_build", []) or []
        if isinstance(post_rules, str):
            post_rules = post_rules.split()
        for rule_name in post_rules:
            fobos.rule_execute(rule_name)


def _cliargs_for_target(base_cliargs, target_dict):
    """
    Create a per-target cliargs by deep-copying base and applying overrides.

    Parameters
    ----------
    base_cliargs : argparse.Namespace
    target_dict : dict

    Returns
    -------
    argparse.Namespace
    """
    from copy import deepcopy
    import argparse

    t_cliargs = deepcopy(base_cliargs)
    # Apply source -> target
    if "source" in target_dict:
        t_cliargs.target = target_dict["source"]
    # Apply output
    if "output" in target_dict:
        t_cliargs.output = target_dict["output"]
    # Apply per-target overrides (cflags, lflags, etc.)
    for key, value in target_dict.items():
        if key in ("name", "source", "output"):
            continue
        if hasattr(t_cliargs, key):
            attr = getattr(t_cliargs, key)
            if isinstance(attr, bool):
                setattr(t_cliargs, key, value.lower() in ("true", "1", "yes"))
            elif isinstance(attr, int):
                try:
                    setattr(t_cliargs, key, int(value))
                except ValueError:
                    pass
            elif isinstance(attr, list):
                setattr(t_cliargs, key, value.split())
            else:
                setattr(t_cliargs, key, value)
    return t_cliargs


def run_fobis_clean(configuration):
    """
    Run FoBiS in build mode.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    cleaner = Cleaner(cliargs=configuration.cliargs, print_w=configuration.print_r)
    if not configuration.cliargs.only_obj and not configuration.cliargs.only_target:
        cleaner.clean_mod()
        cleaner.clean_obj()
        cleaner.clean_target()
    if configuration.cliargs.only_obj:
        cleaner.clean_mod()
        cleaner.clean_obj()
    if configuration.cliargs.only_target:
        cleaner.clean_target()


def run_fobis_rule(configuration):
    """
    Run FoBiS in build mode.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    if configuration.cliargs.list:
        configuration.fobos.rules_list(quiet=configuration.cliargs.quiet)
    elif configuration.cliargs.execute:
        configuration.fobos.rule_execute(rule=configuration.cliargs.execute, quiet=configuration.cliargs.quiet)
    elif configuration.cliargs.get:
        configuration.fobos.get(option=configuration.cliargs.get, mode=configuration.cliargs.mode)
    elif configuration.cliargs.get_output_name:
        configuration.fobos.get_output_name(mode=configuration.cliargs.mode)
    elif configuration.cliargs.ford:
        result = syswork("ford " + configuration.cliargs.ford)
        if result[0] != 0:
            configuration.print_r(result[1])
        else:
            configuration.print_b(result[1])
    elif configuration.cliargs.gcov_analyzer:
        gcov_analyzer(configuration=configuration)
    elif configuration.cliargs.is_ascii_kind_supported:
        is_ascii_kind_supported(configuration=configuration)
    elif configuration.cliargs.is_ucs4_kind_supported:
        is_ucs4_kind_supported(configuration=configuration)
    elif configuration.cliargs.is_float128_kind_supported:
        is_float128_kind_supported(configuration=configuration)


def run_fobis_install(configuration):
    """
    Run FoBiS in install mode.

    When 'repo' is provided (e.g. 'szaghi/FLAP' or a full URL) the command
    clones the GitHub-hosted FoBiS project, builds it with --track_build, and
    installs the resulting artifacts to the specified prefix.

    Without 'repo', the existing behaviour is preserved: install previously
    built artifacts recorded in .track_build files inside the build directory.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    if configuration.cliargs.repo:
        from .Fetcher import Fetcher

        deps_dir = configuration.cliargs.deps_dir or os.path.join(os.path.expanduser("~"), ".fobis")
        fetcher = Fetcher(deps_dir=deps_dir, print_n=configuration.print_b, print_w=configuration.print_r)
        fetcher.install_from_github(
            repo=configuration.cliargs.repo,
            branch=configuration.cliargs.branch,
            tag=configuration.cliargs.tag,
            rev=configuration.cliargs.rev,
            mode=configuration.cliargs.mode,
            update=configuration.cliargs.update,
            no_build=configuration.cliargs.no_build,
            prefix=configuration.cliargs.prefix,
            bin_dir=configuration.cliargs.bin,
            lib_dir=configuration.cliargs.lib,
            include_dir=configuration.cliargs.include,
        )
        return

    if not os.path.exists(configuration.cliargs.build_dir):
        configuration.fobos.print_w('Error: build directory not found! Maybe you have to run "FoBiS.py build" before.')
        sys.exit(1)
    safe_mkdir(directory=configuration.cliargs.prefix)
    for filename in os.listdir(configuration.cliargs.build_dir):
        if filename.endswith(".track_build"):
            is_program = False
            is_library = False
            track_file = configparser.ConfigParser()
            track_file.read(os.path.join(configuration.cliargs.build_dir, filename))
            if track_file.has_option(section="build", option="output"):
                output = track_file.get(section="build", option="output")
                if track_file.has_option(section="build", option="program"):
                    is_program = track_file.get(section="build", option="program")
                if track_file.has_option(section="build", option="library"):
                    is_library = track_file.get(section="build", option="library")
                if is_program:
                    bin_path = os.path.join(configuration.cliargs.prefix, configuration.cliargs.bin)
                    safe_mkdir(directory=bin_path)
                    configuration.fobos.print_n('Install "' + output + '" in "' + bin_path + '"')
                    shutil.copy(output, bin_path)
                if is_library:
                    lib_path = os.path.join(configuration.cliargs.prefix, configuration.cliargs.lib)
                    safe_mkdir(directory=lib_path)
                    configuration.fobos.print_n('Install "' + output + '" in "' + lib_path + '"')
                    shutil.copy(output, lib_path)
                    if track_file.has_option(section="build", option="mod_file"):
                        mod_file = track_file.get(section="build", option="mod_file")
                        inc_path = os.path.join(configuration.cliargs.prefix, configuration.cliargs.include)
                        safe_mkdir(directory=inc_path)
                        configuration.fobos.print_n('Install "' + mod_file + '" in "' + inc_path + '"')
                        shutil.copy(mod_file, inc_path)


def run_fobis_doctests(configuration):
    """
    Run FoBiS in build mode.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    builder = Builder(cliargs=configuration.cliargs, print_n=configuration.print_b, print_w=configuration.print_r)
    pfiles = parse_files(configuration=configuration)
    dependency_hiearchy(
        builder=builder, pfiles=pfiles, print_w=configuration.print_r, force_compile=configuration.cliargs.force_compile
    )
    nomodlibs = build_nomodlibs(configuration=configuration, pfiles=pfiles, builder=builder)
    doctests, doctests_dirs = parse_doctests(configuration=configuration, pfiles=pfiles, builder=builder)
    for pfile in pfiles:
        doctests.append(pfile)
    dependency_hiearchy(
        builder=builder,
        pfiles=doctests,
        print_w=configuration.print_r,
        force_compile=configuration.cliargs.force_compile,
    )
    test_doctests(configuration=configuration, doctests=doctests, pfiles=pfiles, nomodlibs=nomodlibs, builder=builder)
    if not configuration.cliargs.keep_volatile_doctests:
        for doc_dir in doctests_dirs:
            if os.path.isdir(doc_dir):
                shutil.rmtree(doc_dir)


def parse_files(configuration, src_dir=None, is_doctest=False):
    """
    Parse files and return the list of parsed files.

    Parameters
    ----------
    configuration : FoBiSConfig()
    src_dir: str
      root directory into which search; if omitted use configuration.cliargs.src

    Returns
    -------
    list
      list of ParsedFile() objects
    """
    pfiles = []
    if src_dir is not None:
        src = [src_dir]
    else:
        src = configuration.cliargs.src
    for src_dir in src:
        if configuration.cliargs.disable_recursive_search:
            for filename in os.listdir(src_dir):
                if any(
                    os.path.splitext(os.path.basename(filename))[1] == ext for ext in configuration.cliargs.extensions
                ):
                    if os.path.basename(filename) not in [
                        os.path.basename(exc) for exc in configuration.cliargs.exclude
                    ] and all(exc not in os.path.dirname(filename) for exc in configuration.cliargs.exclude_dirs):
                        pfile = ParsedFile(name=os.path.join(src_dir, filename), is_doctest=is_doctest)
                        if is_doctest:
                            pfile.parse(
                                inc=configuration.cliargs.inc,
                                preprocessor=configuration.cliargs.doctests_preprocessor,
                                preproc=configuration.cliargs.preproc,
                                include=configuration.cliargs.include,
                            )
                        else:
                            pfile.parse(
                                inc=configuration.cliargs.inc,
                                preproc=configuration.cliargs.preproc,
                                include=configuration.cliargs.include,
                            )
                        pfiles.append(pfile)
        else:
            for root, _, files in os.walk(src_dir):
                for filename in files:
                    if any(
                        os.path.splitext(os.path.basename(filename))[1] == ext
                        for ext in configuration.cliargs.extensions
                    ):
                        if os.path.basename(filename) not in [
                            os.path.basename(exc) for exc in configuration.cliargs.exclude
                        ] and all(exc not in root for exc in configuration.cliargs.exclude_dirs):
                            filen = os.path.join(root, filename)
                            pfile = ParsedFile(name=filen, is_doctest=is_doctest)
                            if is_doctest:
                                pfile.parse(
                                    inc=configuration.cliargs.inc,
                                    preprocessor=configuration.cliargs.doctests_preprocessor,
                                    preproc=configuration.cliargs.preproc,
                                    include=configuration.cliargs.include,
                                )
                            else:
                                pfile.parse(
                                    inc=configuration.cliargs.inc,
                                    preproc=configuration.cliargs.preproc,
                                    include=configuration.cliargs.include,
                                )
                            pfiles.append(pfile)
    return pfiles


def parse_doctests(configuration, pfiles, builder):
    """Parse parsed-files for

    Parameters
    ----------
    configuration : FoBiSConfig()
    pfiles : list
      list of ParsedFile() objects
    builder : Builder()

    Returns
    -------
    list
      list of doctests
    """
    doctests = []
    doctests_dirs = []
    for pfile in pfiles:
        if pfile.doctest:
            if pfile.doctest.to_test:
                doc_dir = pfile.doctest.save_volatile_programs(build_dir=builder.build_dir)
                doctests_dirs.append(doc_dir)
    if len(doctests_dirs) > 0:
        doctests_dirs = list(set(doctests_dirs))
    for doc_dir in doctests_dirs:
        doctests += parse_files(configuration=configuration, src_dir=doc_dir, is_doctest=True)
    return doctests, doctests_dirs


def build_pfile(configuration, pfile, pfiles, nomodlibs, submodules, builder):
    """Build a parsed file.

    Parameters
    ----------
    configuration : FoBiSConfig()
    pfile : ParsedFile()
    pfiles : list
      list of ParsedFile() objects
    nomodlibs : list
      list of built non module libraries object names
    submodules : list
      list of built submodules object names
    builder : Builder()
    """
    configuration.print_b(builder.verbose(quiet=configuration.cliargs.quiet))
    if pfile.program:
        remove_other_main(builder=builder, pfiles=pfiles, myself=pfile)
    builder.build(
        file_to_build=pfile,
        output=configuration.cliargs.output,
        nomodlibs=nomodlibs,
        submodules=submodules,
        mklib=configuration.cliargs.mklib,
        verbose=configuration.cliargs.verbose,
        log=configuration.cliargs.log,
        track=configuration.cliargs.track_build,
    )
    if configuration.cliargs.log:
        pfile.save_build_log(builder=builder)
    if configuration.cliargs.graph:
        pfile.save_dep_graph()


def build_nomodlibs(configuration, pfiles, builder):
    """Build all non module library files.

    Parameters
    ----------
    configuration : FoBiSConfig()
    pfiles : list
      list of ParsedFile() objects
    builder : Builder()

    Returns
    -------
    list
      list of built non module libraries object names
    """
    nomodlibs = []
    for pfile in pfiles:
        if pfile.nomodlib:
            build_ok = builder.build(
                file_to_build=pfile, verbose=configuration.cliargs.verbose, log=configuration.cliargs.log
            )
            if build_ok:
                nomodlibs = nomodlibs + pfile.obj_dependencies(exclude_programs=True)
    return nomodlibs


def build_submodules(configuration, pfiles, builder):
    """Build all submodule files.

    Parameters
    ----------
    configuration : FoBiSConfig()
    pfiles : list
      list of ParsedFile() objects
    builder : Builder()

    Returns
    -------
    list
      list of built submodules object names
    """
    submodules = []
    for pfile in pfiles:
        if pfile.submodule:
            build_ok = builder.build(
                file_to_build=pfile, verbose=configuration.cliargs.verbose, log=configuration.cliargs.log
            )
            if build_ok:
                submodules.append(pfile.basename + ".o")
                # Also include transitive module dependencies of this submodule.
                # Modules used exclusively by submodule files are not reachable from the
                # main program's module dependency graph and would otherwise be compiled
                # but never added to the link command.
                submodules += pfile.obj_dependencies(exclude_programs=True)
    return list(set(submodules))


def test_doctests(configuration, doctests, pfiles, nomodlibs, builder):
    """Test doctests: build/execute/check-result of each doctest.

    Parameters
    ----------
    configuration : FoBiSConfig()
    doctests : list
      list of ParsedFile() objects containing doctests
    pfiles : list
      list of ParsedFile() objects
    nomodlibs : list
      list of built non module libraries object names
    builder : Builder()
    """
    for test in doctests:
        if test.is_doctest and os.path.basename(test.name).split("-doctest")[0] not in [
            os.path.basename(os.path.splitext(exc)[0]) for exc in configuration.cliargs.exclude_from_doctests
        ]:
            remove_other_main(builder=builder, pfiles=pfiles, myself=test)
            builder.build(file_to_build=test, nomodlibs=nomodlibs, verbose=False, log=False, quiet=True)
            test_exe = os.path.join(builder.build_dir, os.path.splitext(os.path.basename(test.name))[0])
            configuration.print_b("executing doctest " + os.path.basename(test_exe))
            result = syswork(test_exe)
            if result[0] == 0:
                # comparing results
                test_result = os.path.join(
                    os.path.dirname(test.name), os.path.splitext(os.path.basename(test.name))[0] + ".result"
                )
                with open(test_result) as res:
                    expected_result = res.read()
                if result[1].strip() == expected_result:
                    configuration.print_b("doctest passed")
                else:
                    configuration.print_r("doctest failed!")
                    configuration.print_b('  result obtained: "' + result[1].strip() + '"')
                    configuration.print_b('  result expected: "' + expected_result + '"')
            if not configuration.cliargs.keep_volatile_doctests:
                os.remove(test_exe)


def save_makefile(configuration, pfiles, builder):
    """
    Save GNU makefile.

    Parameters
    ----------
    pfiles : list
      list of parsed files
    builder : Builder object
    """

    def _gnu_variables(builder):
        """
        Method for getting GNU Make variables

        Parameters
        ----------
        builder : Builder object

        Returns
        -------
        str
          string containing the GNU Make variables
        """
        string = []
        string.append("\n#main building variables\n")
        string.append("DSRC    = " + " ".join(configuration.cliargs.src) + "\n")
        string.append(builder.gnu_make())
        string.append("VPATH   = $(DSRC) $(DOBJ) $(DMOD)" + "\n")
        string.append("MKDIRS  = $(DOBJ) $(DMOD) $(DEXE)" + "\n")
        string.append("LCEXES  = $(shell echo $(EXES) | tr '[:upper:]' '[:lower:]')\n")
        string.append("EXESPO  = $(addsuffix .o,$(LCEXES))\n")
        string.append("EXESOBJ = $(addprefix $(DOBJ),$(EXESPO))\n")
        string.append("\n")
        string.append("#auxiliary variables\n")
        string.append('COTEXT  = "Compiling $(<F)"\n')
        string.append('LITEXT  = "Assembling $@"\n')
        return "".join(string)

    def _gnu_building_rules(pfiles):
        """
        Method returing the building rules.

        Parameters
        ----------
        pfifles : list
          list of parsed file

        Returns
        -------
        str
          string containing the building rules
        """
        # collect non-module-libraries object
        nomodlibs = []
        for pfile in pfiles:
            if pfile.nomodlib:
                nomodlibs.append("$(DOBJ)" + pfile.basename.lower() + ".o")
        string = []
        string.append("\n#building rules\n")
        # linking rules
        for pfile in pfiles:
            save_target_rule = False
            if pfile.program:
                save_target_rule = True
            elif configuration.cliargs.target:
                if os.path.basename(configuration.cliargs.target) == os.path.basename(pfile.name):
                    save_target_rule = True
            if save_target_rule:
                if len(nomodlibs) > 0:
                    string.append(
                        "$(DEXE)"
                        + pfile.basename.upper()
                        + ": $(MKDIRS) "
                        + "$(DOBJ)"
                        + pfile.basename.lower()
                        + ".o \\"
                        + "\n"
                    )
                    for nomod in nomodlibs[:-1]:
                        string.append("\t" + nomod + " \\" + "\n")
                    string.append("\t" + nomodlibs[-1] + "\n")
                else:
                    string.append(
                        "$(DEXE)"
                        + pfile.basename.upper()
                        + ": $(MKDIRS) "
                        + "$(DOBJ)"
                        + pfile.basename.lower()
                        + ".o\n"
                    )
                string.append("\t@rm -f $(filter-out $(DOBJ)" + pfile.basename.lower() + ".o,$(EXESOBJ))\n")
                string.append("\t@echo $(LITEXT)\n")
                string.append("\t@$(FC) $(OPTSL) $(DOBJ)*.o $(LIBS) -o $@\n")
                string.append("EXES := $(EXES) " + pfile.basename.upper() + "\n")
        return "".join(string)

    def _gnu_auxiliary_rules():
        """
        Method returing some useful GNU Make auxiliary rules

        Returns
        -------
        str
          string containing the auxiliary rules
        """
        string = []
        string.append("#phony auxiliary rules\n")
        string.append(".PHONY : $(MKDIRS)\n")
        string.append("$(MKDIRS):\n")
        string.append("\t@mkdir -p $@\n")
        string.append(".PHONY : cleanobj\n")
        string.append("cleanobj:\n")
        string.append("\t@echo deleting objects\n")
        string.append("\t@rm -fr $(DOBJ)\n")
        string.append(".PHONY : cleanmod\n")
        string.append("cleanmod:\n")
        string.append("\t@echo deleting mods\n")
        string.append("\t@rm -fr $(DMOD)\n")
        string.append(".PHONY : cleanexe\n")
        string.append("cleanexe:\n")
        string.append("\t@echo deleting exes\n")
        string.append("\t@rm -f $(addprefix $(DEXE),$(EXES))\n")
        string.append(".PHONY : clean\n")
        string.append("clean: cleanobj cleanmod\n")
        string.append(".PHONY : cleanall\n")
        string.append("cleanall: clean cleanexe\n")
        return "".join(string)

    string = []
    string.append("#!/usr/bin/make\n")
    string.append(_gnu_variables(builder=builder))
    string.append(_gnu_building_rules(pfiles=pfiles))
    string.append("\n#compiling rules\n")
    for pfile in pfiles:
        string.append(pfile.gnu_make_rule(builder=builder))
    string.append(_gnu_auxiliary_rules())
    with open(configuration.cliargs.makefile, "w") as mk_file:
        mk_file.writelines(string)


def gcov_analyzer(configuration):
    """
    Run gcov file analyzer.
    """
    gcovs = []
    for root, _, files in os.walk("."):
        for filename in files:
            if os.path.splitext(os.path.basename(filename))[1] == ".gcov":
                configuration.print_b("Analyzing " + os.path.join(root, filename))
                gcovs.append(Gcov(filename=os.path.join(root, filename)))
    for gcov in gcovs:
        gcov.parse()
        gcov.save(
            output=os.path.join(configuration.cliargs.gcov_analyzer[0], os.path.basename(gcov.filename) + ".md"),
            graphs=True,
        )
    if len(gcovs) > 0 and len(configuration.cliargs.gcov_analyzer) > 1:
        string = []
        string.append("### " + configuration.cliargs.gcov_analyzer[1] + "\n")
        for gcov in gcovs:
            string.append("\n#### [[" + os.path.basename(gcov.filename) + "]]\n\n")
            if gcov.l_pie_url or gcov.p_pie_url:
                string.append(gcov.l_pie_url + "\n" + gcov.p_pie_url + "\n")
            if gcov.metrics["coverage"]:
                string.append("|Lines| | |\n")
                string.append("| --- | --- | --- |\n")
                string.append("|Executable lines            |" + gcov.metrics["coverage"][0] + "| |\n")
                string.append(
                    "|Executed lines              |"
                    + gcov.metrics["coverage"][1]
                    + "|"
                    + gcov.metrics["coverage"][3]
                    + "%|\n"
                )
                string.append(
                    "|Unexecuted lines            |"
                    + gcov.metrics["coverage"][2]
                    + "|"
                    + gcov.metrics["coverage"][4]
                    + "%|\n"
                )
                string.append("|Average hits / executed     |" + gcov.metrics["coverage"][5] + "| |\n")
                string.append("\n")
                string.append(
                    _mermaid_pie(
                        "Lines (" + gcov.metrics["coverage"][3] + "% covered)",
                        gcov.metrics["coverage"][1],
                        gcov.metrics["coverage"][2],
                    )
                )
            if gcov.metrics["procedures"]:
                string.append("|Procedures| | |\n")
                string.append("| --- | --- | --- |\n")
                string.append("|Total procedures            |" + gcov.metrics["procedures"][0] + "| |\n")
                string.append(
                    "|Executed procedures         |"
                    + gcov.metrics["procedures"][1]
                    + "|"
                    + gcov.metrics["procedures"][3]
                    + "%|\n"
                )
                string.append(
                    "|Unexecuted procedures       |"
                    + gcov.metrics["procedures"][2]
                    + "|"
                    + gcov.metrics["procedures"][4]
                    + "%|\n"
                )
                string.append("|Average hits / executed     |" + gcov.metrics["procedures"][5] + "| |\n")
                string.append("\n")
                string.append(
                    _mermaid_pie(
                        "Procedures (" + gcov.metrics["procedures"][3] + "% covered)",
                        gcov.metrics["procedures"][1],
                        gcov.metrics["procedures"][2],
                    )
                )
        with open(
            os.path.join(configuration.cliargs.gcov_analyzer[0], configuration.cliargs.gcov_analyzer[1] + ".md"), "w"
        ) as summary:
            summary.writelines(string)


def is_ascii_kind_supported(configuration):
    """Check is the compiler support ASCII character kind.

    Parameters
    ----------
    configuration : FoBiSConfig()


    Returns
    -------
    bool
      true if ASCII kind is supported, false otherwise
    """
    builder = Builder(cliargs=configuration.cliargs, print_n=configuration.print_b, print_w=configuration.print_r)
    test_file_name = os.path.join(builder.build_dir, "ascii_kind_introspection.f90")
    with open(test_file_name, "w") as fh:
        fh.write("program test\nprint*, selected_char_kind('ascii')\nendprogram")
    test = ParsedFile(name=test_file_name)
    test.parse(inc=configuration.cliargs.inc)
    pfiles = [test]
    dependency_hiearchy(builder=builder, pfiles=pfiles, print_w=configuration.print_r)
    builder.build(file_to_build=pfiles[0], verbose=configuration.cliargs.verbose, log=configuration.cliargs.log)
    os.remove(test_file_name)
    test_exe = os.path.join(builder.build_dir, os.path.splitext(os.path.basename(test.name))[0])
    result = syswork(test_exe)
    os.remove(test_exe)
    is_supported = False
    if result[0] == 0:
        if int(result[1]) > 0:
            is_supported = True
    print("Compiler '" + builder.compiler.compiler + "' support ASCII kind:", is_supported)
    return is_supported


def is_ucs4_kind_supported(configuration):
    """Check is the compiler support UCS4 character kind.

    Parameters
    ----------
    configuration : FoBiSConfig()


    Returns
    -------
    bool
      true if UCS4 kind is supported, false otherwise
    """
    builder = Builder(cliargs=configuration.cliargs, print_n=configuration.print_b, print_w=configuration.print_r)
    test_file_name = os.path.join(builder.build_dir, "ucs4_kind_introspection.f90")
    with open(test_file_name, "w") as fh:
        fh.write("program test\nprint*, selected_char_kind('iso_10646')\nendprogram")
    test = ParsedFile(name=test_file_name)
    test.parse(inc=configuration.cliargs.inc)
    pfiles = [test]
    dependency_hiearchy(builder=builder, pfiles=pfiles, print_w=configuration.print_r)
    builder.build(file_to_build=pfiles[0], verbose=configuration.cliargs.verbose, log=configuration.cliargs.log)
    os.remove(test_file_name)
    test_exe = os.path.join(builder.build_dir, os.path.splitext(os.path.basename(test.name))[0])
    result = syswork(test_exe)
    os.remove(test_exe)
    is_supported = False
    if result[0] == 0:
        if int(result[1]) > 0:
            is_supported = True
    print("Compiler '" + builder.compiler.compiler + "' support UCS4 kind:", is_supported)
    return is_supported


def is_float128_kind_supported(configuration):
    """Check is the compiler support float128 real kind.

    Parameters
    ----------
    configuration : FoBiSConfig()


    Returns
    -------
    bool
      true if UCS4 kind is supported, false otherwise
    """
    builder = Builder(cliargs=configuration.cliargs, print_n=configuration.print_b, print_w=configuration.print_r)
    test_file_name = os.path.join(builder.build_dir, "float128_kind_introspection.f90")
    with open(test_file_name, "w") as fh:
        fh.write("program test\nprint*, selected_real_kind(33,4931)\nendprogram")
    test = ParsedFile(name=test_file_name)
    test.parse(inc=configuration.cliargs.inc)
    pfiles = [test]
    dependency_hiearchy(builder=builder, pfiles=pfiles, print_w=configuration.print_r)
    builder.build(file_to_build=pfiles[0], verbose=configuration.cliargs.verbose, log=configuration.cliargs.log)
    os.remove(test_file_name)
    test_exe = os.path.join(builder.build_dir, os.path.splitext(os.path.basename(test.name))[0])
    result = syswork(test_exe)
    os.remove(test_exe)
    is_supported = False
    if result[0] == 0:
        if int(result[1]) > 0:
            is_supported = True
    print("Compiler '" + builder.compiler.compiler + "' support float128 kind:", is_supported)
    return is_supported


def run_fobis_tree(configuration):
    """
    Run FoBiS in tree mode: print the inter-project dependency tree.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    from .Fobos import render_tree

    fobos = configuration.fobos
    cliargs = configuration.cliargs
    deps_dir = fobos.get_deps_dir()
    max_depth = getattr(cliargs, "tree_depth", None)
    dedupe = not getattr(cliargs, "tree_no_dedupe", False)

    # Root node
    proj_info = fobos.get_project_info()
    root_name = proj_info.get("name") or "unnamed project"
    root_version = fobos.get_version() or ""
    root_label = root_name
    if root_version:
        root_label += " " + root_version
    configuration.print_b(root_label)

    nodes = fobos.get_dep_tree(
        deps_dir=deps_dir,
        depth=0,
        max_depth=max_depth,
        visited=set(),
        dedupe=dedupe,
    )
    if nodes:
        configuration.print_b(render_tree(nodes))
    else:
        configuration.print_b("  (no dependencies declared)")


def run_fobis_run(configuration):
    """
    Run FoBiS in run mode: build a target and execute it.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    import subprocess

    cliargs = configuration.cliargs
    target_name = getattr(cliargs, "run_target", None)
    no_build = getattr(cliargs, "run_no_build", False)
    dry_run = getattr(cliargs, "run_dry_run", False)
    extra_args = getattr(cliargs, "run_extra_args", []) or []
    example_name = getattr(cliargs, "run_example", None)

    # Resolve output binary path
    fobos = configuration.fobos
    mode = getattr(cliargs, "mode", None)

    if example_name:
        targets = fobos.get_targets("example")
        matched = [t for t in targets if t["name"] == example_name]
        if not matched:
            configuration.print_r(f"Error: no [[example.{example_name}]] section found in fobos.")
            sys.exit(1)
        t_dict = matched[0]
        output_path = os.path.join(
            getattr(cliargs, "build_dir", "build"),
            "example",
            t_dict.get("output", example_name),
        )
        build_mode = mode or "default"
    elif target_name:
        # Try to find matching mode output
        output_path = target_name
        build_mode = mode
    else:
        output_path = fobos.get_output_name(mode=mode, toprint=False) or ""
        build_mode = mode

    # Build step
    if not no_build:
        build_args = ["build"]
        if build_mode:
            build_args += ["-mode", build_mode]
        if dry_run:
            configuration.print_b("[build]  fobis build " + " ".join(build_args[1:]))
        else:
            run_fobis(fake_args=build_args)

    # Resolve binary if needed
    if output_path and not os.path.isfile(output_path):
        # Try inside build_dir
        bd = getattr(cliargs, "build_dir", "build")
        candidate = os.path.join(bd, os.path.basename(output_path))
        if os.path.isfile(candidate):
            output_path = candidate

    if not dry_run and not os.path.isfile(output_path):
        configuration.print_r(
            f"Error: binary not found at '{output_path}'. "
            "Check the fobos 'output' or 'target' setting."
        )
        sys.exit(1)

    if dry_run:
        configuration.print_b("[run]    " + output_path + " " + " ".join(extra_args))
        return

    # Execute
    result = subprocess.run([output_path] + extra_args)
    sys.exit(result.returncode)


def run_fobis_check(configuration):
    """
    Run FoBiS in check mode: validate the dependency graph without building.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    pfiles = parse_files(configuration=configuration)
    # Create a dummy builder just to resolve includes
    builder = Builder(
        cliargs=configuration.cliargs,
        print_n=configuration.print_b,
        print_w=configuration.print_r,
    )
    dependency_hiearchy(
        builder=builder,
        pfiles=pfiles,
        print_w=configuration.print_r,
        force_compile=False,
    )
    # Check for unresolved dependencies
    errors = 0
    for pfile in pfiles:
        for dep in pfile.dependencies:
            if not dep.file:
                configuration.print_r(
                    f"  Unresolved: '{pfile.name}' depends on '{dep.name}' ({dep.type}) — not found"
                )
                errors += 1
    if errors:
        configuration.print_r(f"\nDependency check: {errors} unresolved dependency(-ies).")
        sys.exit(1)
    else:
        configuration.print_b(f"Dependency check: OK ({len(pfiles)} files scanned, 0 errors)")


def run_fobis_test(configuration):
    """
    Run FoBiS in test mode: discover, build, and run Fortran test programs.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    from .TestRunner import TestRunner, discover_tests

    cliargs = configuration.cliargs
    fobos = configuration.fobos

    # Read [test] fobos section for defaults
    test_config = fobos.get_test_config() if fobos.fobos else {}
    test_dir = test_config.get("test_dir", "test")
    default_timeout = float(test_config.get("timeout", 60))

    suite_filter = getattr(cliargs, "test_suite", None)
    filter_pattern = getattr(cliargs, "test_filter", None)
    timeout = getattr(cliargs, "test_timeout", default_timeout)
    no_build = getattr(cliargs, "test_no_build", False)
    list_only = getattr(cliargs, "test_list", False)
    extra_args = getattr(cliargs, "test_extra_args", []) or []
    do_coverage = getattr(cliargs, "test_coverage", False)

    if not os.path.isdir(test_dir):
        configuration.print_b(
            f"No '{test_dir}' directory found. Create it and add Fortran program files."
        )
        return

    tests = discover_tests(test_dir)
    if not tests:
        configuration.print_b(f"No test programs found in '{test_dir}'.")
        return

    if list_only:
        configuration.print_b(f"Discovered tests in '{test_dir}':")
        for t in tests:
            suite_tag = f"  [{t['suite']}]" if t.get("suite") else ""
            configuration.print_b(f"  {t['name']:<30} {t['source']}{suite_tag}")
        return

    build_dir = getattr(cliargs, "build_dir", "build")
    runner = TestRunner(
        build_dir=build_dir,
        print_n=configuration.print_b,
        print_w=configuration.print_r,
    )

    configuration.print_b(f"\nBuilding test suite ({len(tests)} target(s))...\n")

    def build_test(test):
        """Build a single test program and return the binary path."""
        src = test["source"]
        out_dir = os.path.join(build_dir, "test")
        os.makedirs(out_dir, exist_ok=True)
        binary = os.path.join(out_dir, test["name"])
        build_args = ["build", "-target", src, "-output", binary]
        mode_val = getattr(cliargs, "mode", None)
        if mode_val:
            build_args += ["-mode", mode_val]
        try:
            run_fobis(fake_args=build_args)
            return binary if os.path.isfile(binary) else None
        except SystemExit as e:
            if e.code != 0:
                return None
            return binary if os.path.isfile(binary) else None

    suite = runner.run_suite(
        tests=tests,
        build_fn=build_test,
        suite_filter=suite_filter,
        name_filter=filter_pattern,
        timeout=timeout,
        extra_args=extra_args,
        no_build=no_build,
    )
    configuration.print_b(runner.format_results(suite))

    # Optionally run coverage after tests
    if do_coverage:
        run_fobis_coverage(configuration)

    if suite.failed:
        sys.exit(1)


def run_fobis_introspect(configuration):
    """
    Run FoBiS in introspect mode: emit machine-readable project metadata.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    import json

    cliargs = configuration.cliargs
    fobos = configuration.fobos

    data = {}

    # Project info
    if getattr(cliargs, "introspect_projectinfo", False):
        proj = fobos.get_project_info()
        version = fobos.get_version()
        data["projectinfo"] = {
            "name": proj.get("name", ""),
            "version": version,
            "authors": proj.get("authors", []),
            "summary": proj.get("summary", ""),
            "repository": proj.get("repository", ""),
        }

    # Compiler info
    if getattr(cliargs, "introspect_compiler", False):
        data["compiler"] = {
            "name": getattr(cliargs, "compiler", "gnu"),
            "binary": getattr(cliargs, "fc", "") or "",
            "cflags": getattr(cliargs, "cflags", "") or "",
            "lflags": getattr(cliargs, "lflags", "") or "",
        }

    # Source files
    if getattr(cliargs, "introspect_sources", False):
        pfiles = parse_files(configuration=configuration)
        data["sources"] = [
            {
                "file": pf.name,
                "modules": list(pf.module_names) if pf.module_names else [],
                "uses": [d.name for d in pf.dependencies if d.type == "module"],
                "program": pf.program,
            }
            for pf in pfiles
        ]

    # Targets
    if getattr(cliargs, "introspect_targets", False):
        output = fobos.get_output_name(toprint=False) or ""
        mklib = getattr(cliargs, "mklib", "") or ""
        target_type = "library" if mklib else "executable"
        data["targets"] = [{"name": os.path.basename(output), "type": target_type, "output": output}]

    # Dependencies
    if getattr(cliargs, "introspect_dependencies", False):
        deps = fobos.get_dependencies()
        lock = {}
        try:
            from .Fetcher import Fetcher
            deps_dir = fobos.get_deps_dir()
            fetcher = Fetcher(deps_dir=deps_dir)
            lock = fetcher.load_lock()
        except Exception:
            pass
        data["dependencies"] = {}
        for name, spec in deps.items():
            from .Fetcher import Fetcher
            fetcher_tmp = Fetcher(deps_dir=fobos.get_deps_dir())
            parsed = fetcher_tmp.parse_dep_spec(spec)
            dep_dir = os.path.join(fobos.get_deps_dir(), name)
            dep_info = {
                "url": parsed.get("url", ""),
                "use": parsed.get("use", "sources"),
                "path": dep_dir,
                "locked": name in lock,
            }
            for pin in ("tag", "branch", "rev", "semver"):
                if pin in parsed:
                    dep_info[pin] = parsed[pin]
            if name in lock:
                dep_info["commit"] = lock[name].get("commit", "")
            data["dependencies"][name] = dep_info

    # Build options
    if getattr(cliargs, "introspect_buildoptions", False):
        data["buildoptions"] = {
            "mode": getattr(cliargs, "mode", "") or "",
            "build_dir": getattr(cliargs, "build_dir", "./"),
            "obj_dir": getattr(cliargs, "obj_dir", "./obj/"),
            "mod_dir": getattr(cliargs, "mod_dir", "./mod/"),
            "mklib": getattr(cliargs, "mklib", "") or "",
            "jobs": getattr(cliargs, "jobs", 1),
        }

    # Include dirs
    if getattr(cliargs, "introspect_include_dirs", False):
        data["include_dirs"] = getattr(cliargs, "include", []) or []

    # Write mode
    if getattr(cliargs, "introspect_write", False):
        info_dir = ".fobis-info"
        os.makedirs(info_dir, exist_ok=True)
        for key, value in data.items():
            fname = os.path.join(info_dir, f"intro-{key}.json")
            with open(fname, "w") as f:
                json.dump(value, f, indent=2)
            configuration.print_b(f"[introspect] wrote {fname}")
        return

    # Default: print to stdout
    output_format = getattr(cliargs, "introspect_format", "json")
    if output_format == "toml":
        try:
            import tomllib
            # Python 3.11+ has tomllib but no tomli writer; use basic serialisation
            pass
        except ImportError:
            pass
        # Fallback to JSON if toml writer unavailable
    print(json.dumps(data, indent=2))


def run_fobis_coverage(configuration):
    """
    Run FoBiS in coverage mode: generate coverage reports.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    from .Coverage import CoverageReporter

    cliargs = configuration.cliargs
    fobos = configuration.fobos

    # Read [coverage] fobos section for defaults
    fobos_config = fobos.get_coverage_config() if fobos.fobos else {}
    formats = getattr(cliargs, "coverage_formats", None) or fobos_config.get("format", ["html"])
    output_dir = getattr(cliargs, "coverage_output_dir", None) or fobos_config.get("output_dir", "coverage")
    source_dir = getattr(cliargs, "coverage_source_dir", None) or "."
    exclude = getattr(cliargs, "coverage_exclude", None) or fobos_config.get("exclude", [])
    fail_under = getattr(cliargs, "coverage_fail_under", None) or fobos_config.get("fail_under")
    tool = getattr(cliargs, "coverage_tool", None)
    build_dir = getattr(cliargs, "build_dir", "./")

    reporter = CoverageReporter(
        build_dir=build_dir,
        src_dir=source_dir,
        print_n=configuration.print_b,
        print_w=configuration.print_r,
    )

    exit_code = reporter.generate(
        formats=formats,
        output_dir=output_dir,
        exclude=exclude,
        fail_under=fail_under,
        tool=tool,
    )
    if exit_code != 0:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
