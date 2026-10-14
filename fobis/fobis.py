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
import contextlib
import os
import re
import shutil
import sys

from . import compile_commands
from .Builder import Builder
from .Cleaner import Cleaner
from .FoBiSConfig import FoBiSConfig
from .Gcov import Gcov, _mermaid_pie
from .ParsedFile import ParsedFile
from .utils import BuildFailed, dependency_hiearchy, is_c_header, remove_other_main, safe_mkdir, syswork


def main():
    """
    Main function.
    """
    # line by line on a pipe too (CI logs, | tee): block buffering put the compilers' messages, written to stderr,
    # before FoBiS's own lines that preceded them
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(line_buffering=True)
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
    # ``ecosystem`` streams the output of long multi-repo runs and asks for confirmations, ``mcp`` speaks
    # JSON-RPC on stdin/stdout, ``llm`` streams download progress: the CliRunner of FoBiSConfig would buffer
    # stdout and replace stdin, so run them directly.
    if sys.argv[1:2] in (["ecosystem"], ["mcp"], ["llm"]):
        from .cli import app as _app

        _app(prog_name=_prog_name())
        return
    run_fobis()
    sys.exit(0)


def _prog_name():
    """The command's name in usage lines: ``fobis`` under ``python -m fobis`` (argv[0] is then __main__.py)."""
    name = os.path.basename(sys.argv[0])
    return "fobis" if name in ("__main__.py", "-m", "") else name


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
            if _json:
                run_fobis_build_json(configuration)
            elif getattr(configuration.cliargs, "explain", False):
                try:
                    run_fobis_build(configuration)
                except BuildFailed as failure:
                    _explain_build_failure(configuration, failure)
                    raise
            else:
                run_fobis_build(configuration)
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
        if configuration.cliargs.which == "lint":
            run_fobis_lint(configuration)
        if configuration.cliargs.which == "review":
            run_fobis_review(configuration)
        if configuration.cliargs.which == "merge_assist":
            run_fobis_merge_assist(configuration)
        if configuration.cliargs.which == "testgen":
            run_fobis_testgen(configuration)
        if configuration.cliargs.which == "case":
            run_fobis_case(configuration)
        if configuration.cliargs.which == "provenance":
            run_fobis_provenance(configuration)
        if configuration.cliargs.which == "verify":
            run_fobis_verify(configuration)
        if configuration.cliargs.which == "matrix":
            run_fobis_matrix(configuration)
        if configuration.cliargs.which == "assess":
            run_fobis_assess(configuration)
        if configuration.cliargs.which == "diff_run":
            run_fobis_diff_run(configuration)
        if configuration.cliargs.which == "bench":
            run_fobis_bench(configuration)
        if configuration.cliargs.which == "gate":
            run_fobis_gate(configuration)
        if configuration.cliargs.which == "profile":
            run_fobis_profile(configuration)
        if configuration.cliargs.which == "fpm":
            run_fobis_fpm(configuration)
        if configuration.cliargs.which == "bindings":
            run_fobis_bindings(configuration)
        if configuration.cliargs.which == "modernize":
            run_fobis_modernize(configuration)
        if configuration.cliargs.which == "query":
            run_fobis_query(configuration)
        if configuration.cliargs.which == "agents_md":
            run_fobis_agents_md(configuration)
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
    # the fobos printers too: its rules (pre_build/post_build) report on them, and their lines are not errors
    configuration.fobos.print_n = collector.print_n
    configuration.fobos.print_w = collector.print_w

    obj_dir = os.path.normpath(os.path.join(configuration.cliargs.build_dir, configuration.cliargs.obj_dir))
    pre_objects = _obj_files(obj_dir)

    old_stderr = sys.stderr
    sys.stderr = io.StringIO()
    exit_code = 0
    failure = None
    try:
        run_fobis_build(configuration)
    except BuildFailed as exc:
        exit_code, failure = (exc.code if isinstance(exc.code, int) else 1), exc
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else 1
    finally:
        stderr_text = sys.stderr.getvalue()
        sys.stderr = old_stderr

    post_objects = _obj_files(obj_dir)
    objects_compiled = len(post_objects - pre_objects)

    errors = list(collector.warnings)
    reported = "\n".join(errors)
    # what reached stderr directly, unless it repeats a message already collected (the compiler's output)
    errors.extend(line for line in stderr_text.strip().splitlines() if line.strip() and line not in reported)

    result = {
        "status": "ok" if exit_code == 0 else "error",
        "target": configuration.cliargs.target or "all",
        "objects_compiled": objects_compiled,
        "errors": errors,
    }
    if failure is not None:  # the compiler's messages, parsed, and what FoBiS explains from facts
        diagnostics, diagnoses, _, _ = _build_failure_facts(configuration, failure)
        result["diagnostics"] = [d.to_dict() for d in diagnostics]
        result["diagnoses"] = [d.to_dict() for d in diagnoses]
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
    no_dev = getattr(configuration.cliargs, "no_dev", False)
    for name, spec in deps.items():
        parsed = fetcher.parse_dep_spec(spec)
        use_mode = parsed.get("use", "sources")
        dev = parsed.get("dev") == "true"
        if dev and no_dev:  # a test-only dependency, not wanted: its lock entry (if any) is kept as it was
            configuration.print_b(f"{name}: test-only dependency, skipped (--no-dev)")
            if name in lock:
                lock_entries.append({"name": name, **lock[name]})
            clone = os.path.join(deps_dir, name)
            if os.path.isdir(clone):  # fetched before: recorded as test-only, so no other build compiles it
                deps_info.append(
                    {"name": name, "path": clone, "mode": parsed.get("mode", ""), "use": use_mode, "dev": True}
                )
            continue

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

        # Verify against lockfile (non-frozen: warn only). Not with --update: moving past the lock is
        # its purpose, and the lock is rewritten below.
        if lock and not frozen and not configuration.cliargs.update:
            fetcher.verify_lock(name, dep_path, lock)

        if not configuration.cliargs.no_build and use_mode == "fobos":
            fetcher.build_dep(name, dep_path, mode=parsed.get("mode"))

        deps_info.append({"name": name, "path": dep_path, "mode": parsed.get("mode", ""), "use": use_mode, "dev": dev})

        # Build lock entry
        lock_entry: dict[str, str] = {
            "name": name,
            "url": parsed["url"],
            "commit": commit_sha,
            "sha256": fetcher._compute_sha256(dep_path),
        }
        for pin_key in ("branch", "tag", "rev", "semver", "dev"):
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

    from .Commit import CommitError, generate
    from .llm import LLMConfig, LLMError, get_provider
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

    if getattr(cliargs, "show_facts", False):
        from .ai.change import change_facts

        facts = change_facts()
        if getattr(cliargs, "json_output", False):
            import json

            print(json.dumps({"staged": bool(facts.files), **facts.to_dict()}, indent=2))
            sys.exit(0 if facts.files else 1)
        if not facts.files:
            configuration.print_r("Nothing staged. Run `git add <files>` first.")
            sys.exit(1)
        configuration.print_b(facts.render())
        return

    # CLI flags override config file values
    max_diff = getattr(cliargs, "max_diff", None) or ucfg.llm_max_diff_chars
    refine_passes_cli = getattr(cliargs, "refine_passes", None)
    refine_passes = refine_passes_cli if refine_passes_cli is not None else ucfg.llm_refine_passes

    provider = None
    try:
        llm_cfg = LLMConfig.from_user_config(
            ucfg,
            provider=getattr(cliargs, "provider", None),
            url=getattr(cliargs, "url", None),
            model=getattr(cliargs, "model", None),
            api_key_env=getattr(cliargs, "api_key_env", None),
        )
        provider = get_provider(llm_cfg, on_status=configuration.print_b)
        message = generate(
            provider=provider,
            max_diff_chars=max_diff,
            refine_passes=refine_passes,
            print_n=configuration.print_b,
            print_w=configuration.print_r,
            facts=not getattr(cliargs, "no_facts", False),
        )
    except (CommitError, LLMError) as exc:
        configuration.print_r(f"Error: {exc}")
        sys.exit(1)
    finally:
        if provider is not None and hasattr(provider, "close"):
            provider.close()  # the managed provider stops its llama-server

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
        skip=configuration.fobos.get_scaffold_config()["skip"],
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

        # The compiler record is per object directory: checked once, before any target is built
        compiler_record = _compiler_guard(
            configuration, Builder(cliargs=cliargs, print_n=lambda *a, **k: None, print_w=configuration.print_r)
        )
        # Scan source files once for all targets
        pfiles_all = parse_files(configuration=configuration)
        configuration.build_trace = {"pfiles": pfiles_all}
        database: list[dict] = []  # the compilation database of all the targets
        for t_dict in all_build_targets:
            t_cliargs = _cliargs_for_target(cliargs, t_dict)
            t_builder = Builder(cliargs=t_cliargs, print_n=configuration.print_b, print_w=configuration.print_r)
            configuration.print_b(t_builder.verbose(quiet=configuration.cliargs.quiet))
            dependency_hiearchy(
                builder=t_builder,
                pfiles=pfiles_all,
                print_w=configuration.print_r,
                force_compile=t_cliargs.force_compile,
            )
            compile_commands.update(t_cliargs, t_builder, pfiles_all, configuration.print_r, accumulated=database)
            nomodlibs = build_nomodlibs(configuration=configuration, pfiles=pfiles_all, builder=t_builder)
            submodules = build_submodules(configuration=configuration, pfiles=pfiles_all, builder=t_builder)
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
        compiler_record()
        return

    # Standard (single-target) build path
    builder = Builder(cliargs=cliargs, print_n=configuration.print_b, print_w=configuration.print_r)
    configuration.print_b(builder.verbose(quiet=cliargs.quiet))
    compiler_record = _compiler_guard(configuration, builder)
    pfiles = parse_files(configuration=configuration)
    configuration.build_trace = {"pfiles": pfiles}
    dependency_hiearchy(
        builder=builder, pfiles=pfiles, print_w=configuration.print_r, force_compile=cliargs.force_compile
    )
    # before compiling: an editor needs the database most when the build fails
    compile_commands.update(cliargs, builder, pfiles, configuration.print_r)
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

    if cliargs.target and not cliargs.build_all and not build_succeeded:  # before: nothing built, exit status 0
        configuration.print_r(
            f'Error: the target "{cliargs.target}" is not among the sources of this build '
            f"(src: {' '.join(cliargs.src)}): add its directory to the mode's src"
        )
        sys.exit(1)

    compiler_record()  # the build ended without a compile failure: its objects are the recorded compiler's

    # Execute post_build lifecycle hooks (only on success)
    if build_succeeded:
        post_rules = getattr(cliargs, "post_build", []) or []
        if isinstance(post_rules, str):
            post_rules = post_rules.split()
        for rule_name in post_rules:
            fobos.rule_execute(rule_name)


COMPILER_RECORD = ".fobis-compiler.json"


def _compiler_guard(configuration, builder):
    """Force a full rebuild when the compiler behind the mode's command changed since the last build in this object
    directory (another path, or another ``--version``: a module swap keeps the command name, and FoBiS's timestamps
    alone would link objects of two compilers, or reuse ``.mod`` files the new one cannot read).

    The record (``<obj_dir>/.fobis-compiler.json``) is written by the returned function, called once the build has
    compiled without failure; without a record (first build, or objects of an older FoBiS) nothing is forced.
    """
    import json
    import shlex

    from .verification.provenance import compiler_version

    words = shlex.split(builder.cmd_comp or "")
    command = words[:1] + [w for w in words[1:3] if w.startswith(("-fc=", "-f90=", "-compiler="))]
    current = {}
    if command:
        current = {
            "command": " ".join(command),
            "path": shutil.which(command[0]) or command[0],
            "version": compiler_version(command[0]) if len(command) == 1 else _wrapped_version(command),
        }
    path = os.path.join(builder.obj_dir, COMPILER_RECORD)
    recorded = {}
    with contextlib.suppress(OSError, ValueError), open(path, encoding="utf-8") as handle:
        recorded = json.load(handle)
    changed = [k for k in ("path", "version") if recorded and current and recorded.get(k) != current.get(k)]
    if changed and not configuration.cliargs.force_compile:
        configuration.cliargs.force_compile = True
        detail = "; ".join(f"{k} {recorded.get(k)!r} -> {current.get(k)!r}" for k in changed)
        configuration.print_r(f"The compiler changed since the last build ({detail}): rebuilding everything")

    def write():
        if current:
            with contextlib.suppress(OSError), open(path, "w", encoding="utf-8") as handle:
                json.dump(current, handle, indent=1)

    return write


def _wrapped_version(command: list[str]) -> str:
    """``--version`` of a wrapper that selects its compiler with an option (``mpiifort -fc=ifx``)."""
    from .verification.provenance import _first_line

    return _first_line([*command, "--version"])


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
                with contextlib.suppress(ValueError):
                    setattr(t_cliargs, key, int(value))
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
        compile_commands.remove(cleaner.build_dir, print_w=cleaner.print_w)
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
    failed = test_doctests(
        configuration=configuration, doctests=doctests, pfiles=pfiles, nomodlibs=nomodlibs, builder=builder
    )
    if not configuration.cliargs.keep_volatile_doctests:
        for doc_dir in doctests_dirs:
            if os.path.isdir(doc_dir):
                shutil.rmtree(doc_dir)
    if failed:
        configuration.print_r(f"{failed} doctest(s) failed")
        sys.exit(1)


def _merged_preproc_flags(cliargs) -> str:
    """
    Return the preprocessor flags to feed cpp at parse time.

    Combines ``cliargs.preproc`` (the dedicated preprocessor channel) with
    every ``-D...`` / ``-U...`` token found in ``cliargs.cflags``.  After
    the feature-flag refactor some defines are emitted to ``cflags`` rather
    than ``preproc`` (e.g. via ``[features] mpi = -D_MPI_``); without this
    merge, ``cpp`` runs without those defines and ``#ifdef`` ladders that
    gate ``use`` statements via macros expand to the wrong branch — leading
    to "module unreachable" warnings during dependency scanning.

    Tokens that are already present on either side are not de-duplicated;
    cpp tolerates redundant ``-D`` flags.
    """
    preproc = (getattr(cliargs, "preproc", "") or "").strip()
    cflags = getattr(cliargs, "cflags", "") or ""
    extra = [tok for tok in cflags.split() if tok.startswith(("-D", "-U"))]
    if extra:
        joined = " ".join(extra)
        preproc = (preproc + " " + joined).strip() if preproc else joined
    return preproc


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
    parse_preproc = _merged_preproc_flags(configuration.cliargs)
    parse_compiler = getattr(configuration.cliargs, "compiler", "") or ""
    parse_intrinsic_modules = list(getattr(configuration.cliargs, "intrinsic_modules", None) or [])
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
                                preproc=parse_preproc,
                                include=configuration.cliargs.include,
                                compiler=parse_compiler,
                                intrinsic_modules=parse_intrinsic_modules,
                            )
                        else:
                            pfile.parse(
                                inc=configuration.cliargs.inc,
                                preproc=parse_preproc,
                                include=configuration.cliargs.include,
                                compiler=parse_compiler,
                                intrinsic_modules=parse_intrinsic_modules,
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
                                    preproc=parse_preproc,
                                    include=configuration.cliargs.include,
                                    compiler=parse_compiler,
                                    intrinsic_modules=parse_intrinsic_modules,
                                )
                            else:
                                pfile.parse(
                                    inc=configuration.cliargs.inc,
                                    preproc=parse_preproc,
                                    include=configuration.cliargs.include,
                                    compiler=parse_compiler,
                                    intrinsic_modules=parse_intrinsic_modules,
                                )
                            pfiles.append(pfile)
    # by path, in natural order: not the directory listing's (it differs between file systems, so did the order of
    # compilation and of the doctests)
    pfiles = [pfile for pfile in pfiles if not is_c_header(pfile.name)]  # C headers next to the sources
    return sorted(pfiles, key=lambda pfile: _natural_key(pfile.name))


def _natural_key(text):
    """Sort key putting `x-2` before `x-10`."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", text)]


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
        doctests_dirs = sorted(set(doctests_dirs))
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
    if pfile.program:
        remove_other_main(builder=builder, pfiles=pfiles, myself=pfile)
    configuration.build_trace = {"pfiles": pfiles, "target": pfile}
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


def _build_failure_facts(configuration, failure):
    """The facts of a failed build: (diagnostics, deterministic diagnoses, errors left, `BuildFacts`).

    Shared by ``build --explain`` and ``build --json``. The project scan runs only when an error is recognised.

    Parameters
    ----------
    configuration : FoBiSConfig()
    failure : BuildFailed
        Carries the output of the failed commands.
    """
    from .ai.diagnostics import parse_diagnostics
    from .ai.explain import BuildFacts, classify
    from .analysis import parse_defines
    from .lint import discover_files

    cliargs = configuration.cliargs
    diagnostics = parse_diagnostics("\n".join(failure.outputs))
    if not any(d.is_error for d in diagnostics):
        return diagnostics, [], [], None
    trace = getattr(configuration, "build_trace", {})
    pfiles = trace.get("pfiles")
    target = trace.get("target")
    linked = None
    if target is not None:
        linked = {os.path.abspath(p.name) for p in (target.pfile_dep_all or [])}
        linked |= {os.path.abspath(target.name)} | {os.path.abspath(p.name) for p in pfiles if p.nomodlib}
    fobos = configuration.fobos
    sources = discover_files([*(cliargs.src or []), "."], extensions=cliargs.extensions)
    facts = BuildFacts.scan(
        sources,
        deps_dir=fobos.get_deps_dir(),
        defines=parse_defines(_merged_preproc_flags(cliargs)),
        compiler=cliargs.compiler,
        mode=getattr(cliargs, "mode", None),
        cflags=cliargs.cflags or "",
        built={os.path.abspath(p.name) for p in pfiles} if pfiles is not None else None,
        linked=linked,
        target=target.name if target is not None else None,
        dependencies=fobos.get_dependencies(),
        src=list(cliargs.src or []),
        exclude=list(cliargs.exclude or []),
        exclude_dirs=list(cliargs.exclude_dirs or []),
    )
    diagnoses, remaining = classify(diagnostics, facts)
    return diagnostics, diagnoses, remaining, facts


def _explain_build_failure(configuration, failure):
    """Explain a failed build (``fobis build --explain``): facts first, then the LLM for what they do not cover.

    Parameters
    ----------
    configuration : FoBiSConfig()
    failure : BuildFailed
        Carries the output of the failed commands.
    """
    from .ai.explain import build_bundle, explain, render_diagnoses

    say = configuration.print_b
    _, diagnoses, remaining, facts = _build_failure_facts(configuration, failure)
    if facts is None:
        configuration.print_r("explain: no compiler or linker error recognised in the output")
        return
    say("")
    say("Explanation (fobis build --explain)")
    if diagnoses:
        say(render_diagnoses(diagnoses))
    if not remaining:
        return
    first = remaining[0]
    bundle = build_bundle(first, facts, _knowledge_base())
    answered = _model_explanation(configuration, bundle, "explain", explain, f"{first.where}: {first.message}")
    if answered and len(remaining) > 1:
        say(f"  ({len(remaining) - 1} more error(s) not explained: fix this one first, then rebuild)")


def _knowledge_base():
    """The shipped and installed knowledge packs, or None when they cannot be loaded."""
    from .kb import KnowledgeBase, PackError

    try:
        return KnowledgeBase.load()
    except PackError:
        return None


def _model_explanation(configuration, bundle, prompt, ask, header, grouped=True, show_context=None) -> bool:
    """Print the model's cited explanation of *bundle* (or, with ``--explain-context``, the model's input).

    Parameters
    ----------
    configuration : FoBiSConfig()
    bundle : ContextBundle
    prompt : str
        Name of the system prompt template (``fobis/ai/prompts/<prompt>.md``).
    ask : callable
        ``ask(bundle, provider) -> Grounded``.
    header : str
        Line printed before the answer.
    grouped : bool
        Print the claims under their kind (Cause / Fix); False for plain cited answers.
    show_context : bool or None
        Print the model's input instead of asking (default: the ``--explain-context`` option).

    Returns
    -------
    bool
        A model answer was printed.
    """
    from .ai.explain import GROUPS
    from .ai.grounding import load_prompt, render_answer
    from .llm import LLMConfig, LLMError, get_provider
    from .UserConfig import UserConfig

    say = configuration.print_b
    if show_context is None:
        show_context = getattr(configuration.cliargs, "explain_context", False)
    if show_context:
        say(f"=== system prompt ===\n{load_prompt(prompt)}\n=== user message ===\n{bundle.render()}")
        return False
    say(header)
    client = None
    try:
        cfg = LLMConfig.from_user_config(UserConfig())
        client = get_provider(cfg, on_status=say)
        result = ask(bundle, client)
    except LLMError as exc:
        configuration.print_r(f"  no model explanation: {exc}")
        return False
    finally:
        if client is not None and hasattr(client, "close"):
            client.close()
    text = render_answer(result, groups=GROUPS if grouped else None)
    say("\n".join(f"  {line}" if line else "" for line in text.splitlines()))
    return True


def _explain_crash(configuration, output, exit_code, command, mode=None, ask_model=True, title=None) -> bool:
    """Explain a failed run (``fobis run/test --explain``): facts first, then the LLM when the location is trusted.

    Parameters
    ----------
    configuration : FoBiSConfig()
    output : str
        What the program wrote on standard error.
    exit_code : int
        Its exit status (negative: killed by a signal).
    command : str
        ``run`` or ``test`` (for the advice).
    mode : str or None
        The fobos mode of the build.
    ask_model : bool
        Whether the model may be asked (``test`` asks it for the first failure only).
    title : str or None
        Heading (default ``Explanation (fobis <command> --explain)``).

    Returns
    -------
    bool
        The model was asked (or its input printed).
    """
    from .ai.crash import build_bundle, classify_crash, explain_crash, parse_crash, render_notes, scan_context

    crash = parse_crash(output, exit_code)
    if crash is None:
        return False
    say = configuration.print_b
    ctx = scan_context(
        configuration.fobos, mode, command=command, shadow=getattr(configuration.cliargs, "shadow", None)
    )
    notes, wanted = classify_crash(crash, ctx)
    say("")
    say(title or f"Explanation (fobis {command} --explain)")
    say(render_notes(notes))
    if not (wanted and ask_model):
        return False
    header = f"{crash.file}:{crash.line}: {crash.message}"
    _model_explanation(configuration, build_bundle(crash, ctx, _knowledge_base()), "crash", explain_crash, header)
    return True


def _run_tee(args):
    """Run *args* with stdout inherited and stderr echoed while it is recorded; (exit status, stderr text)."""
    import subprocess

    proc = subprocess.Popen(args, stderr=subprocess.PIPE, text=True, errors="replace")
    recorded = []
    for line in proc.stderr:
        sys.stderr.write(line)
        sys.stderr.flush()
        recorded.append(line)
    proc.wait()
    return proc.returncode, "".join(recorded)


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

    Returns
    -------
    int
      number of failed doctests: the ones giving a wrong result and the ones exiting with an error
    """
    failed = 0
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
                    failed += 1
                    configuration.print_r("doctest failed!")
                    configuration.print_b('  result obtained: "' + result[1].strip() + '"')
                    configuration.print_b('  result expected: "' + expected_result + '"')
            else:
                failed += 1
                configuration.print_r("doctest failed!")
                configuration.print_b("  exit status: " + str(result[0]))
                configuration.print_b('  output: "' + result[1].strip() + '"')
            if not configuration.cliargs.keep_volatile_doctests:
                os.remove(test_exe)
    return failed


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
        # linking rules: the target only when the mode names one (it is make's default goal, and its output the
        # executable's name); else every program, named after its file
        target = configuration.cliargs.target
        matched = [p for p in pfiles if target and os.path.basename(target) == os.path.basename(p.name)]
        for pfile in pfiles:
            save_target_rule = pfile in matched if matched else pfile.program
            if matched:  # the name fobis build gives it
                name = configuration.cliargs.output or os.path.splitext(os.path.basename(pfile.name))[0]
            else:
                name = pfile.basename.upper()
            if save_target_rule:
                if len(nomodlibs) > 0:
                    string.append(
                        "$(DEXE)" + name + ": $(MKDIRS) " + "$(DOBJ)" + pfile.basename.lower() + ".o \\" + "\n"
                    )
                    for nomod in nomodlibs[:-1]:
                        string.append("\t" + nomod + " \\" + "\n")
                    string.append("\t" + nomodlibs[-1] + "\n")
                else:
                    string.append("$(DEXE)" + name + ": $(MKDIRS) " + "$(DOBJ)" + pfile.basename.lower() + ".o\n")
                string.append("\t@rm -f $(filter-out $(DOBJ)" + pfile.basename.lower() + ".o,$(EXESOBJ))\n")
                string.append("\t@echo $(LITEXT)\n")
                string.append("\t@$(FC) $(OPTSL) $(DOBJ)*.o $(LIBS) -o $@\n")
                string.append("EXES := $(EXES) " + name + "\n")
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
    string.append(_gnu_building_rules(pfiles=sorted(pfiles, key=lambda p: p.name)))
    string.append("\n#compiling rules\n")
    for pfile in sorted(pfiles, key=lambda p: p.name):  # by file name: not the directory listing's order
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
    nodes = fobos.get_dep_tree(
        deps_dir=deps_dir,
        depth=0,
        max_depth=max_depth,
        visited=set(),
        dedupe=dedupe,
    )
    if getattr(cliargs, "json_output", False):
        import json

        def node(n):
            return {
                "name": n.name,
                "spec": n.spec,
                "version": n.version,
                "fetched": n.fetched,
                "has_fobos": n.has_fobos,
                "duplicate": n.duplicate,
                "dev": n.dev,
                "dependencies": [node(c) for c in n.children],
            }

        tree = {
            "name": root_name,
            "version": root_version,
            "deps_dir": deps_dir,
            "dependencies": [node(n) for n in nodes],
        }
        print(json.dumps(tree, indent=2))
        return
    configuration.print_b(root_label)
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

    explain = getattr(cliargs, "explain", False)
    launcher, _ = _program_launcher(configuration, "run")  # checked before building
    shadow = getattr(cliargs, "shadow", None)
    if shadow and output_path and not target_name:  # the shadow's program is in the shadow's build directory
        mode_build_dir = fobos.get(option="build_dir", mode=mode, toprint=False) or "./"
        output_path = os.path.join(cliargs.build_dir, os.path.relpath(output_path, os.path.normpath(mode_build_dir)))

    # Build step
    if not no_build:
        build_args = ["build"]
        if build_mode:
            build_args += ["-mode", build_mode]
        if shadow:
            build_args += ["--shadow", shadow]
        if explain:
            build_args += ["--explain-context" if cliargs.explain_context else "--explain"]
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
            f"Error: binary not found at '{output_path}'. Check the fobos 'output' or 'target' setting."
        )
        sys.exit(1)

    if dry_run:
        configuration.print_b("[run]    " + " ".join([*launcher, output_path, *extra_args]))
        return

    # Execute: the build's messages first (stdout is block-buffered when it is a pipe, the program writes to the
    # same file directly)
    sys.stdout.flush()
    sys.stderr.flush()
    if not os.path.dirname(output_path):  # a program in the current directory: not searched on PATH
        output_path = os.path.join(".", output_path)
    if explain:
        returncode, errors = _run_tee([*launcher, output_path, *extra_args])
        if returncode != 0:
            _explain_crash(configuration, errors, returncode, "run", mode=build_mode)
        sys.exit(_exit_status(returncode))
    result = subprocess.run([*launcher, output_path, *extra_args])
    sys.exit(_exit_status(result.returncode))


def _exit_status(returncode: int) -> int:
    """The shell's exit status for a child's return code: a program killed by signal N (Python: -N) exits 128 + N,
    as a shell reports it (139 for SIGSEGV); without the mapping ``sys.exit(-11)`` gave 245."""
    return 128 - returncode if returncode < 0 else returncode


def run_fobis_check(configuration):
    """
    Run FoBiS in check mode: validate the dependency graph without building.

    Reports the ``use``/``include`` dependencies no project file provides and the circular dependencies (no compile
    order exists); exit 1 on either, and with ``--strict`` on any warning too. With ``--json`` one object goes to
    stdout: ``status``, ``files`` (number scanned), ``unresolved`` (file, dependency, type), ``cycles`` (file names
    along each cycle) and ``warnings`` (what the dependency analysis reported).

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    from .utils import CircularDependency

    as_json = getattr(configuration.cliargs, "json_output", False)
    strict = getattr(configuration.cliargs, "strict", False)
    warnings: list[str] = []
    print_r = configuration.print_r

    def collect(message, *args, **kwargs):
        warnings.append(str(message))
        if not as_json:
            print_r(message, *args, **kwargs)

    if as_json:
        configuration.print_b = lambda *a, **k: None
    configuration.print_r = collect
    pfiles = parse_files(configuration=configuration)
    # Create a dummy builder just to resolve includes
    builder = Builder(
        cliargs=configuration.cliargs,
        print_n=configuration.print_b,
        print_w=configuration.print_r,
    )
    cycles: list[list[str]] = []
    try:
        dependency_hiearchy(
            builder=builder,
            pfiles=pfiles,
            print_w=configuration.print_r,
            force_compile=False,
        )
    except CircularDependency as failure:
        cycles = failure.cycles
    configuration.print_r = print_r
    # unresolved dependencies and cycles are reported on their own: the analysis' messages about them are not warnings
    warnings = [w for w in warnings if w.strip() and "unreachable" not in w and "circular dependency" not in w]
    unresolved = [
        {"file": pfile.name, "dependency": dep.name, "type": dep.type}
        for pfile in pfiles
        for dep in pfile.dependencies
        if not dep.file and not getattr(dep, "external", False)  # a .mod found in an include directory resolves it
    ]
    failed = bool(unresolved or cycles or (strict and warnings))
    if as_json:
        import json

        result = {
            "status": "error" if failed else "ok",
            "files": len(pfiles),
            "unresolved": unresolved,
            "cycles": cycles,
            "warnings": warnings,
        }
        print(json.dumps(result, indent=2))
        if failed:
            sys.exit(1)
        return
    for item in unresolved:
        configuration.print_r(
            f"  Unresolved: '{item['file']}' depends on '{item['dependency']}' ({item['type']}) — not found"
        )
    if failed:
        problems = [f"{len(unresolved)} unresolved dependency(-ies)"] if unresolved else []
        problems += [f"{len(cycles)} circular dependency(-ies)"] if cycles else []
        problems += [f"{len(warnings)} warning(s) (--strict)"] if strict and warnings else []
        configuration.print_r(f"\nDependency check: {', '.join(problems)}.")
        sys.exit(1)
    configuration.print_b(f"Dependency check: OK ({len(pfiles)} files scanned, 0 errors)")


DEFAULT_LINT_BASELINE = ".fobis-lint-baseline.json"


def run_fobis_merge_assist(configuration):
    """
    Run FoBiS in merge-assist mode: propose resolutions for the conflicts of a merge, rebase or cherry-pick.

    Deterministic rules first, then the LLM per remaining hunk, each file verified by a syntax-only compile with
    the mode's compiler. With ``--apply`` the accepted resolutions are written to the working tree. The git state
    is never changed: no ``git add``, no ``--continue``.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    import shlex

    from .ai.change import _git
    from .ai.crash import mode_infos
    from .ai.grounding import load_prompt
    from .ai.merge import (
        apply_to_worktree,
        both_sides_touched,
        build_bundle,
        conflicted_files,
        load_conflict,
        operation,
        pre_pass,
        render_hunk,
        resolve_file,
    )

    cliargs = configuration.cliargs
    if getattr(cliargs, "merge_format", "text") not in ("text", "json"):
        configuration.print_r(f"Error: unknown format {cliargs.merge_format!r}: use text or json")
        sys.exit(2)
    as_json = getattr(cliargs, "merge_format", "text") == "json"
    say = (lambda m: print(m, file=sys.stderr)) if as_json else configuration.print_b  # stdout: the JSON only
    if as_json and cliargs.merge_apply and not cliargs.merge_yes:
        configuration.print_r("Error: --format json does not ask: use --apply --yes, or no --apply")
        sys.exit(2)
    root = _git("rev-parse", "--show-toplevel").strip()
    if not root:
        configuration.print_r("Error: not inside a git repository")
        sys.exit(1)
    paths = conflicted_files()
    if cliargs.merge_paths:
        wanted = {os.path.relpath(os.path.abspath(p), root) for p in cliargs.merge_paths}
        paths = [p for p in paths if p in wanted]
    if not paths:
        if as_json:
            import json

            print(json.dumps({"operation": None, "files": [], "both_sides_touched": []}, indent=2))
        else:
            say("No conflicted file.")
        return
    op = operation()
    say(f"{op.kind}: ours = {op.ours_name}; theirs = {op.theirs_name}")
    if op.kind == "rebase":
        say("(during a rebase, ours is the upstream and theirs is your commit being replayed)")
    files = [load_conflict(p) for p in paths]
    if cliargs.merge_context:
        say(f"=== system prompt ===\n{load_prompt('merge')}")
        for cf in files:
            for hunk in cf.hunks:
                draft = pre_pass(cf, hunk)
                if draft is None or draft.confidence != "high":
                    say(
                        f"=== {cf.path}: conflict {hunk.index + 1} ===\n{build_bundle(cf, hunk, op, draft=draft).render()}"
                    )
        return
    infos = mode_infos(configuration.fobos)
    wanted_mode = getattr(cliargs, "mode", None) or getattr(configuration.fobos, "mode", None)
    mode = next((m for m in infos if m.name == wanted_mode), infos[0] if infos else None)
    compiler = mode.compiler if mode else "gnu"
    cflags = mode.cflags if mode else ""
    defines = [t for t in shlex.split(cflags) if t.startswith(("-D", "-U", "-I"))]
    parser = configuration.fobos.fobos
    fc = None
    includes = []
    if parser is not None and mode is not None:
        fc = parser.get(mode.name, "fc") if parser.has_option(mode.name, "fc") else None
        build_dir = parser.get(mode.name, "build_dir") if parser.has_option(mode.name, "build_dir") else "./"
        mod_dir = parser.get(mode.name, "mod_dir") if parser.has_option(mode.name, "mod_dir") else "./mod/"
        candidate = os.path.normpath(os.path.join(build_dir, mod_dir))
        if os.path.isdir(candidate):
            includes.append(os.path.abspath(candidate))
    provider = None
    if not cliargs.merge_no_model:
        from .llm import LLMConfig, LLMError, get_provider
        from .UserConfig import UserConfig

        try:
            provider = get_provider(LLMConfig.from_user_config(UserConfig()), on_status=say)
        except LLMError as exc:
            configuration.print_r(f"Warning: no model ({exc}): deterministic resolutions only")
    checks = {}
    try:
        for cf in files:
            file_includes = [os.path.join(root, os.path.dirname(cf.path)), *includes]
            check = resolve_file(
                cf, op, provider, compiler=compiler, fc=fc, includes=file_includes, defines=defines, on_status=say
            )
            checks[cf.path] = check
            if as_json:
                continue
            say("")
            for hunk in cf.hunks:
                say(render_hunk(cf, hunk, op))
            if check.elsewhere:
                say(
                    f"  {cf.path}: compile errors outside the conflicts: "
                    + "; ".join(d.message for d in check.elsewhere[:3])
                )
    finally:
        if provider is not None and hasattr(provider, "close"):
            provider.close()
    if cliargs.merge_apply:
        if not cliargs.merge_yes and not sys.stdin.isatty():
            configuration.print_r("Error: --apply asks hunk by hunk: run it in a terminal, or add --yes")
            sys.exit(1)
        for cf in files:
            accepted, quit_ = _choose_hunks(cf, cliargs.merge_yes)
            if accepted:
                target = os.path.join(root, cf.path)
                with open(target, encoding="utf-8", errors="replace") as handle:
                    current = handle.read()
                text, applied = apply_to_worktree(current, cf, accepted)
                if applied:
                    with open(target, "w", encoding="utf-8") as handle:
                        handle.write(text)
                missing = len(accepted) - len(applied)
                say(
                    f"{cf.path}: {len(applied)} conflict(s) resolved"
                    + (f"; {missing} no longer in the file (already edited), left as they are" if missing else "")
                )
            if quit_:
                break
    touched = both_sides_touched(files)
    if as_json:
        import json

        data = {
            "operation": {
                "kind": op.kind,
                "ours": op.ours,
                "theirs": op.theirs,
                "ours_name": op.ours_name,
                "theirs_name": op.theirs_name,
            },
            "files": [
                {
                    "path": cf.path,
                    "hunks": [h.to_dict() for h in cf.hunks],
                    "compiles": checks[cf.path].ok,
                    "not_checked_because": checks[cf.path].reason if checks[cf.path].ok is None else "",
                    "errors_elsewhere": [d.to_dict() for d in checks[cf.path].elsewhere],
                }
                for cf in files
            ],
            "both_sides_touched": touched,
            "applied": bool(cliargs.merge_apply),
        }
        print(json.dumps(data, indent=2))
        return
    say("")
    if touched:
        say("Changed by both sides (test them after the merge): " + ", ".join(touched))
    say("Nothing was staged. Review with `git diff`, run `fobis test`, then `git add` the files yourself.")


def _choose_hunks(cf, accept_all):
    """The hunks of *cf* the user accepts (asking, or by rule with *accept_all*), and whether the user quit."""
    import subprocess
    import tempfile

    from .ai.merge import Resolution

    accepted = set()
    for hunk in cf.hunks:
        res = hunk.resolution
        if accept_all:
            safe = res is not None and (
                (res.source == "pre-pass" and res.confidence == "high") or (res.source == "model" and res.verified)
            )
            if safe:
                accepted.add(hunk.index)
            continue
        options = (
            "[a]ccept [o]urs [t]heirs [b]oth [e]dit [s]kip [q]uit"
            if res
            else "[o]urs [t]heirs [b]oth [e]dit [s]kip [q]uit"
        )
        while True:
            answer = input(f"{cf.path} conflict {hunk.index + 1}/{len(cf.hunks)}: {options}? ").strip().lower()[:1]
            if answer == "a" and res is not None:
                accepted.add(hunk.index)
            elif answer in ("o", "t", "b"):
                strategy = {"o": "ours", "t": "theirs", "b": "both"}[answer]
                hunk.resolution = Resolution("user", strategy, list(hunk.side(strategy)))
                accepted.add(hunk.index)
            elif answer == "e":
                start = res.lines if res is not None else hunk.ours
                with tempfile.NamedTemporaryFile("w", suffix=os.path.splitext(cf.path)[1], delete=False) as tmp:
                    tmp.write("".join(line + "\n" for line in start))
                subprocess.run([os.environ.get("EDITOR", "vi"), tmp.name])
                with open(tmp.name, encoding="utf-8") as handle:
                    lines = handle.read().splitlines()
                os.unlink(tmp.name)
                hunk.resolution = Resolution("user", "custom", lines)
                accepted.add(hunk.index)
            elif answer == "q":
                return accepted, True
            elif answer != "s":
                continue
            break
    return accepted, False


def subprocess_ok(args: list[str]) -> bool:
    """*args* ran and exited with status 0."""
    import subprocess

    try:
        return subprocess.run(args, capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _scheduler_config(configuration):
    """The ``[scheduler]`` settings (user config, then fobos), loaded once; a declaration error exits 2."""
    from .verification.scheduler import SchedulerError, load_config

    if getattr(configuration, "_scheduler", None) is None:
        try:
            configuration._scheduler = load_config(configuration.fobos)
        except SchedulerError as exc:
            configuration.print_r(f"Error: {exc}")
            sys.exit(2)
    return configuration._scheduler


def _scratch_parent(cliargs):
    """Where scratch copies go: the system's temporary directory, but inside the project (``.fobis/scratch``) for
    a scheduler, whose compute nodes do not see the login node's ``/tmp``."""
    if getattr(cliargs, "runner", "local") != "slurm":
        return None
    os.makedirs(os.path.join(".fobis", "scratch"), exist_ok=True)
    return os.path.abspath(os.path.join(".fobis", "scratch"))


def _program_launcher(configuration, command: str) -> tuple[list[str], int]:
    """The words starting the programs of ``fobis run``/``fobis test`` and the MPI ranks.

    The launcher is ``--launcher``, else the mode's ``launcher`` key, else (test) the ``[test]`` section's, else
    ``mpirun -np {ranks}`` when ``--ranks`` is given; ``{ranks}`` is replaced by ``--ranks`` (1 by default). Under
    ``--runner slurm`` a test without a launcher but with ranks uses the scheduler's (``srun``). Locally, a launcher
    that is not on PATH, or ranks on a declared login node, stop before anything is built (exit 2).
    """
    from .verification.case import DEFAULT_LAUNCHER, launcher_words
    from .verification.scheduler import guard_message, on_login_node

    cliargs = configuration.cliargs
    fobos = configuration.fobos
    ranks = getattr(cliargs, f"{command}_ranks", None) or 0
    launcher = getattr(cliargs, f"{command}_launcher", None) or ""
    if not launcher and fobos.fobos:
        launcher = fobos.get(option="launcher", mode=getattr(cliargs, "mode", None), toprint=False)
    if not (launcher and isinstance(launcher, str)) and command == "test" and fobos.fobos:
        launcher = fobos.get_test_config().get("launcher", "")
    launcher = launcher if isinstance(launcher, str) else ""
    slurm = getattr(cliargs, "runner", "local") == "slurm"
    if not launcher and ranks:
        launcher = _scheduler_config(configuration).launcher if slurm else DEFAULT_LAUNCHER
    words = launcher_words(launcher, ranks)
    if not slurm:
        if words and shutil.which(words[0]) is None:
            configuration.print_r(f"Error: the launcher {words[0]!r} ({launcher}) is not on PATH")
            sys.exit(2)
        host = on_login_node(_scheduler_config(configuration)) if ranks else ""
        if host:
            configuration.print_r("Error: " + guard_message(host).replace("an MPI or GPU case", "an MPI program"))
            sys.exit(2)
    return words, ranks


def _test_scheduler(configuration):
    """The `SlurmScheduler` running the test programs with ``fobis test --runner slurm``, else None."""
    from .verification.scheduler import SlurmScheduler

    if getattr(configuration.cliargs, "runner", "local") != "slurm":
        return None
    config = _scheduler_config(configuration)
    return SlurmScheduler(config, progress=lambda m: print(f"slurm: {m}", file=sys.stderr, flush=True))


def _make_runner(configuration, *args, **kwargs):
    """The runner of the cases: a `SlurmRunner` with ``--runner slurm``, else a `LocalRunner` that refuses MPI and
    GPU cases on a declared login node."""
    from .verification import LocalRunner
    from .verification.scheduler import SlurmRunner, SlurmScheduler, guard_message, on_login_node

    config = _scheduler_config(configuration)
    kind = getattr(configuration.cliargs, "runner", "local") or "local"
    if kind not in ("local", "slurm"):
        configuration.print_r(f"Error: unknown runner {kind!r} (local or slurm)")
        sys.exit(2)
    if kind == "slurm":

        def progress(message):
            print(f"slurm: {message}", file=sys.stderr, flush=True)

        return SlurmRunner(*args, scheduler=SlurmScheduler(config, progress=progress), **kwargs)
    runner = LocalRunner(*args, **kwargs)
    host = on_login_node(config)
    if host:
        runner.refuse = guard_message(host)
    return runner


def _verification_runner(configuration, shadow=None):
    """The `LocalRunner` of the project in the cwd, with the fobos's ``[verification]`` settings."""
    from .verification import load_settings

    cliargs = configuration.cliargs
    fobos_args = ["--fobos", cliargs.fobos] if cliargs.fobos else []
    if cliargs.fobos_case_insensitive:
        fobos_args.append("--fobos-case-insensitive")
    settings = load_settings(configuration.fobos)
    deps_dir = configuration.fobos.get_deps_dir() if configuration.fobos.fobos else ".fobis_deps"
    return _make_runner(configuration, ".", fobos_args, settings.runs_dir, settings.launcher, deps_dir, shadow=shadow)


def _format_values(values: list, limit: int = 6) -> str:
    shown = ", ".join(f"{v:.17g}" if isinstance(v, float) else str(v) for v in values[:limit])
    return shown + (f", ... ({len(values)} values)" if len(values) > limit else "")


def run_fobis_case(configuration):
    """
    Run FoBiS in case mode: list the declared cases, or build and run them and report their quantities.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    import json

    from .verification import CaseError, load_cases

    cliargs = configuration.cliargs
    as_json = getattr(cliargs, "json_output", False)
    try:
        cases = load_cases(configuration.fobos)
    except CaseError as exc:
        configuration.print_r(f"Error: {exc}")
        sys.exit(2)
    if cliargs.case_action == "list":
        if as_json:
            print(json.dumps({"cases": [c.to_dict() for c in cases.values()]}, indent=2))
        elif not cases:
            configuration.print_b("No case declared: add [case:NAME] sections to the fobos (see fobis case --help).")
        else:
            for case in cases.values():
                what = case.target or " ".join(case.command)
                quantities = ", ".join(p.name for p in case.probes) or "none"
                configuration.print_b(f"{case.name:<20} {what}  [quantities: {quantities}]")
        return
    wanted = cliargs.case_names or list(cases)
    unknown = [n for n in wanted if n not in cases]
    if unknown:
        configuration.print_r(f"Error: unknown case(s) {', '.join(unknown)} (declared: {', '.join(cases) or 'none'})")
        sys.exit(2)
    runner = _verification_runner(configuration, getattr(cliargs, "case_shadow", None))
    if not as_json and os.path.isdir(".git"):
        ignored = subprocess_ok(["git", "check-ignore", "-q", os.path.join(runner.runs_dir, "x")])
        if not ignored:
            configuration.print_r(
                f"Note: add {os.path.relpath(runner.runs_dir)}/ to .gitignore (run directories and built programs)"
            )
    results = []
    for name in wanted:
        if not as_json:
            configuration.print_b(f"Running case {name}...")
        result = runner.run(cases[name], mode=cliargs.case_mode)
        results.append(result)
        if as_json:
            continue
        say = configuration.print_b if result.ok else configuration.print_r
        if result.exit_code is None and not result.rundir:  # never started: refused, or the build failed
            say(f"  {result.status}")
        else:
            say(
                f"  {result.status} (exit {result.exit_code}, {result.elapsed:.2f} s) "
                f"in {os.path.relpath(result.rundir or '.')}"
            )
        for quantity in result.quantities:
            shape = f" shape {quantity.shape}" if quantity.shape else ""
            configuration.print_b(f"    {quantity.name} = {_format_values(quantity.values)}{shape}")
        for name_, error in result.probe_errors.items():
            configuration.print_r(f"    {name_}: {error}")
        if result.build is not None:
            for diagnosis in result.build.get("diagnoses", []):
                configuration.print_r(f"    build: {diagnosis.get('summary')}")
            if not result.build.get("diagnoses"):
                configuration.print_r("    build: " + "; ".join(result.build.get("errors", [])[:3]))
        if result.status in ("failed", "timeout", "error") and result.stderr.strip():
            configuration.print_r("    " + "\n    ".join(result.stderr.strip().splitlines()[-10:]))
    if as_json:
        print(json.dumps({"results": [r.to_dict() for r in results]}, indent=2))
    if any(not r.ok for r in results):
        sys.exit(1)


def run_fobis_verify(configuration):
    """
    Run FoBiS in verify mode: run cases and compare their quantities with the stored references.

    With ``--update`` the runs become the references (never implicitly); with ``--repeat N`` each case runs N times
    and the runs are compared with each other (non-determinism).

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    import json

    from .verification import CaseError, load_cases, load_settings
    from .verification.verify import (
        Verification,
        VerifyError,
        load_reference,
        reference_path,
        render_text,
        save_reference,
        verify,
    )

    cliargs = configuration.cliargs
    as_json = getattr(cliargs, "json_output", False)
    try:
        cases = load_cases(configuration.fobos)
    except CaseError as exc:
        configuration.print_r(f"Error: {exc}")
        sys.exit(2)
    wanted = cliargs.verify_names or list(cases)
    unknown = [n for n in wanted if n not in cases]
    if unknown or not wanted:
        what = f"unknown case(s) {', '.join(unknown)}" if unknown else "no case declared"
        configuration.print_r(f"Error: {what} (declared: {', '.join(cases) or 'none'})")
        sys.exit(2)
    settings = load_settings(configuration.fobos)
    runner = _verification_runner(configuration, getattr(cliargs, "verify_shadow", None))
    outcomes: list[Verification] = []
    for name in wanted:
        case = cases[name]
        configuration.print_b(f"Verifying case {name}...")
        results = [runner.run(case, mode=cliargs.verify_mode)]
        for number in range(2, cliargs.verify_repeat + 1):
            results.append(runner.run(case, variant=f"repeat-{number}", mode=cliargs.verify_mode))
        path = reference_path(settings.references_dir, name)
        try:
            reference = None if cliargs.verify_update else load_reference(path)
        except VerifyError as exc:
            configuration.print_r(f"Error: {exc}")
            sys.exit(2)
        outcome = verify(results, reference, case.tolerance, path)
        if cliargs.verify_update and outcome.status == "no-reference":
            run = results[0]
            if outcome.repeat:
                outcome.status = "nondeterministic"
                outcome.note = "not updated: the repeated runs differ"
            elif run.probe_errors:
                outcome.status = "fail"
                outcome.note = "not updated: quantities not read: " + ", ".join(run.probe_errors)
            else:
                save_reference(path, run)
                outcome.status, outcome.note = "updated", f"reference written to {path}"
                if run.provenance.get("git", {}).get("dirty"):
                    outcome.note += " (from uncommitted code)"
        outcomes.append(outcome)
    if as_json:
        print(json.dumps({"cases": [o.to_dict() for o in outcomes]}, indent=2))
    else:
        text = render_text(outcomes)
        (configuration.print_b if all(o.ok for o in outcomes) else configuration.print_r)(text)
    if not all(o.ok for o in outcomes):
        sys.exit(1)


def run_fobis_matrix(configuration):
    """
    Run FoBiS in matrix mode: build, test and (with ``--verify``) verify every mode x shadow combination.

    Each cell is a nested ``fobis`` command in the environment of the mode's ``[verification] setup`` line, with
    the mode rebuilt in its own shadow build directory: the user's build tree is never touched.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    import json
    import subprocess

    from .mcp_server import fobis_command
    from .TestRunner import discover_tests
    from .verification import CaseError, load_cases, load_settings
    from .verification.matrix import Matrix, render_text
    from .verification.shadow import SHADOWS

    cliargs = configuration.cliargs
    fobos = configuration.fobos
    if not fobos.fobos:
        configuration.print_r("Error: fobis matrix needs a fobos file (its modes are the rows of the matrix)")
        sys.exit(2)
    declared = fobos.fobos.get("modes", "modes").split() if fobos.fobos.has_option("modes", "modes") else []
    if not declared and fobos.fobos.has_section("default"):
        declared = ["default"]
    modes = cliargs.matrix_modes or declared
    shadows = cliargs.matrix_shadows or ["none"]
    problems = [f"unknown mode {m!r}" for m in modes if m not in declared]
    problems += [f"unknown shadow {s!r} (available: {', '.join(SHADOWS)})" for s in shadows if s not in SHADOWS]
    try:
        cases = load_cases(fobos) if cliargs.matrix_verify else {}
        settings = load_settings(fobos)
    except CaseError as exc:
        problems.append(str(exc))
    if cliargs.matrix_verify and not problems and not cases:
        problems.append("--verify: no case declared ([case:NAME] sections)")
    if problems:
        configuration.print_r("Error: " + "; ".join(problems))
        sys.exit(2)
    test_dir = (fobos.get_test_config() or {}).get("test_dir", "test")
    has_tests = not cliargs.matrix_no_tests and os.path.isdir(test_dir) and bool(discover_tests(test_dir))
    fobos_args = ["--fobos", cliargs.fobos] if cliargs.fobos else []
    if cliargs.fobos_case_insensitive:
        fobos_args.append("--fobos-case-insensitive")

    def run(args, env):
        done = subprocess.run([*fobis_command(), *args, *fobos_args], capture_output=True, text=True, env=env)
        return done.returncode, done.stdout, done.stderr

    def progress(line):
        print(f"matrix: {line}", file=sys.stderr, flush=True)

    matrix = Matrix(
        modes,
        shadows,
        run,
        setup=settings.setup,
        cases=cases,
        references_dir=settings.references_dir,
        has_tests=has_tests,
        compilers=cliargs.matrix_compilers,
        verify=cliargs.matrix_verify,
        recheck=cliargs.matrix_recheck,
        progress=progress,
    )
    result = matrix.run()
    if getattr(cliargs, "json_output", False):
        print(json.dumps(result.to_dict(), indent=2))
    else:
        (configuration.print_b if result.ok else configuration.print_r)(render_text(result, shadows))
    if not result.ok:
        sys.exit(1)


def run_fobis_query(configuration):
    """
    Run FoBiS in query mode: one deterministic question about the code of the mode's sources.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    import json

    from .analysis import parse_defines
    from .analysis.query import CodeGraph, QueryError, query, render_text
    from .lint import discover_files, lint_files

    cliargs = configuration.cliargs
    files = discover_files(
        cliargs.src,
        extensions=cliargs.extensions,
        exclude=cliargs.exclude,
        exclude_dirs=cliargs.exclude_dirs,
        recursive=not cliargs.disable_recursive_search,
    )
    analysed = lint_files(
        files,
        [],
        defines=parse_defines(_merged_preproc_flags(cliargs)),
        openmp=bool(getattr(cliargs, "openmp", False)),
    )
    graph = CodeGraph(analysed.units, analysed.project)
    try:
        result = query(graph, cliargs.query_kind, cliargs.query_argument)
    except QueryError as exc:
        configuration.print_r(f"Error: {exc}")
        sys.exit(2)
    if getattr(cliargs, "json_output", False):
        data = result.to_dict()
        data["files"] = len(analysed.units)
        print(json.dumps(data, indent=2))
    else:
        configuration.print_b(render_text(result) + f"\n({len(analysed.units)} file(s) analysed)")


def run_fobis_agents_md(configuration):
    """
    Run FoBiS in agents-md mode: write (or check, or print) the generated block of AGENTS.md.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    import json

    from .ai.agents_md import AgentsMdError, collect, project_files, render, status, write
    from .lint import discover_files
    from .verification import CaseError

    cliargs = configuration.cliargs
    fobos = configuration.fobos
    deps_dir = fobos.get_deps_dir() if fobos is not None and fobos.fobos is not None else ""
    files = discover_files(
        cliargs.src,
        extensions=cliargs.extensions,
        exclude=cliargs.exclude,
        exclude_dirs=cliargs.exclude_dirs,
        recursive=not cliargs.disable_recursive_search,
    )
    try:
        facts = collect(configuration, project_files(files, ".", deps_dir))
    except CaseError as exc:
        configuration.print_r(f"Error: {exc}")
        sys.exit(2)
    block = render(facts)
    as_json = getattr(cliargs, "json_output", False)
    if cliargs.agents_print:
        if as_json:
            print(json.dumps({"facts": facts.to_dict(), "block": block}, indent=2))
        else:
            print(block, end="")
        return
    reports, failed = [], False
    try:
        for path in cliargs.agents_outputs:
            if cliargs.agents_check:
                state, diff = status(path, block)
                failed |= state != "current"
                reports.append({"path": path, "status": state, "diff": diff})
            else:
                reports.append({"path": path, "status": write(path, block, facts.name or "Agent instructions")})
    except (AgentsMdError, OSError) as exc:
        configuration.print_r(f"Error: {exc}")
        sys.exit(2)
    if as_json:
        print(json.dumps({"files": reports, "facts": facts.to_dict(), "block": block}, indent=2))
    else:
        for report in reports:
            if report.get("diff"):
                configuration.print_r(report["diff"].rstrip("\n"))
            hint = (
                ""
                if report["status"] in ("current", "created", "updated", "appended", "unchanged")
                else (
                    ": run fobis agents-md" + ("" if report["path"] == "AGENTS.md" else f" --output {report['path']}")
                )
            )
            printer = configuration.print_r if hint else configuration.print_b
            printer(f"{report['path']}: {report['status']}{hint}")
    if failed:
        sys.exit(1)


def _mode_environments(settings, fobos_args, deps_dir, root="."):
    """mode -> the environment of its ``[verification] setup`` line (by mode, compiler or family; None without
    one), memoised; a failing setup raises RuntimeError."""
    from .verification import LocalRunner
    from .verification.matrix import setup_environment
    from .verification.shadow import family

    environments: dict = {}

    def environment(mode):
        if mode not in environments:
            plain = LocalRunner(root, fobos_args, settings.runs_dir, settings.launcher, deps_dir)
            compiler = plain.introspect(mode).get("compiler", {}).get("name", "") if mode else ""
            command = next(
                (settings.setup[k] for k in (mode, compiler, family(compiler) or "") if k and k in settings.setup), ""
            )
            environments[mode] = setup_environment(command) if command else None
        return environments[mode]

    return environment


def _side_sources(root, defines):
    """The analysed Fortran sources under a scratch side (FoBiS's own directories skipped): units and index."""
    from .cli._constants import __extensions_parsed__
    from .lint import discover_files, lint_files

    files = discover_files([root], extensions=__extensions_parsed__, exclude_dirs=[os.path.join(root, ".fobis")])
    analysed = lint_files(files, [], defines=defines)
    return analysed.units, analysed.project  # display paths (relative to the cwd): events() makes them root-relative


def _bench_feedback(case, mode, roots, runner_for, defines, say):
    """Compiler-feedback changes between the revision and the working tree (list of `Change`), or a note."""
    from .verification import feedback_diff
    from .verification.runner import BuildVariant

    compiler = runner_for(roots["new"]).introspect(mode).get("compiler", {}).get("name", "")
    flags = feedback_diff.REPORT_FLAGS.get(compiler)
    if not flags:
        return [], f"no compiler-report flags known for {compiler or 'this compiler'}: feedback not compared"
    found, names = {}, {}
    for side, root in roots.items():
        say(f"case {case.name}: building the {side} side with {flags}")
        ok, log = runner_for(root, BuildVariant("feedback", flags, "")).build_log(case, mode)
        if not ok:
            return [], f"the {side} side did not build with {flags}: feedback not compared"
        units, project = _side_sources(root, defines)
        found[side] = feedback_diff.events(log, units, project, os.path.abspath(root))
        names[side] = {u.name for file_units in units.values() for u in file_units.walk() if u.name}
    return feedback_diff.diff(found["old"], found["new"], names["old"], names["new"]), ""


def run_fobis_bench(configuration):
    """
    Run FoBiS in bench mode: measure cases' run times (alone, against their history, or against a revision).

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    import functools
    import json
    import tempfile

    from .analysis import parse_defines
    from .Ecosystem import copy_working_copy
    from .verification import CaseError, load_cases, load_settings
    from .verification import bench as bm
    from .verification.diffrun import DiffRunError, copy_dependencies, export_revision, resolve

    cliargs = configuration.cliargs
    fobos = configuration.fobos
    as_json = getattr(cliargs, "json_output", False)
    compare = cliargs.bench_compare
    try:
        cases = load_cases(fobos)
        settings = load_settings(fobos)
        commit = resolve(".", compare) if compare else ""
        if cliargs.bench_feedback and not compare:
            raise CaseError("--feedback needs --compare REF")
        if cliargs.bench_record and compare:
            raise CaseError("--record records the working tree alone: run it without --compare")
        declared = [n for n in cases if fobos.fobos is not None and fobos.fobos.has_section(f"bench:{n}")]
        wanted = cliargs.bench_names or declared or list(cases)
        unknown = [n for n in wanted if n not in cases]
        if unknown or not wanted:
            what = f"unknown case(s) {', '.join(unknown)}" if unknown else "no case declared"
            raise CaseError(f"{what} (declared: {', '.join(cases) or 'none'})")
        specs = {name: bm.load_spec(fobos, name) for name in wanted}
    except (CaseError, DiffRunError) as exc:
        configuration.print_r(f"Error: {exc}")
        sys.exit(2)
    label = (commit[:12] if commit.startswith(compare) else compare) if compare else ""
    fobos_args = ["--fobos", cliargs.fobos] if cliargs.fobos else []
    if cliargs.fobos_case_insensitive:
        fobos_args.append("--fobos-case-insensitive")
    deps_dir = fobos.get_deps_dir() if fobos.fobos else ".fobis_deps"
    environment = _mode_environments(settings, fobos_args, deps_dir)

    def say(line):
        print(f"bench: {line}", file=sys.stderr, flush=True)

    scratch = ""
    roots = {"new": "."}
    results = []
    try:
        if compare:
            scratch = tempfile.mkdtemp(prefix="fobis-bench-", dir=_scratch_parent(cliargs))
            roots = {"old": os.path.join(scratch, "revision"), "new": os.path.join(scratch, "worktree")}
            say(f"extracting {compare} ({commit[:12]}) and copying the working tree to {scratch}")
            notes = []
            export_revision(".", commit, roots["old"], notes)
            copy_working_copy(".", roots["new"])
            copy_dependencies(".", deps_dir, roots["old"])
            copy_dependencies(".", deps_dir, roots["new"])
        for name in wanted:
            case, spec = cases[name], specs[name]
            if cliargs.bench_runs:
                spec.max_runs = cliargs.bench_runs
                spec.min_runs = min(spec.min_runs, spec.max_runs)
            mode = cliargs.bench_mode or case.mode
            env = environment(mode)
            result = bm.BenchResult(name, mode or "", spec.time)
            results.append(result)

            def runner_for(root, variant=None, env=env):
                return _make_runner(
                    configuration,
                    root,
                    fobos_args,
                    settings.runs_dir,
                    settings.launcher,
                    deps_dir,
                    env=env,
                    variant=variant,
                )

            runs, provenances = {}, {}
            for side, root in roots.items():
                runner = runner_for(root)
                provenances[side] = runner.provenance(case, mode)
                binary = None
                if case.target:
                    say(f"case {name}: building {'the working tree' if side == 'new' else label}")
                    binary, report = runner.build(case, mode)
                    if binary is None:
                        errors = report.get("errors") or [d.get("message", "") for d in report.get("diagnostics", [])]
                        result.status = "error"
                        result.error = f"{side} side: build failed" + (f": {errors[0]}" if errors else "")
                        break
                runs[side] = functools.partial(
                    runner.run, case, variant=f"bench-{side}", mode=mode, binary=binary, provenance=provenances[side]
                )
            if result.status == "error":
                continue
            try:
                samples = bm.measure(runs, spec, progress=lambda m, n=name: say(f"case {n}: {m}"))
            except bm.RunFailedError as exc:
                result.status, result.error = "error", str(exc)
                continue
            result.stats = {side: bm.summarise(samples[side], spec) for side in runs}
            result.mode = provenances["new"].get("mode") or result.mode
            new = result.stats["new"]
            provenance = provenances["new"]
            result.notes = bm.notes(spec, new, provenance.get("compiler", {}).get("cflags", ""), provenance)
            if compare:
                result.comparison = {**bm.verdict(result.stats["old"], new), "against": label}
                if cliargs.bench_feedback and case.target:
                    defines = parse_defines(_merged_preproc_flags(cliargs))
                    changes, note = _bench_feedback(case, mode, roots, runner_for, defines, say)
                    result.feedback = [c.to_dict() for c in changes]
                    if note:
                        result.notes.append(note)
            else:
                path = bm.history_path(settings.bench_dir, name)
                previous = bm.latest_comparable(bm.read_history(path), bm.machine_key(provenance), mode or "")
                if previous:
                    against = f"recorded {previous.get('commit', '')[:12] or '?'} ({previous.get('date', '')})"
                    result.comparison = {**bm.verdict(bm.stats_from(previous["stats"]), new), "against": against}
                if cliargs.bench_record:
                    bm.append_history(path, bm.record(name, mode or "", new, provenance))
                    result.recorded = path
    except (DiffRunError, RuntimeError, OSError) as exc:
        configuration.print_r(f"Error: {exc}")
        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)
        sys.exit(2)
    if scratch and not cliargs.bench_keep:
        shutil.rmtree(scratch, ignore_errors=True)
    failed = any(r.status != "ok" or (r.comparison or {}).get("verdict") == "slower" for r in results)
    if as_json:
        data = {"status": "fail" if failed else "ok", "compare": compare or "", "commit": commit}
        data["cases"] = [r.to_dict() for r in results]
        if scratch and cliargs.bench_keep:
            data["scratch"] = scratch
        print(json.dumps(data, indent=2))
    else:
        lines = []
        for r in results:
            lines.append(f"bench {r.case} (mode {r.mode or 'default'}, {r.time} time)")
            if r.status != "ok":
                lines.append(f"  ERROR: {r.error}")
                continue
            if "old" in r.stats:
                lines.append(f"  {label}: {bm.describe(r.stats['old'])}")
            lines.append(f"  {'working tree' if compare else 'measured'}: {bm.describe(r.stats['new'])}")
            if r.comparison:
                lines.append(f"  vs {r.comparison['against']}: {bm.describe_verdict(r.comparison)}")
            from .verification.feedback_diff import Change

            for change in r.feedback:
                lines.append(
                    "  "
                    + Change(
                        **{k: change[k] for k in ("procedure", "category", "detail", "old", "new", "lines", "scope")}
                    ).text()
                )
            if compare and cliargs.bench_feedback and not r.feedback and not any("feedback" in n for n in r.notes):
                lines.append("  compiler feedback: no change in vectorisation or data movement")
            lines += [f"  note: {n}" for n in r.notes]
            if r.recorded:
                lines.append(f"  recorded in {r.recorded}")
        if scratch and cliargs.bench_keep:
            lines.append(f"scratch copies kept in {scratch}")
        (configuration.print_r if failed else configuration.print_b)("\n".join(lines))
    if failed:
        sys.exit(1)


def _gate_plan(configuration, config, mode, fobos_args):
    """The gate's `Plan` for this project: each stage's commands, or why it does not apply; and the base label."""
    import subprocess

    from .TestRunner import discover_tests
    from .verification import load_cases
    from .verification.assess import load_spec
    from .verification.gate import GateError, Plan

    fobos = configuration.fobos
    parser = fobos.fobos if fobos is not None else None
    cases = load_cases(fobos)
    plan = Plan()
    mode_args = ["--mode", mode] if mode else []

    def git(*args):
        done = subprocess.run(["git", *args], capture_output=True, text=True)
        return done.returncode, done.stdout.strip()

    repository = git("rev-parse", "--is-inside-work-tree")[0] == 0
    ref, label, changed = "HEAD", "", True
    if config.base:
        if not repository:
            raise GateError("--base needs a git repository")
        code, merge_base = git("merge-base", "HEAD", config.base)
        if code != 0:
            raise GateError(f"{config.base!r} is not a revision with a merge base with HEAD")
        ref, label = merge_base, f"{config.base} (merge base {merge_base[:12]})"
    elif repository:
        changed = bool(git("status", "--porcelain", "--untracked-files=normal")[1])
    unchanged = "the working tree has no change against HEAD (--base REF gates committed work)"

    def add(stage, *commands):
        plan.commands[stage] = [[*c, *fobos_args] for c in commands]

    add("build", ["build", "--json", *mode_args])
    if not repository:
        plan.skipped["review"] = "not a git repository"
    elif not changed:
        plan.skipped["review"] = unchanged
    else:
        add(
            "review",
            [
                "review",
                "--format",
                "json",
                "--exit-zero",
                *mode_args,
                *(["--base", ref, "--worktree"] if label else []),
            ],
        )
    test_dir = fobos.get_test_config()["test_dir"] if parser is not None else "test"
    if discover_tests(test_dir):
        add("test", ["test", "--json", *mode_args])
    else:
        plan.skipped["test"] = f"no test program in {test_dir}/"
    no_case = "no case declared ([case:NAME])"
    if cases:
        add("verify", ["verify", "--json"])
    else:
        plan.skipped["verify"] = no_case
    for stage, command in (("diff-run", ["diff-run", ref, "--json"]), ("bench", ["bench", "--compare", ref, "--json"])):
        benches = [n for n in cases if parser is not None and parser.has_section(f"bench:{n}")]
        if not cases:
            plan.skipped[stage] = no_case
        elif stage == "bench" and not benches:
            plan.skipped[stage] = "no benchmark declared ([bench:NAME])"
        elif not repository:
            plan.skipped[stage] = "not a git repository"
        elif not changed:
            plan.skipped[stage] = unchanged
        else:
            add(stage, command)
    budgeted = [
        n for n in cases if parser is not None and parser.has_section(f"assess:{n}") and load_spec(fobos, n).budgets
    ]
    if budgeted:
        add("assess", *(["assess", n, "--json"] for n in budgeted))
    else:
        plan.skipped["assess"] = "no assessment budget declared ([assess:NAME] budget)"
    if config.matrix_modes:
        command = ["matrix", "--json", "--modes", ",".join(config.matrix_modes)]
        add("matrix", command + ["--shadows", ",".join(config.matrix_shadows)] + (["--verify"] if cases else []))
    else:
        plan.skipped["matrix"] = "no matrix declared ([gate] matrix_modes)"
    return plan, label


def run_fobis_gate(configuration):
    """
    Run FoBiS in gate mode: the declared checks as stages, one verdict with the first failing fact of each.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    import json
    import subprocess
    import time

    from .mcp_server import fobis_command
    from .verification import CaseError
    from .verification.gate import GateError, load_config, render_text, run_gate, verdict

    cliargs = configuration.cliargs
    try:
        config = load_config(configuration.fobos)
        if cliargs.gate_stages:
            config.stages = list(cliargs.gate_stages)
        config.skip(cliargs.gate_skip, "--skip")
        config.advisory |= set(cliargs.gate_advisory)
        config.base = cliargs.gate_base or config.base
        config.check()
        mode = cliargs.gate_mode or config.mode
        fobos_args = ["--fobos", cliargs.fobos] if cliargs.fobos else []
        if cliargs.fobos_case_insensitive:
            fobos_args.append("--fobos-case-insensitive")
        plan, label = _gate_plan(configuration, config, mode, fobos_args)
    except (GateError, CaseError) as exc:
        configuration.print_r(f"Error: {exc}")
        sys.exit(2)

    def run(args):
        done = subprocess.run([*fobis_command(), *args], capture_output=True, text=True)
        return done.returncode, done.stdout, done.stderr

    start = time.monotonic()
    results = run_gate(
        config,
        plan,
        run,
        progress=lambda m: print(f"gate: {m}", file=sys.stderr, flush=True),
        fail_fast=cliargs.gate_fail_fast,
    )
    total = time.monotonic() - start
    status = verdict(results)
    if getattr(cliargs, "json_output", False):
        data = {"status": status, "base": label, "elapsed": round(total, 2), "stages": [r.to_dict() for r in results]}
        print(json.dumps(data, indent=2))
    else:
        (configuration.print_b if status == "pass" else configuration.print_r)(render_text(results, total, label))
    if status != "pass":
        sys.exit(1)


def run_fobis_profile(configuration):
    """
    Run FoBiS in profile mode: build a case's program for a profiler, run it, map the profile to the sources.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    import glob
    import json
    import re
    import shutil as _shutil
    import subprocess

    from .analysis import parse_defines
    from .lint import discover_files, lint_files
    from .verification import CaseError, LocalRunner, load_cases, load_settings
    from .verification import profile as pf
    from .verification.runner import BuildVariant
    from .verification.shadow import family

    cliargs = configuration.cliargs
    as_json = getattr(cliargs, "json_output", False)
    tool = cliargs.profile_tool
    try:
        cases = load_cases(configuration.fobos)
        if cliargs.profile_case not in cases:
            raise CaseError(f"unknown case {cliargs.profile_case!r} (declared: {', '.join(cases) or 'none'})")
        if tool not in pf.TOOLS:
            raise CaseError(f"unknown tool {tool!r} (available: {', '.join(pf.TOOLS)}; ncu is not supported)")
        executable = {"gprof": "gprof", "callgrind": "valgrind", "nsys": "nsys"}[tool]
        if _shutil.which(executable) is None:
            raise CaseError(f"{executable} is not on PATH (needed by --tool {tool})")
        case = cases[cliargs.profile_case]
        if tool == "gprof" and not case.target:
            raise CaseError(
                f"case {case.name} runs a command: gprof needs a program FoBiS builds (use --tool callgrind)"
            )
    except CaseError as exc:
        configuration.print_r(f"Error: {exc}")
        sys.exit(2)
    settings = load_settings(configuration.fobos)
    fobos_args = ["--fobos", cliargs.fobos] if cliargs.fobos else []
    if cliargs.fobos_case_insensitive:
        fobos_args.append("--fobos-case-insensitive")
    deps_dir = configuration.fobos.get_deps_dir() if configuration.fobos.fobos else ".fobis_deps"
    mode = cliargs.profile_mode or case.mode
    environment = _mode_environments(settings, fobos_args, deps_dir)(mode)

    probe = LocalRunner(".", fobos_args, settings.runs_dir, settings.launcher, deps_dir, env=environment)
    compiler = probe.introspect(mode).get("compiler", {}).get("name", "") if case.target else ""
    if tool == "gprof":
        flags = pf.GPROF_FLAGS.get(family(compiler) or "")
        if not flags:
            configuration.print_r(f"Error: no gprof flag known for the compiler {compiler!r} (use --tool callgrind)")
            sys.exit(2)
        variant = BuildVariant("profile-gprof", f"{flags} -g", flags)
    elif tool == "callgrind":
        variant = BuildVariant("profile-callgrind", "-g", "") if case.target else None
    else:
        variant = None  # nsys: the mode's own build
    runner = _make_runner(
        configuration, ".", fobos_args, settings.runs_dir, settings.launcher, deps_dir, env=environment, variant=variant
    )
    wrapper = []
    if tool == "callgrind":
        wrapper = ["valgrind", "--tool=callgrind", "--callgrind-out-file=callgrind.out.%p"]
    elif tool == "nsys":
        wrapper = pf.NSYS_WRAPPER
    else:
        case.env = {**case.env, "GMON_OUT_PREFIX": "gmon.out"}  # one file per process (MPI ranks), summed by gprof
    if wrapper:
        unwrapped = runner.command
        runner.command = lambda case_, program: pf.wrap(unwrapped(case_, program), program, case_.args, wrapper)
    binary = None
    print(f"profile: building {case.name} for {tool}", file=sys.stderr, flush=True)
    if case.target:
        binary, report = runner.build(case, mode)
        if binary is None:
            errors = report.get("errors") or [d.get("message", "") for d in report.get("diagnostics", [])]
            configuration.print_r(f"Error: the build for {tool} failed" + (f": {errors[0]}" if errors else ""))
            sys.exit(1)
    print(f"profile: running {case.name} under {tool}", file=sys.stderr, flush=True)
    result = runner.run(case, variant=f"profile-{tool}", mode=mode, binary=binary)
    if result.status not in ("ok", "probe-error"):
        tail = (result.stderr or "").strip().splitlines()[-1:] or [result.status]
        configuration.print_r(f"Error: the run under {tool} {result.status}: {tail[0]}")
        sys.exit(1)
    files = discover_files(
        cliargs.src,
        extensions=cliargs.extensions,
        exclude=cliargs.exclude,
        exclude_dirs=cliargs.exclude_dirs,
        recursive=not cliargs.disable_recursive_search,
    )
    analysed = lint_files(files, [], defines=parse_defines(_merged_preproc_flags(cliargs)))
    source = pf.SourceMap(analysed.units, main=case.target or None)
    try:
        if tool == "gprof":
            outputs = sorted(glob.glob(os.path.join(result.rundir, "gmon.out*")))
            if not outputs:
                raise pf.ProfileError("no gmon.out written (the program must end normally to write it)")
            done = subprocess.run(["gprof", "-b", "-p", binary, *outputs], capture_output=True, text=True)
            profile = pf.from_gprof(done.stdout, source, cliargs.profile_top)
            if len(outputs) > 1:  # one file per process: each one's own total (load balance across MPI ranks)
                for output in outputs:
                    alone = subprocess.run(["gprof", "-b", "-p", binary, output], capture_output=True, text=True)
                    profile.processes.append(round(sum(r.self_cost for r in pf.parse_gprof(alone.stdout)[0]), 6))
        elif tool == "nsys":
            reports = sorted(
                glob.glob(os.path.join(result.rundir, "nsys-*.nsys-rep")),
                key=lambda p: int(re.sub(r"\D", "", os.path.basename(p)) or 0),
            )
            if not reports:
                raise pf.ProfileError("nsys wrote no report (is nsys available where the program ran?)")
            tables = []
            for report in reports:
                base = report[: -len(".nsys-rep")]
                subprocess.run(
                    [
                        "nsys",
                        "stats",
                        "--format",
                        "csv",
                        "--force-export=true",
                        "--report",
                        ",".join(pf.NSYS_REPORTS),
                        "--output",
                        base,
                        report,
                    ],
                    capture_output=True,
                    text=True,
                )
                own = {}
                for name in pf.NSYS_REPORTS:
                    with contextlib.suppress(OSError), open(f"{base}_{name}.csv", encoding="utf-8") as handle:
                        own[name] = pf.parse_csv(handle.read())
                tables.append(own)
            profile = pf.from_nsys(tables, source, cliargs.profile_top)
        else:
            data = pf.Callgrind()
            for path in sorted(glob.glob(os.path.join(result.rundir, "callgrind.out.*"))):
                with open(path, encoding="utf-8", errors="replace") as handle:
                    pf.parse_callgrind(handle.read(), data)
            profile = pf.from_callgrind(data, source, cliargs.profile_top)
    except pf.ProfileError as exc:
        configuration.print_r(f"Error: {exc}")
        sys.exit(1)
    if as_json:
        data = {"case": case.name, "mode": result.provenance.get("mode") or mode or "", **profile.to_dict()}
        data["run"] = {"status": result.status, "elapsed": round(result.elapsed, 3), "rundir": result.rundir}
        print(json.dumps(data, indent=2))
    else:
        configuration.print_b(pf.render_text(case.name, profile))


def run_fobis_modernize(configuration):
    """
    Run FoBiS in modernize mode: lint fixes applied to a scratch copy, kept when build, tests and cases agree.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    import json
    import subprocess
    import tempfile

    from .ai.agents_md import project_files
    from .analysis import parse_defines, read_source
    from .Ecosystem import copy_working_copy
    from .lint import discover_files, lint_files, select_rules
    from .mcp_server import fobis_command
    from .TestRunner import discover_tests
    from .verification import CaseError, LocalRunner, load_cases, load_settings
    from .verification import modernize as mz
    from .verification.diffrun import compare, copy_dependencies
    from .verification.gate import build_facts, parse_json

    cliargs = configuration.cliargs
    fobos = configuration.fobos
    try:
        rules = select_rules(cliargs.modernize_select or list(mz.FIXABLE_RULES), [])
        cases = load_cases(fobos)
    except (ValueError, CaseError) as exc:
        configuration.print_r(f"Error: {exc}")
        sys.exit(2)
    deps_dir = fobos.get_deps_dir() if fobos is not None and fobos.fobos is not None else ".fobis_deps"
    files = discover_files(
        cliargs.src,
        extensions=cliargs.extensions,
        exclude=cliargs.exclude,
        exclude_dirs=cliargs.exclude_dirs,
        recursive=not cliargs.disable_recursive_search,
    )
    result = lint_files(
        project_files(files, ".", deps_dir), rules, defines=parse_defines(_merged_preproc_flags(cliargs))
    )
    plan = mz.make_plan(result.findings, read_source)
    as_json = getattr(cliargs, "json_output", False)
    if not plan.by_rule:
        message = "nothing to modernise: no automatic fix applies"
        print(json.dumps({"status": "nothing", "fixes": {}}) if as_json else message)
        return
    settings = load_settings(fobos)
    fobos_args = ["--fobos", cliargs.fobos] if cliargs.fobos else []
    mode_args = ["--mode", cliargs.mode] if cliargs.mode else []
    test_dir = fobos.get_test_config()["test_dir"] if fobos is not None and fobos.fobos is not None else "test"
    has_tests = bool(discover_tests(test_dir))
    scratch = tempfile.mkdtemp(prefix="fobis-modernize-")
    notes: list[str] = []

    def say(line):
        print(f"modernize: {line}", file=sys.stderr, flush=True)

    def fobis_in(root, args):
        done = subprocess.run([*fobis_command(), *args, *fobos_args], cwd=root, capture_output=True, text=True)
        return parse_json(done.stdout) or {}

    def copy(name):
        root = os.path.join(scratch, name)
        copy_working_copy(".", root)
        copy_dependencies(".", deps_dir, root)
        return root

    def test_statuses(root):
        return {r["name"]: r["status"] for r in fobis_in(root, ["test", "--json", *mode_args]).get("results", [])}

    def run_cases(root):
        runner = LocalRunner(root, fobos_args, settings.runs_dir, settings.launcher, deps_dir)
        return {name: runner.run(case, variant="modernize") for name, case in cases.items()}

    try:
        say(f"base copy in {scratch}")
        base = copy("base")
        base_build = fobis_in(base, ["build", "--json", *mode_args])
        base_builds = base_build.get("status") == "ok"
        base_tests = test_statuses(base) if has_tests else None
        base_runs = run_cases(base) if cases else {}
        for name, run in list(base_runs.items()):
            if not run.ok:  # a case failing on the untouched copy shows nothing about the fixes
                notes.append(f"case {name} is {run.status} on the untouched copy: not used as evidence")
                del base_runs[name]

        def check(subset):
            say(f"checking {', '.join(subset)}")
            root = copy("fixed-" + "-".join(subset))
            mz.write_texts(root, mz.fixed_texts(plan, subset, read_source))
            verdict = mz.Check(list(subset))
            build = fobis_in(root, ["build", "--json", *mode_args])
            if build.get("status") == "ok":
                verdict.build = "ok"
            elif base_builds:
                verdict.status, verdict.build = "fail", (build_facts(build) or ["the build failed"])[0]
                return verdict
            else:  # the untouched copy does not build either: no evidence; tests and cases decide
                verdict.build = "fails as in the untouched copy: " + (build_facts(base_build) or ["?"])[0]
            fixed_tests = test_statuses(root) if has_tests else None
            diffs = []
            if base_runs:
                new_runs = run_cases(root)
                diffs = [compare(new_runs[n], base_runs[n], cases[n].tolerance) for n in base_runs]
            return mz.judge(verdict, base_tests, fixed_tests, diffs)

        checks = [check(plan.rules)]
        if checks[0].status == "pass":
            verified = plan.rules
        else:
            verified = []
            if len(plan.rules) > 1:
                for rule in plan.rules:
                    checks.append(check([rule]))
                    if checks[-1].status == "pass":
                        verified.append(rule)
    except (OSError, RuntimeError) as exc:
        configuration.print_r(f"Error: {exc}")
        shutil.rmtree(scratch, ignore_errors=True)
        sys.exit(2)
    applied = []
    evidence = checks[0].evidence
    if cliargs.modernize_apply and verified:
        if evidence == "build" and not cliargs.modernize_unverified:
            notes.append("no tests and no cases: a build alone does not show unchanged behaviour (--unverified)")
        else:
            for path, text in mz.fixed_texts(plan, verified, read_source).items():
                if mz.digest(read_source(path)) != plan.digests[path]:
                    notes.append(f"{path} changed since the analysis: not written")
                    continue
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(text)
                applied.append(path)
    if not cliargs.modernize_keep:
        shutil.rmtree(scratch, ignore_errors=True)
    failed = [r for r in plan.rules if r not in verified]
    if as_json:
        data = {
            "status": "verified" if not failed else ("partial" if verified else "failed"),
            "fixes": plan.counts(),
            "checks": [c.to_dict() for c in checks],
            "verified": verified,
            "applied": applied,
            "notes": notes,
        }
        if cliargs.modernize_keep:
            data["scratch"] = scratch
        print(json.dumps(data, indent=2))
    else:
        text = mz.render_text(plan, checks, applied, verified)
        text += "".join(f"\nnote: {n}" for n in notes)
        text += f"\nscratch copies kept in {scratch}" if cliargs.modernize_keep else ""
        (configuration.print_b if not failed else configuration.print_r)(text)
    if failed:
        sys.exit(1)


def _generic_specifics(module):
    """specific -> generic, for the specific procedures of a module's public generic interfaces."""
    import re

    from .ai.impact import _is_public

    found = {}
    for unit in module.children:
        if unit.kind == "interface" and unit.name and _is_public(module, unit.name):
            for statement in unit.statements:
                match = re.match(r"^(?:module\s+)?procedure\s*(?:::)?\s*(.*)$", statement.masked.strip())
                if match:
                    found.update((n.strip(), unit.name) for n in match.group(1).split(",") if n.strip())
    return found


def run_fobis_bindings(configuration):
    """
    Run FoBiS in bindings mode: bind(c) shims, a C header and a Python wrapper for the modules' public procedures.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    import json

    from . import bindings as bd
    from .ai.agents_md import project_files
    from .ai.impact import _is_public
    from .analysis import parse_defines
    from .lint import discover_files, lint_files

    cliargs = configuration.cliargs
    fobos = configuration.fobos
    deps_dir = fobos.get_deps_dir() if fobos is not None and fobos.fobos is not None else ""
    files = discover_files(
        cliargs.src,
        extensions=cliargs.extensions,
        exclude=cliargs.exclude,
        exclude_dirs=cliargs.exclude_dirs,
        recursive=not cliargs.disable_recursive_search,
    )
    analysed = lint_files(
        project_files(files, ".", deps_dir), [], defines=parse_defines(_merged_preproc_flags(cliargs))
    )
    modules = [u for f in analysed.units.values() for u in f.units if u.kind == "module"]
    wanted = cliargs.bindings_modules
    unknown = sorted(set(wanted) - {m.name for m in modules})
    if unknown or not modules:
        what = f"unknown module(s) {', '.join(unknown)}" if unknown else "no module in the sources"
        configuration.print_r(f"Error: {what}")
        sys.exit(2)
    bindings = []
    for module in sorted(modules, key=lambda m: m.name):
        if not wanted or module.name in wanted:
            bindings += bd.plan(module, analysed.project, _is_public, _generic_specifics(module))
    project = fobos.get_project_info().get("name", "") if fobos is not None and fobos.fobos is not None else ""
    name = (cliargs.bindings_name or project or os.path.basename(os.getcwd())).lower().replace("-", "_")
    outputs = {
        f"{name}_c.f90": bd.shim(bindings, name),
        f"{name}.h": bd.header(bindings, name),
        f"{name}.py": bd.python(bindings, name),
    }
    written = []
    if not cliargs.bindings_print and any(not b.skipped for b in bindings):
        targets = {os.path.join(cliargs.bindings_output_dir, f): text for f, text in outputs.items()}
        existing = [p for p in targets if os.path.exists(p)]
        if existing and not cliargs.bindings_force:
            configuration.print_r(f"Error: {', '.join(existing)} exist(s): use --force to overwrite, or --print")
            sys.exit(2)
        os.makedirs(cliargs.bindings_output_dir, exist_ok=True)
        for path, text in targets.items():
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
            written.append(path)
    if getattr(cliargs, "json_output", False):
        print(json.dumps({"bindings": [b.to_dict() for b in bindings], "files": written}, indent=2))
        return
    configuration.print_b(bd.report(bindings) + ("\nwritten: " + ", ".join(written) if written else ""))


def run_fobis_fpm(configuration):
    """
    Run FoBiS in fpm mode: translate an fpm.toml into a fobos (import) or a fobos into an fpm.toml (export).

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    import json
    import re

    from .fpm import FpmError, fobos_from_fpm, fpm_from_fobos, load_toml

    cliargs = configuration.cliargs
    try:
        if cliargs.fpm_action == "import":
            if not os.path.isfile(cliargs.fpm_manifest):
                raise FpmError(f"{cliargs.fpm_manifest} not found")
            with open(cliargs.fpm_manifest, encoding="utf-8") as handle:
                manifest = load_toml(handle.read())
            root = os.path.dirname(os.path.abspath(cliargs.fpm_manifest))
            translation = fobos_from_fpm(manifest, root, cliargs.fpm_compiler)
        else:
            from .ai.agents_md import project_files
            from .analysis import parse_defines
            from .lint import discover_files, lint_files

            fobos = configuration.fobos
            if fobos is None or fobos.fobos is None:
                raise FpmError("no fobos to export (fobis fpm export reads the fobos of the current directory)")
            deps_dir = fobos.get_deps_dir()
            files = discover_files(
                cliargs.src,
                extensions=cliargs.extensions,
                exclude=cliargs.exclude,
                exclude_dirs=cliargs.exclude_dirs,
                recursive=not cliargs.disable_recursive_search,
            )
            defines = parse_defines(_merged_preproc_flags(cliargs))
            analysed = lint_files(project_files(files, ".", deps_dir), [], defines=defines)
            project = fobos.get_project_info()
            version = fobos.get_version() or project.get("version", "")
            project["version"] = version[1:] if re.fullmatch(r"v\d.*", version) else version  # fpm: 1.2.3
            if fobos.fobos.has_option("project", "summary"):
                project["summary"] = " ".join(fobos.fobos.get("project", "summary").split())
            test_dir = fobos.get_test_config()["test_dir"] if fobos.fobos.has_section("test") else ""
            mode_keys = {"mpi": bool(cliargs.mpi), "openmp": bool(cliargs.openmp)}
            macros = [d for d in _merged_preproc_flags(cliargs).split() if d.startswith("-D")]
            translation = fpm_from_fobos(
                project, fobos.get_dependencies(), analysed.units, ".", test_dir, mode_keys, macros
            )
        output = cliargs.fpm_output
        written = ""
        if not cliargs.fpm_print:
            if os.path.exists(output) and not cliargs.fpm_force:
                raise FpmError(f"{output} exists: use --force to overwrite it, or --print")
            with open(output, "w", encoding="utf-8") as handle:
                handle.write(translation.text)
            written = output
    except (FpmError, OSError) as exc:
        configuration.print_r(f"Error: {exc}")
        sys.exit(2)
    if getattr(cliargs, "json_output", False):
        print(json.dumps({"written": written, "text": translation.text, "notes": translation.notes}, indent=2))
        return
    if cliargs.fpm_print:
        print(translation.text, end="")
    else:
        configuration.print_b(f"{written} written")
    for note in translation.notes:
        configuration.print_r(f"note: {note}")


def run_fobis_diff_run(configuration):
    """
    Run FoBiS in diff-run mode: the cases on a revision and on the working tree, built and run in scratch copies,
    their quantities compared.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    import json
    import tempfile

    from .Ecosystem import copy_working_copy
    from .verification import CaseError, load_cases, load_settings
    from .verification.assess import AssessError, assess, load_spec
    from .verification.diffrun import (
        DiffRunError,
        changed_files,
        compare,
        copy_dependencies,
        export_revision,
        judge,
        resolve,
    )
    from .verification.provenance import git_state
    from .verification.verify import render_text

    cliargs = configuration.cliargs
    fobos = configuration.fobos
    as_json = getattr(cliargs, "json_output", False)
    ref = cliargs.diff_ref or "HEAD"
    try:
        cases = load_cases(fobos)
        settings = load_settings(fobos)
        commit = resolve(".", ref)
    except (CaseError, DiffRunError) as exc:
        configuration.print_r(f"Error: {exc}")
        sys.exit(2)
    label = commit[:12] if commit.startswith(ref) else ref  # a full hash given: its short form
    wanted = cliargs.diff_names or list(cases)
    unknown = [n for n in wanted if n not in cases]
    if unknown or not wanted:
        what = f"unknown case(s) {', '.join(unknown)}" if unknown else "no case declared"
        configuration.print_r(f"Error: {what} (declared: {', '.join(cases) or 'none'})")
        sys.exit(2)
    fobos_args = ["--fobos", cliargs.fobos] if cliargs.fobos else []
    if cliargs.fobos_case_insensitive:
        fobos_args.append("--fobos-case-insensitive")
    deps_dir = fobos.get_deps_dir() if fobos.fobos else ".fobis_deps"
    environment = _mode_environments(settings, fobos_args, deps_dir)
    scratch = tempfile.mkdtemp(prefix="fobis-diff-run-", dir=_scratch_parent(cliargs))
    old_root, new_root = os.path.join(scratch, "revision"), os.path.join(scratch, "worktree")
    notes: list[str] = []

    def say(line):
        print(f"diff-run: {line}", file=sys.stderr, flush=True)

    try:
        say(f"extracting {ref} ({commit[:12]}) and copying the working tree to {scratch}")
        export_revision(".", commit, old_root, notes)
        copy_working_copy(".", new_root)
        if copy_dependencies(".", deps_dir, old_root) and copy_dependencies(".", deps_dir, new_root):
            notes.append(f"both sides use the working copy's fetched dependencies ({deps_dir})")
        changed = changed_files(".", commit)
        repository = git_state(".")
        diffs = []
        for name in wanted:
            case = cases[name]
            mode = cliargs.diff_mode or case.mode
            env = environment(mode)
            sides = {}
            for side, root in (("old", old_root), ("new", new_root)):
                say(f"case {name}: build and run on the {'revision' if side == 'old' else 'working tree'}")
                runner = _make_runner(
                    configuration, root, fobos_args, settings.runs_dir, settings.launcher, deps_dir, env=env
                )
                sides[side] = runner.run(case, variant=f"diff-run-{side}", mode=mode)
            sides["old"].provenance["git"] = {"commit": commit, "ref": ref}
            sides["new"].provenance["git"] = repository
            case_diff = compare(sides["new"], sides["old"], case.tolerance)
            changes = case_diff.verification.provenance_changes  # the code change is listed above, file by file
            case_diff.verification.provenance_changes = [c for c in changes if not c.startswith("git.")]
            if cliargs.diff_assess and case_diff.verification.status == "fail":
                say(f"case {name}: assessing the working tree's own spread")
                spec = load_spec(fobos, name)
                families = [f for f in spec.families if f not in ("inputs", "refinement")] or ["rounding"]

                def runner_for(build, mode_, root=new_root):
                    return _make_runner(
                        configuration,
                        root,
                        fobos_args,
                        settings.runs_dir,
                        settings.launcher,
                        deps_dir,
                        env=environment(mode_),
                        variant=build,
                    )

                assessment = assess(spec, case, families, runner_for, root=new_root, mode=mode)
                digits = {}
                for family in assessment.families:
                    for quantity, data in family.quantities.items():
                        if data.get("digits") is not None:
                            digits[quantity] = min(digits.get(quantity, float("inf")), float(data["digits"]))
                judge(case_diff, digits)
            diffs.append(case_diff)
    except (DiffRunError, AssessError, RuntimeError, OSError) as exc:
        configuration.print_r(f"Error: {exc}")
        shutil.rmtree(scratch, ignore_errors=True)
        sys.exit(2)
    if not cliargs.diff_keep:
        shutil.rmtree(scratch, ignore_errors=True)
    ok = all(d.ok for d in diffs)
    if as_json:
        data = {
            "ref": ref,
            "commit": commit,
            "status": "equivalent" if ok else "differs",
            "changed": [c.to_dict() for c in changed],
            "notes": notes,
            "cases": [d.to_dict() for d in diffs],
        }
        if cliargs.diff_keep:
            data["scratch"] = scratch
        print(json.dumps(data, indent=2))
    else:
        shown = label if label == commit[:12] else f"{label} ({commit[:12]})"
        lines = [f"diff-run: {shown} vs the working tree, {len(changed)} file(s) changed"]
        for item in changed[:20]:
            procedures = f": {', '.join(item.procedures[:6])}" if item.procedures else ""
            lines.append(f"  {item.status} {item.path}{procedures}")
        if len(changed) > 20:
            lines.append(f"  ... {len(changed) - 20} more")
        lines += [f"note: {note}" for note in notes]
        for d in diffs:
            for name, item in d.spread.items():
                if "within" in item:
                    verdict = "within" if item["within"] else "beyond"
                    digits = item["digits"]
                    shared = "every digit" if digits == "inf" else f"{digits:.1f} digit(s)"
                    d.verification.note = (d.verification.note + "; " if d.verification.note else "") + (
                        f"{name}: {verdict} the working tree's own spread ({shared} shared by its variants)"
                    )
        statuses = {"pass": "equivalent", "fail": "differs", "run-failed": "new-failed"}
        for d in diffs:
            if d.status == "within-uncertainty":
                d.verification.status = "within-uncertainty"
        report = render_text([d.verification for d in diffs], reference=label, statuses=statuses).splitlines()
        report[-1] = f"{sum(d.ok for d in diffs)} of {len(diffs)} case(s) equivalent."
        lines += ["", *report]
        if cliargs.diff_keep:
            lines.append(f"scratch copies kept in {scratch}")
        (configuration.print_b if ok else configuration.print_r)("\n".join(lines))
    if not ok:
        sys.exit(1)


def run_fobis_assess(configuration):
    """
    Run FoBiS in assess mode: ensembles of variants of a case and what their spread says about its quantities.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    import json

    from .verification import CaseError, load_cases, load_settings
    from .verification.assess import FAMILIES, AssessError, assess, load_spec, render_text

    cliargs = configuration.cliargs
    fobos = configuration.fobos
    try:
        cases = load_cases(fobos)
        settings = load_settings(fobos)
        spec = load_spec(fobos, cliargs.assess_name)
    except CaseError as exc:
        configuration.print_r(f"Error: {exc}")
        sys.exit(2)
    case = cases.get(cliargs.assess_name)
    families = cliargs.assess_families or spec.families
    bad = [f for f in families if f not in FAMILIES]
    if case is None or bad:
        what = (
            f"unknown case {cliargs.assess_name!r} (declared: {', '.join(cases) or 'none'})"
            if case is None
            else f"unknown family {', '.join(bad)} (known: {', '.join(FAMILIES)})"
        )
        configuration.print_r(f"Error: {what}")
        sys.exit(2)
    fobos_args = ["--fobos", cliargs.fobos] if cliargs.fobos else []
    if cliargs.fobos_case_insensitive:
        fobos_args.append("--fobos-case-insensitive")
    deps_dir = fobos.get_deps_dir() if fobos.fobos else ".fobis_deps"
    environment = _mode_environments(settings, fobos_args, deps_dir)

    def runner_for(build, mode):
        return _make_runner(
            configuration,
            ".",
            fobos_args,
            settings.runs_dir,
            settings.launcher,
            deps_dir,
            env=environment(mode),
            variant=build,
        )

    def progress(line):
        print(f"assess: {line}", file=sys.stderr, flush=True)

    try:
        assessment = assess(
            spec,
            case,
            families,
            runner_for,
            mode=cliargs.assess_mode,
            samples=cliargs.assess_samples,
            jobs=cliargs.assess_jobs,
            progress=progress,
        )
    except (AssessError, RuntimeError) as exc:
        configuration.print_r(f"Error: {exc}")
        sys.exit(2)
    if getattr(cliargs, "json_output", False):
        print(json.dumps(assessment.to_dict(), indent=2))
    else:
        (configuration.print_b if assessment.ok else configuration.print_r)(render_text(assessment))
    if not assessment.ok:
        sys.exit(1)


def run_fobis_provenance(configuration):
    """
    Run FoBiS in provenance mode: print what a result produced now would depend on.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    import json

    from .verification.case import Case

    runner = _verification_runner(configuration)
    mode = configuration.cliargs.prov_mode
    data = runner.provenance(Case("provenance", target="-"), mode)
    if getattr(configuration.cliargs, "json_output", False):
        print(json.dumps(data, indent=2))
        return

    def lines(value, indent=""):
        for key, item in value.items():
            if isinstance(item, dict):
                yield f"{indent}{key}:"
                yield from lines(item, indent + "  ")
            elif isinstance(item, list):
                yield f"{indent}{key}: {', '.join(map(str, item)) or '-'}"
            else:
                yield f"{indent}{key}: {item if item not in ('', None) else '-'}"

    configuration.print_b("\n".join(lines(data)))


def _testgen_dirs(configuration) -> tuple[str, str]:
    """``testgen``: the test directory (fobos ``[test] test_dir``) and the directory, relative to the project
    root, where test programs are built in the scratch copy: the test directory when the mode's sources contain it
    (a target outside the sources is not built), else the first source directory."""
    cliargs = configuration.cliargs
    fobos = configuration.fobos
    test_dir = (fobos.get_test_config() if fobos.fobos else {}).get("test_dir", "test")
    sources = [os.path.abspath(s) for s in cliargs.src or ["./"]]
    scanned = os.path.abspath(test_dir)
    if any(scanned == s or scanned.startswith(s.rstrip(os.sep) + os.sep) for s in sources):
        return test_dir, os.path.relpath(scanned)
    return test_dir, os.path.relpath(sources[0])


def run_fobis_testgen(configuration):
    """
    Run FoBiS in testgen mode: generate a test program for the public procedures of a module.

    The compile-checked skeleton comes from facts; the model completes it; its program is built and run in a
    scratch copy of the project and kept only when it builds, runs with exit status 0 and checks something. The
    user's tree is written only with ``--apply``, never over an existing file.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    import json

    from .ai.grounding import load_prompt
    from .ai.testgen import (
        Sandbox,
        build_bundle,
        checked_skeleton,
        example_test,
        find_module,
        generate,
        plan_cases,
        program_name,
        render_cases,
    )
    from .analysis import parse_defines
    from .lint import discover_files

    cliargs = configuration.cliargs
    as_json = cliargs.testgen_format == "json"
    say = configuration.print_b
    warn = (lambda m: print(m, file=sys.stderr)) if as_json else configuration.print_r  # stdout: the JSON only
    if cliargs.testgen_format not in ("text", "json"):
        warn(f"Error: unknown format {cliargs.testgen_format!r}: use text or json")
        sys.exit(2)
    status = (lambda m: print(m, file=sys.stderr)) if as_json else say
    files = discover_files(
        cliargs.src,
        extensions=cliargs.extensions,
        exclude=cliargs.exclude,
        exclude_dirs=cliargs.exclude_dirs,
        recursive=not cliargs.disable_recursive_search,
    )
    target = find_module(cliargs.testgen_module, files, defines=parse_defines(_merged_preproc_flags(cliargs)))
    if target is None:
        warn(f"Error: module {cliargs.testgen_module!r} not found in the sources ({', '.join(cliargs.src)})")
        sys.exit(2)
    limit = cliargs.testgen_max if cliargs.testgen_max is not None else (None if cliargs.testgen_skeleton else 8)
    cases = plan_cases(target, cliargs.testgen_procedures, limit)
    if not cases:
        wanted = ", ".join(cliargs.testgen_procedures)
        warn(f"Error: module {target.name} has no public procedure to test" + (f" named {wanted}" if wanted else ""))
        sys.exit(2)
    test_dir, source_dir = _testgen_dirs(configuration)
    build_args = []
    if cliargs.fobos:
        build_args += ["--fobos", cliargs.fobos]
    if cliargs.fobos_case_insensitive:
        build_args.append("--fobos-case-insensitive")
    if cliargs.mode:
        build_args += ["--mode", cliargs.mode]
    if not configuration.fobos.fobos:
        for src in cliargs.testgen_src_cli or []:
            build_args += ["--src", src]
    deps_dir = configuration.fobos.get_deps_dir() if configuration.fobos.fobos else ".fobis_deps"
    status(f"Module {target.name} ({os.path.relpath(target.path)}): building the skeleton in a scratch copy...")
    with Sandbox(".", source_dir, build_args, deps_dir, cliargs.testgen_timeout) as sandbox:
        skel, built = checked_skeleton(target, cases, sandbox)
        if built.project_errors:
            warn("Error: the project does not build in the scratch copy:")
            warn("\n".join(built.output.strip().splitlines()[-30:]))
            sys.exit(1)
        if not skel.active:
            warn(f"Error: no public procedure of {target.name} can be called from a generated test:")
            warn("\n".join(render_cases(skel)))
            sys.exit(1)
        if not built.ok and built.error_lines():
            warn("Error: the skeleton does not compile:\n" + "\n".join(built.errors) + "\n\n" + skel.text)
            sys.exit(1)
        if not built.ok:  # no compiler message about the skeleton: the build itself failed
            warn("Error: the build failed in the scratch copy:\n" + "\n".join(built.output.strip().splitlines()[-30:]))
            sys.exit(1)
        bundle = build_bundle(target, skel, example_test(test_dir, target.name))
        if cliargs.testgen_context:
            print(f"=== system prompt ===\n{load_prompt('testgen')}\n=== user message ===\n{bundle.render()}")
            return
        result = None
        if not cliargs.testgen_skeleton:
            from .llm import LLMConfig, LLMError, get_provider
            from .UserConfig import UserConfig

            provider = None
            try:
                provider = get_provider(LLMConfig.from_user_config(UserConfig()), on_status=status)
                result = generate(
                    target, skel, sandbox, provider, bundle, retries=cliargs.testgen_retries, on_status=status
                )
            except LLMError as exc:
                warn(f"Error: no model: {exc} (fobis testgen --skeleton needs none)")
                sys.exit(1)
            finally:
                if provider is not None and hasattr(provider, "close"):
                    provider.close()
    program = skel.text if cliargs.testgen_skeleton else (result.program if result else None)
    written = None
    if program is not None and cliargs.testgen_apply:
        written = cliargs.testgen_output or os.path.join(test_dir, f"{program_name(target.name)}.f90")
        if os.path.exists(written):
            warn(f"Error: {written} exists: not overwritten (choose another path with --output)")
            sys.exit(1)
        os.makedirs(os.path.dirname(written) or ".", exist_ok=True)
        with open(written, "w", encoding="utf-8") as handle:
            handle.write(program)
    if as_json:
        data = {
            "module": target.name,
            "path": os.path.relpath(target.path),
            "tested": [c.label for c in skel.active],
            "skipped": {c.label: c.skipped for c in skel.cases if c.skipped},
            "skeleton": skel.text,
            "accepted": program is not None,
            "program": program,
            "written": written,
        }
        if result is not None:
            data.update(
                attempts=result.attempts,
                notes=result.notes,
                reason=result.reason,
                last=result.last,
                called=result.coverage.called if result.coverage else [],
                checks=result.coverage.checks if result.coverage else 0,
                output=result.output,
            )
        print(json.dumps(data, indent=2))
    else:
        say(f"\nTest of module {target.name}:")
        say("\n".join(render_cases(skel)))
        if cliargs.testgen_skeleton:
            say("\nSkeleton (builds; give the inputs values and add the checks):\n")
        elif result.program is not None:
            cov = result.coverage
            say(
                f"\nAccepted after {result.attempts} attempt(s): builds, runs (exit 0), calls "
                f"{', '.join(cov.called)}; {cov.checks} check(s). Review it before committing."
            )
            if result.notes:
                say(f"Model notes: {result.notes}")
            say("")
        else:
            warn(f"\nNo program accepted after {result.attempts} attempt(s): {result.reason}")
            if result.last:
                say("Last attempt (rejected, not written):\n")
                say(result.last)
            if result.output:
                say("Its output:\n" + "\n".join(result.output.strip().splitlines()[-20:]))
        if program is not None:
            say(program if written is None else f"Written to {written}")
            if written is None:
                say(f"(fobis testgen {target.name} --apply writes it to {test_dir}/)")
    if program is None:
        sys.exit(1)


def run_fobis_review(configuration):
    """
    Run FoBiS in review mode: the lint findings on the changed lines only, and an optional risk summary.

    The change is the staged one (``--staged``), the commits since the merge base with ``--base``, else every
    uncommitted change. The whole project is linted; only findings touching an added or modified line are kept.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    import json

    from .ai.change import WORKTREE
    from .ai.grounding import load_prompt, render_answer, to_json
    from .ai.review import (
        GROUPS,
        ReviewError,
        diff_scope,
        effective_lines,
        in_scope,
        render_markdown,
        review_revision,
        risk_bundle,
        risk_summary,
        scoped_result,
    )
    from .cli.review import REVIEW_FORMATS
    from .lint import render
    from .lint.report import render_json

    cliargs = configuration.cliargs
    if cliargs.lint_format not in REVIEW_FORMATS:
        configuration.print_r(f"Error: unknown format '{cliargs.lint_format}': use one of {', '.join(REVIEW_FORMATS)}")
        sys.exit(1)
    try:
        revision = review_revision(
            cliargs.review_base, cliargs.review_staged, worktree=getattr(cliargs, "review_worktree", False)
        )
    except ReviewError as exc:
        configuration.print_r(f"Error: {exc}")
        sys.exit(1)
    scope = diff_scope(revision)
    changed = list(scope.lines())
    if revision.new != WORKTREE:  # lint reads the working tree: its lines must be those of the reviewed side
        for change in scope.changes:
            path = os.path.join(revision.root, change.path)
            if change.added and os.path.isfile(path):
                with open(path, encoding="utf-8", errors="replace") as handle:
                    if handle.read() != revision.show("new", change.path, _git_text):
                        configuration.print_r(
                            f"Warning: {change.path} has uncommitted changes: its line numbers may not match the review"
                        )
    result = _lint_project(configuration, extra_files=[p for p in changed if os.path.isfile(p)])
    kept = in_scope(result.findings, scope, cliargs.review_context, effective_lines(scope, result))
    scoped = scoped_result(result, kept)
    risk = None
    if cliargs.review_deep and cliargs.lint_format in ("text", "markdown", "json"):
        bundle = risk_bundle(result, scope, scoped.findings)
        if cliargs.review_deep_context:
            print(f"=== system prompt ===\n{load_prompt('review')}\n=== user message ===\n{bundle.render()}")
            return
        from .llm import LLMConfig, LLMError, get_provider
        from .UserConfig import UserConfig

        client = None
        try:
            client = get_provider(
                LLMConfig.from_user_config(UserConfig()), on_status=lambda m: print(m, file=sys.stderr)
            )
            risk = risk_summary(bundle, client)
        except LLMError as exc:
            configuration.print_r(f"Warning: no risk summary: {exc}")
        finally:
            if client is not None and hasattr(client, "close"):
                client.close()
    elif cliargs.review_deep:
        configuration.print_r(f"Warning: --deep adds to the text, markdown and json formats, not {cliargs.lint_format}")
    fmt = cliargs.lint_format
    if fmt == "markdown":
        output = render_markdown(scoped, scope)
        if risk is not None:
            output += "\n\n#### Risk summary [llm]\n\n" + render_answer(risk, groups=GROUPS)
    elif fmt == "json":
        data = json.loads(render_json(scoped))
        data["changed_lines"] = scope.changed_lines
        if risk is not None:
            data["risk"] = to_json(risk)
        output = json.dumps(data, indent=2)
    else:
        output = render(scoped, fmt)
        if fmt == "text":
            output += f"\nReviewed {scope.changed_lines} changed line(s) in {len(changed)} Fortran file(s)."
            if risk is not None:
                output += "\n\nRisk summary [llm]:\n" + render_answer(risk, groups=GROUPS)
    if output:
        print(output)
    failing = [f for f in scoped.findings if f.severity in ("error", "warning")]
    if (failing or result.unreadable) and not cliargs.lint_exit_zero:
        sys.exit(1)


def _git_text(*args):
    """Output of a git command ('' on failure)."""
    import subprocess

    done = subprocess.run(["git", *args], capture_output=True, text=True)
    return done.stdout if done.returncode == 0 else ""


def _lint_project(configuration, extra_files=()):
    """Lint the sources of a lint-like command (``lint``, ``review``): the given paths, else the mode's sources.

    Rule selection merges ``--select``/``--ignore`` with fobos ``[lint]``; ``--compiler-feedback`` is read;
    conditional compilation follows the mode's ``-D`` flags. *extra_files* are linted too (``review``: changed
    files outside the sources). Exits with status 1 on an invalid selection.
    """
    from .analysis import parse_defines
    from .lint import discover_files, lint_files, select_rules

    cliargs = configuration.cliargs
    lint_cfg = configuration.fobos.get_lint_config()
    try:
        rules = select_rules(
            _split_selectors(cliargs.lint_select) or lint_cfg["select"],
            _split_selectors(cliargs.lint_ignore) + lint_cfg["ignore"],
        )
    except ValueError as exc:
        configuration.print_r(f"Error: {exc} (see fobis lint --list-rules)")
        sys.exit(1)
    feedback = None
    if cliargs.lint_compiler_feedback:
        feedback = _read_feedback_log(cliargs.lint_compiler_feedback, cliargs, configuration)
    files = discover_files(
        cliargs.lint_paths or cliargs.src,
        extensions=cliargs.extensions,
        exclude=cliargs.exclude,
        exclude_dirs=cliargs.exclude_dirs,
        recursive=not cliargs.disable_recursive_search,
    )
    known = {os.path.abspath(f) for f in files}
    files += [f for f in extra_files if os.path.abspath(f) not in known]
    return lint_files(
        files,
        rules,
        defines=parse_defines(_merged_preproc_flags(cliargs)),
        openmp=bool(getattr(cliargs, "openmp", False)),
        feedback=feedback,
    )


def _lint_deep(configuration, result):
    """``fobis lint --deep``: review the findings region by region with the LLM.

    Returns the merged `DeepReport` (verdicts left uncertain when no model is available), or None with
    ``--deep-context`` (the bundles were printed instead).
    """
    from .ai.deep import DeepReport, build_bundle, group_findings, review
    from .ai.grounding import load_prompt
    from .llm import LLMConfig, LLMError, get_provider
    from .UserConfig import UserConfig

    cliargs = configuration.cliargs
    groups = group_findings(result)
    chosen = groups[: max(0, cliargs.lint_deep_max)]
    report = DeepReport(groups=len(groups))
    kb = _knowledge_base()
    bundles = [build_bundle(g, result.units, result.project, kb, result.feedback.get(g.path, ())) for g in chosen]
    if cliargs.lint_deep_context:
        print(f"=== system prompt ===\n{load_prompt('deep')}")
        for group, bundle in zip(chosen, bundles, strict=True):
            print(f"=== review of {group.title} in {group.path} ===\n{bundle.render()}")
        if len(groups) > len(chosen):
            print(f"({len(groups) - len(chosen)} more group(s) not shown: raise --deep-max)")
        return None
    if not chosen:
        return report
    client = None
    try:
        cfg = LLMConfig.from_user_config(UserConfig())
        client = get_provider(cfg, on_status=lambda m: print(m, file=sys.stderr))
        for n, (group, bundle) in enumerate(zip(chosen, bundles, strict=True), start=1):
            print(f"[llm] reviewing {n}/{len(chosen)}: {group.title} in {group.path}", file=sys.stderr)
            report.add(review(group, bundle, client))
    except LLMError as exc:
        configuration.print_r(f"Warning: --deep review stopped: {exc}")
    finally:
        if client is not None and hasattr(client, "close"):
            client.close()
    return report


def _lint_ask(configuration, result, ask_at):
    """``fobis lint --ask QUESTION FILE:LINE``: answer a question about the code around that line, with citations."""
    from .ai.deep import ask_region, build_bundle, locate
    from .lint.engine import display_path

    path, line = ask_at
    shown = display_path(path)
    units = result.units.get(shown)
    if units is None:
        configuration.print_r(f"Error: {path} was not linted (check the path, or the mode's sources)")
        sys.exit(1)
    group = locate(units, shown, line)
    group.findings = [
        (i, f) for i, f in enumerate(result.findings) if f.path == shown and group.first <= f.line <= group.last
    ]
    bundle = build_bundle(
        group,
        result.units,
        result.project,
        _knowledge_base(),
        result.feedback.get(shown, ()),
        question=configuration.cliargs.lint_ask,
    )
    _model_explanation(
        configuration,
        bundle,
        "ask",
        ask_region,
        f"{group.title} in {shown}:",
        grouped=False,
        show_context=configuration.cliargs.lint_deep_context,
    )


def _split_selectors(values) -> list[str]:
    """Flatten repeatable, comma-separated rule selectors."""
    return [item for value in values or [] for item in value.replace(",", " ").split()]


def _lint_fixes(findings, write: bool, print_n) -> list:
    """Print (``write=False``) or apply the automatic fixes of *findings*; return the findings left unfixed."""
    import difflib

    from .analysis import read_source
    from .lint import apply_fixes

    by_path: dict[str, list] = {}
    for finding in findings:
        if finding.fixes:
            by_path.setdefault(finding.path, []).append(finding)
    applied_total = 0
    for path, fixable in sorted(by_path.items()):
        text = read_source(path)
        fixed, applied = apply_fixes(text, fixable)
        applied_total += applied
        if write:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(fixed)
        else:
            diff = difflib.unified_diff(
                text.splitlines(keepends=True), fixed.splitlines(keepends=True), f"a/{path}", f"b/{path}"
            )
            print("".join(diff), end="")
    if write:
        print_n(f"{applied_total} fix(es) applied in {len(by_path)} file(s)")
    return [f for f in findings if not (write and f.fixes)]


def _read_feedback_log(path: str, cliargs, configuration) -> str:
    """Text of the compiler-feedback build log *path* ('-' = stdin); exit with a how-to when missing."""
    from .lint.feedback import REPORT_FLAGS

    if path == "-":
        return sys.stdin.read()
    if os.path.isfile(path):
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    compiler = getattr(cliargs, "compiler", "") or ""
    flags = REPORT_FLAGS.get(compiler)
    mode = f" --mode {cliargs.mode}" if getattr(cliargs, "mode", None) else ""
    if flags:
        hint = (
            f'produce it with:\n  fobis build{mode} --cflags "{flags}" --build-dir .fobis/feedback -j 1 --force-compile'
            f" --no-cache 2>&1 | tee {path}"
        )
    else:
        hint = f"compiler '{compiler}' is not supported (supported: nvfortran, gnu)"
    configuration.print_r(f"Error: compiler feedback log '{path}' not found; {hint}")
    sys.exit(1)


def run_fobis_lint(configuration):
    """
    Run FoBiS in lint mode: report bug-prone and obsolescent Fortran constructs.

    Sources are those given on the command line, else the fobos mode's source directories; conditional
    compilation is resolved with the mode's ``-D`` flags. Findings recorded in the baseline file (``--baseline``,
    fobos ``[lint] baseline``, else ``.fobis-lint-baseline.json`` when present) are not reported.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    from .lint import (
        FORMATS,
        RULES,
        BaselineError,
        apply_baseline,
        load_baseline,
        render,
        render_rule_list,
        write_baseline,
    )
    from .lint.report import render_json, render_text

    cliargs = configuration.cliargs
    if cliargs.lint_list_rules:
        print(render_rule_list())
        return
    if cliargs.lint_explain:
        rid = cliargs.lint_explain.strip().upper()
        if rid not in RULES:
            configuration.print_r(f"Error: unknown rule '{cliargs.lint_explain}' (see fobis lint --list-rules)")
            sys.exit(1)
        print(RULES[rid].explain())
        return
    if cliargs.lint_format not in FORMATS:
        configuration.print_r(f"Error: unknown format '{cliargs.lint_format}': use one of {', '.join(FORMATS)}")
        sys.exit(1)
    lint_cfg = configuration.fobos.get_lint_config()

    ask_at = None
    if getattr(cliargs, "lint_ask", None):
        from .ai.deep import parse_location

        located = [parse_location(p) for p in cliargs.lint_paths]
        ask_at = next(((p, n) for p, n in located if n is not None), None)
        if ask_at is None:
            configuration.print_r("Error: --ask needs the code to ask about, as FILE:LINE (e.g. src/flux.F90:120)")
            sys.exit(1)
        cliargs.lint_paths = [p for p, _ in located]

    result = _lint_project(configuration)

    baseline = cliargs.lint_baseline or lint_cfg["baseline"] or DEFAULT_LINT_BASELINE
    if cliargs.lint_update_baseline:
        count = write_baseline(baseline, result.findings)
        configuration.print_b(f"Baseline {baseline}: {count} finding(s) recorded")
        return
    try:
        apply_baseline(result, load_baseline(baseline))
    except BaselineError as exc:
        configuration.print_r(f"Error: {exc}")
        sys.exit(1)

    if cliargs.lint_diff or cliargs.lint_fix:
        result.findings = _lint_fixes(result.findings, write=cliargs.lint_fix, print_n=configuration.print_b)
        if cliargs.lint_diff:
            return

    if ask_at is not None:
        _lint_ask(configuration, result, ask_at)
        return
    notes = tail = reviews = review = None
    if getattr(cliargs, "lint_deep", False):
        if cliargs.lint_format not in ("text", "json"):
            configuration.print_r(f"Warning: --deep annotates the text and json formats, not {cliargs.lint_format}")
        else:
            deep = _lint_deep(configuration, result)
            if deep is None:  # --deep-context: the model's input was printed instead
                return
            from .ai.deep import annotations
            from .ai.deep import to_json as deep_json

            notes, tail = annotations(deep)
            reviews, review = deep_json(deep)
    if notes is not None and cliargs.lint_format == "text":
        output = render_text(result, notes=notes, tail=tail)
    elif reviews is not None:
        output = render_json(result, reviews=reviews, review=review)
    else:
        output = render(result, cliargs.lint_format)
    if output:
        print(output)
    failing = [f for f in result.findings if f.severity in ("error", "warning")]
    if (failing or result.unreadable) and not cliargs.lint_exit_zero:
        sys.exit(1)


def _test_settings(configuration) -> tuple[str, str | None, float]:
    """Test directory, suite and per-test timeout: the command line's, else the fobos ``[test]`` section's
    (``test_dir``, ``suite``, ``timeout``), else ``test``, all suites, 60 s."""
    cliargs = configuration.cliargs
    fobos = configuration.fobos
    config = fobos.get_test_config() if fobos.fobos else {}
    suite = getattr(cliargs, "test_suite", None) or config.get("suite") or None
    timeout = getattr(cliargs, "test_timeout", None)
    return config.get("test_dir", "test"), suite, float(timeout if timeout is not None else config.get("timeout", 60))


def _test_jobs(configuration) -> int:
    """Test programs running at once: ``--jobs``, else ``[test] jobs``, else 1."""
    jobs = getattr(configuration.cliargs, "test_jobs", None)
    if jobs:
        return int(jobs)
    fobos = configuration.fobos
    return int(fobos.get_test_config().get("jobs", 1)) if fobos.fobos else 1


def run_fobis_test(configuration):
    """
    Run FoBiS in test mode: discover, build, and run Fortran test programs.

    Parameters
    ----------
    configuration : FoBiSConfig()
    """
    from .TestRunner import TestRunner, discover_tests, select_tests

    cliargs = configuration.cliargs
    test_dir, suite_filter, timeout = _test_settings(configuration)
    filter_pattern = getattr(cliargs, "test_filter", None)
    no_build = getattr(cliargs, "test_no_build", False)
    list_only = getattr(cliargs, "test_list", False)
    extra_args = getattr(cliargs, "test_extra_args", []) or []
    do_coverage = getattr(cliargs, "test_coverage", False)

    as_json = getattr(cliargs, "json_output", False)
    if not os.path.isdir(test_dir) or not (tests := discover_tests(test_dir)):
        if as_json:
            import json

            print(json.dumps({"status": "none", "test_dir": test_dir, "results": []}, indent=2))
        elif not os.path.isdir(test_dir):
            configuration.print_b(f"No '{test_dir}' directory found. Create it and add Fortran program files.")
        else:
            configuration.print_b(f"No test programs found in '{test_dir}'.")
        return

    if list_only and as_json:
        import json

        print(json.dumps({"status": "listed", "test_dir": test_dir, "tests": tests}, indent=2))
        return
    if list_only:
        configuration.print_b(f"Discovered tests in '{test_dir}':")
        for t in tests:
            suite_tag = f"  [{t['suite']}]" if t.get("suite") else ""
            configuration.print_b(f"  {t['name']:<30} {t['source']}{suite_tag}")
        return

    if as_json:
        _run_fobis_test_json(configuration, tests, test_dir)
        return

    build_dir = getattr(cliargs, "build_dir", "build")
    launcher, ranks = _program_launcher(configuration, "test")
    runner = TestRunner(
        build_dir=build_dir,
        print_n=configuration.print_b,
        print_w=configuration.print_r,
        scheduler=_test_scheduler(configuration),
        launcher=launcher,
        ranks=ranks,
    )

    selected = len(select_tests(tests, suite_filter, filter_pattern))
    configuration.print_b(f"\nBuilding test suite ({selected} target(s))...\n")

    def build_test(test):
        """Build a single test program and return the binary path."""
        src = test["source"]
        out_dir = os.path.join(build_dir, "test")
        os.makedirs(out_dir, exist_ok=True)
        binary = os.path.join(out_dir, test["name"])
        with contextlib.suppress(FileNotFoundError):
            os.remove(binary)  # a build that produces nothing must not leave an older program to run
        # absolute: the builder joins -output to the mode's build_dir, which would prefix it twice
        build_args = ["build", "-target", src, "-output", os.path.abspath(binary), "--dev-deps"]
        mode_val = getattr(cliargs, "mode", None)
        if mode_val:
            build_args += ["-mode", mode_val]
        if getattr(cliargs, "shadow", None):
            build_args += ["--shadow", cliargs.shadow]
        if getattr(cliargs, "quiet", False):
            build_args += ["--quiet"]
        if getattr(cliargs, "explain", False):
            build_args += ["--explain-context" if cliargs.explain_context else "--explain"]
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
        jobs=_test_jobs(configuration),
    )
    configuration.print_b(runner.format_results(suite))
    if getattr(cliargs, "explain", False):
        asked = False
        for result in suite.results:
            if result.passed or result.exit_code == -3:  # -3: the build failed, explained by the build
                continue
            asked |= _explain_crash(
                configuration,
                result.stderr,
                result.exit_code,
                "test",
                mode=getattr(cliargs, "mode", None),
                ask_model=not asked,
                title=f"Explanation of test {result.name} (fobis test --explain)",
            )

    # Optionally run coverage after tests
    if do_coverage:
        run_fobis_coverage(configuration)

    if suite.failed:
        sys.exit(1)


def _run_fobis_test_json(configuration, tests, test_dir):
    """``fobis test --json``: build and run the tests silently, then one JSON object on stdout.

    Each result carries its status (passed, failed, timeout, build-failed, error), exit code, duration and the
    tails of its output; a failed build carries the build's parsed ``diagnostics`` and ``diagnoses`` (see
    ``build --json``), a failed run the parsed ``crash`` and FoBiS's ``notes`` on it (the facts of ``--explain``).
    """
    import contextlib
    import io
    import json

    from .TestRunner import TestRunner

    cliargs = configuration.cliargs
    build_dir = getattr(cliargs, "build_dir", "build")
    mode = getattr(cliargs, "mode", None)
    builds: dict[str, dict] = {}

    def build_test(test):
        binary = os.path.join(build_dir, "test", test["name"])
        os.makedirs(os.path.dirname(binary), exist_ok=True)
        with contextlib.suppress(FileNotFoundError):
            os.remove(binary)  # a build that produces nothing must not leave an older program to run
        args = ["build", "-target", test["source"], "-output", os.path.abspath(binary), "--json", "--dev-deps"]
        if mode:
            args += ["-mode", mode]
        if getattr(cliargs, "shadow", None):
            args += ["--shadow", cliargs.shadow]
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured), contextlib.suppress(SystemExit):
            run_fobis(fake_args=args)
        text = captured.getvalue()
        with contextlib.suppress(ValueError):
            builds[test["name"]] = json.loads(text[text.index("{") :])
        if not os.path.isfile(binary):
            report = builds.setdefault(test["name"], {})
            if report.get("status") != "error":
                report["status"] = "error"
                report.setdefault("errors", []).append(
                    f"{test['source']} was not built: is it among the mode's sources (src)?"
                )
            return None
        return binary

    quiet = io.StringIO()
    launcher, ranks = _program_launcher(configuration, "test")
    runner = TestRunner(
        build_dir=build_dir,
        print_n=lambda *a, **k: None,
        print_w=lambda *a, **k: None,
        scheduler=_test_scheduler(configuration),
        launcher=launcher,
        ranks=ranks,
    )
    with contextlib.redirect_stdout(quiet):
        suite = runner.run_suite(
            tests=tests,
            build_fn=build_test,
            suite_filter=_test_settings(configuration)[1],
            name_filter=getattr(cliargs, "test_filter", None),
            timeout=_test_settings(configuration)[2],
            extra_args=getattr(cliargs, "test_extra_args", []) or [],
            no_build=getattr(cliargs, "test_no_build", False),
            jobs=_test_jobs(configuration),
        )
    context = None
    results = []
    for result in suite.results:
        item = {
            "name": result.name,
            "suite": result.suite,
            "exit_code": result.exit_code,
            "duration": round(result.duration, 3),
            "stdout": "\n".join(result.stdout.splitlines()[-40:]),
            "stderr": "\n".join(result.stderr.splitlines()[-40:]),
        }
        report = builds.get(result.name)
        if result.passed:
            item["status"] = "passed"
        elif result.exit_code == -3 and report is not None and report.get("status") == "error":
            item["status"] = "build-failed"
            item["diagnostics"] = report.get("diagnostics", [])
            item["diagnoses"] = report.get("diagnoses", [])
            if report.get("errors"):
                item["errors"] = report["errors"]
        elif result.exit_code == -1 and result.stderr.startswith("TIMEOUT"):
            item["status"] = "timeout"
        elif result.exit_code in (-2, -3):
            item["status"] = "error"
        else:
            from .ai.crash import classify_crash, parse_crash, scan_context

            item["status"] = "failed"
            crash = parse_crash(result.stderr, result.exit_code)
            if crash is not None:
                with contextlib.redirect_stdout(quiet):
                    context = context or scan_context(
                        configuration.fobos, mode, command="test", shadow=getattr(cliargs, "shadow", None)
                    )
                    notes, _ = classify_crash(crash, context)
                item["crash"] = crash.to_dict()
                item["notes"] = [n.to_dict() for n in notes]
        results.append(item)
    failed = [r for r in results if r["status"] != "passed"]
    data = {
        "status": "error" if failed else "ok",
        "test_dir": test_dir,
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "results": results,
    }
    if suite.wall is not None:  # ran in parallel: the wall-clock time of the run phase
        data["jobs"] = suite.jobs
        data["elapsed"] = round(suite.wall, 3)
    print(json.dumps(data, indent=2))
    if failed:
        sys.exit(1)


INTROSPECT_SECTIONS = (
    "sources",
    "compiler",
    "dependencies",
    "targets",
    "include_dirs",
    "buildoptions",
    "projectinfo",
    "varsets",
    "write",
)


def _introspect_compile_commands(configuration):
    """Print the compilation database ``fobis build`` would write for the same fobos, mode, varset, shadow and
    variant, without compiling: the build's own settings (its namespace, not introspect's) give the same commands."""
    import json

    from .utils import CircularDependency

    cliargs = configuration.cliargs
    others = [name for name in INTROSPECT_SECTIONS if getattr(cliargs, f"introspect_{name}", False)]
    if others:
        configuration.print_r(f"Error: --compile-commands prints the database alone (not with --{others[0]})")
        sys.exit(2)
    args = ["build", "--quiet"]
    for option, value in (("--fobos", cliargs.fobos), ("--mode", cliargs.mode), ("--varset", cliargs.varset)):
        if value:
            args += [option, value]
    if cliargs.fobos_case_insensitive:
        args.append("--fci")
    if getattr(cliargs, "shadow", None):
        args += ["--shadow", cliargs.shadow]
    if getattr(cliargs, "variant", None):
        args += ["--variant", cliargs.variant, "--variant-cflags", cliargs.variant_cflags or ""]
        args += ["--variant-lflags", cliargs.variant_lflags or ""]
    build = FoBiSConfig(fake_args=args)
    build.print_b = lambda *a, **k: None
    build.print_r = configuration.print_r
    builder = Builder(cliargs=build.cliargs, print_n=build.print_b, print_w=build.print_r)
    pfiles = parse_files(configuration=build)
    try:
        dependency_hiearchy(builder=builder, pfiles=pfiles, print_w=build.print_r, force_compile=False)
    except CircularDependency:
        sys.exit(1)
    print(json.dumps(compile_commands.entries(builder, pfiles), indent=2))


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

    if getattr(cliargs, "introspect_compile_commands", False):
        _introspect_compile_commands(configuration)
        return

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

    # Varsets — names, bindings, and the declared default (if any).
    if getattr(cliargs, "introspect_varsets", False):
        data["varsets"] = fobos.get_varsets_info()

    # Compiler info
    if getattr(cliargs, "introspect_compiler", False):
        data["compiler"] = {
            "name": getattr(cliargs, "compiler", "gnu"),
            "binary": getattr(cliargs, "fc", "") or "",
            "cflags": getattr(cliargs, "cflags", "") or "",
            "lflags": getattr(cliargs, "lflags", "") or "",
            "preproc": _merged_preproc_flags(cliargs),
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
            "mode": getattr(cliargs, "mode", "") or getattr(configuration.fobos, "mode", "") or "",
            "build_dir": getattr(cliargs, "build_dir", "./"),
            "obj_dir": getattr(cliargs, "obj_dir", "./obj/"),
            "mod_dir": getattr(cliargs, "mod_dir", "./mod/"),
            "mklib": getattr(cliargs, "mklib", "") or "",
            "jobs": getattr(cliargs, "jobs", 1),
        }
        if getattr(cliargs, "shadow", None):
            data["buildoptions"]["shadow"] = cliargs.shadow

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
        # Python 3.11+ has tomllib but no tomli writer; fallback to JSON
        pass
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
    build_dir = getattr(cliargs, "build_dir", None)
    if build_dir is None and fobos.fobos:  # `fobis test --coverage`: the test namespace has no build_dir
        build_dir = fobos.get(option="build_dir", mode=getattr(cliargs, "mode", None), toprint=False)
    build_dir = build_dir or "./"

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
