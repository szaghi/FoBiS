"""Package indexes (#209 R1): schema, providers (local directory/file, static HTTP, git), cache, the index graph,
qualified names, the user configuration edits, ``index build`` from seeds, ``search`` and ``info``. Real git
repositories served as ``file://`` remotes and a loopback HTTP server; nothing reaches the internet."""

from __future__ import annotations

import json
import shutil

import pytest

from fobis.registry.index import (
    Index,
    IndexSet,
    Package,
    RegistryError,
    dump_index,
    load_index,
    normalise_source,
    provider_of,
    read_index_text,
)
from fobis.registry.sources import SourceInfo, inspect_tree, probe, scan_modules, sort_versions
from fobis.UserConfig import UserConfig
from tests.registry_helpers import cli, fobis_package, git, isolate, remote, static_server

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git")


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    isolate(monkeypatch, tmp_path)


def _index_text(name, packages, follows=()):
    index = Index(name=name, follows=list(follows))
    for pname, source in packages.items():
        index.packages[pname] = Package(name=pname, source=source)
    return dump_index(index)


# ── schema ───────────────────────────────────────────────────────────────────


def test_schema_round_trip():
    text = (
        'schema = 1\nname = "lab"\nfollows = ["https://example.org/i.toml"]\n\n'
        '[package.penf]\nsource = "https://github.com/szaghi/PENF"\ndescription = "kinds"\n'
        'keywords = ["kinds"]\nprovides = ["PENF", "penf_b_size"]\n'
    )
    index = load_index(text)
    assert index.name == "lab" and index.follows == ["https://example.org/i.toml"]
    assert index.packages["penf"].provides == ["penf", "penf_b_size"]  # module names are case insensitive
    assert load_index(dump_index(index)).to_dict() == index.to_dict()


def test_dotted_package_name_round_trip():
    index = load_index('schema = 1\n\n[package."odbc.f"]\nsource = "https://github.com/x/odbc.f"\n')
    text = dump_index(index)
    assert '[package."odbc.f"]' in text
    assert list(load_index(text).packages) == ["odbc.f"]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('schema = 1\nowner = "x"\n', "unknown key(s) owner"),
        ("schema = 2\n", "newer than this FoBiS reads"),
        ('[package.a]\ndescription = "no source"\n', "'source' (the package URL) is required"),
        ('[package.a]\nsource = "u"\nversion = "1.0"\n', "unknown key(s) version"),
        ('[package."a b"]\nsource = "u"\n', "is not valid"),
        ('[package.a]\nsource = "u"\nprovides = "m"\nmirrors = [1]\n', "mirrors must be a list of strings"),
        ("schema = [\n", "not valid TOML"),
    ],
)
def test_schema_errors(text, message):
    with pytest.raises(RegistryError, match=message.replace("(", r"\(").replace(")", r"\)")):
        load_index(text, origin="x.toml")


def test_index_holds_no_versions_by_design():
    # versions are the source's: an index entry carrying one is refused, not ignored
    with pytest.raises(RegistryError, match="version"):
        load_index('[package.a]\nsource = "u"\nversion = "1.0"\n')


def test_normalised_sources():
    assert normalise_source("https://GitHub.com/szaghi/PENF.git/") == "https://github.com/szaghi/PENF"
    assert normalise_source("/srv/x/") == "/srv/x"


# ── providers ────────────────────────────────────────────────────────────────


def test_providers_by_url(tmp_path):
    (tmp_path / "dir").mkdir()
    (tmp_path / "dir" / "index.toml").write_text("schema = 1\n")
    (tmp_path / "f.toml").write_text("schema = 1\n")
    assert provider_of(str(tmp_path / "dir")) == "dir"
    assert provider_of(f"file://{tmp_path / 'f.toml'}") == "file"
    assert provider_of("https://example.org/fortran/index.toml") == "http"
    assert provider_of("https://github.com/x/fortran-index") == "git"


def test_static_http_index_is_cached(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.toml").write_text(_index_text("vendor", {"blas95": "https://example.org/blas95"}))
    cache = tmp_path / "cache" / "vendor"
    with static_server(site) as base:
        text, provider = read_index_text(f"{base}/index.toml", str(cache))
        assert provider == "http" and "blas95" in text
    # the server is gone: the cache answers
    text, _ = read_index_text(f"{base}/index.toml", str(cache))
    assert "blas95" in text
    assert json.loads((cache / "meta.json").read_text())["provider"] == "http"


def test_git_index(tmp_path):
    url = remote(tmp_path, "idx", {"index.toml": _index_text("lab", {"a": "file:///a"})}, tags=())
    text, provider = read_index_text(url, str(tmp_path / "c" / "lab"))
    assert provider == "git" and load_index(text).packages["a"].source == "file:///a"


def test_git_repository_without_index(tmp_path):
    url = remote(tmp_path, "empty", {"README.md": "x\n"}, tags=())
    with pytest.raises(RegistryError, match=r"no index\.toml"):
        read_index_text(url, str(tmp_path / "c" / "x"))


# ── the index graph ──────────────────────────────────────────────────────────


def _graph(tmp_path):
    """mine -> follows -> lab -> follows -> mine (a cycle); vendor alone. 'json' is in lab and vendor."""
    for name, packages, follows in (
        ("mine", {"penf": "https://h/szaghi/PENF"}, [str(tmp_path / "lab")]),
        ("lab", {"json": "https://h/lab/json", "penf": "https://h/szaghi/PENF.git"}, [str(tmp_path / "mine")]),
        ("vendor", {"json": "https://h/vendor/json-fortran"}, []),
    ):
        (tmp_path / name).mkdir()
        (tmp_path / name / "index.toml").write_text(_index_text(name, packages, follows))
    return [("mine", str(tmp_path / "mine")), ("vendor", str(tmp_path / "vendor"))]


def test_graph_walk_cycle_and_priority(tmp_path):
    indexes = IndexSet(_graph(tmp_path)).load()
    assert [(i.qualifier, i.depth, i.via) for i in indexes.loaded] == [
        ("mine", 0, ""),
        ("vendor", 0, ""),
        ("lab", 1, "mine"),
    ]
    # the same source listed twice (with and without .git) counts once
    assert [p.index for p in indexes.lookup("penf")] == ["mine"]
    assert sorted(p.index for p in indexes.lookup("json")) == ["lab", "vendor"]
    assert [p.source for p in indexes.lookup("vendor:json")] == ["https://h/vendor/json-fortran"]


def test_depth_zero_reads_roots_only(tmp_path):
    indexes = IndexSet(_graph(tmp_path), depth=0).load()
    assert [i.qualifier for i in indexes.loaded] == ["mine", "vendor"]


def test_unreadable_index_is_reported_and_skipped(tmp_path):
    roots = [*_graph(tmp_path), ("gone", str(tmp_path / "nowhere"))]
    indexes = IndexSet(roots).load()
    assert len(indexes.loaded) == 3 and "gone" in indexes.errors[0]


# ── the user configuration ───────────────────────────────────────────────────


def test_set_indexes_keeps_comments(tmp_path):
    path = tmp_path / "config.ini"
    path.write_text("# mine\n[llm]\n# the model\nmodel = coder-7b\n\n[indexes]\n# my own index\nmine = /a\nold = /b\n")
    cfg = UserConfig(path=str(path))
    assert cfg.indexes == [("mine", "/a"), ("old", "/b")]
    cfg.set_indexes([("mine", "/a2"), ("lab", "https://x/index.toml")])
    text = path.read_text()
    assert "# the model\nmodel = coder-7b" in text and "# my own index\nmine = /a2" in text
    assert "old =" not in text and text.rstrip().endswith("lab = https://x/index.toml")
    assert UserConfig(path=str(path)).indexes == [("mine", "/a2"), ("lab", "https://x/index.toml")]


def test_index_cli_add_list_remove(tmp_path):
    graph = _graph(tmp_path)
    config = str(tmp_path / "config.ini")
    code, out = cli("index", "add", "Mine", graph[0][1], "--config", config)
    assert code == 0 and "mine: 1 package(s), dir index" in out
    code, out = cli("index", "add", "mine", graph[1][1], "--config", config)
    assert code == 2 and "already configured" in out
    code, out = cli("index", "add", "bad", str(tmp_path / "nowhere"), "--config", config)
    assert code == 1 and "not found" in out
    code, out = cli("index", "list", "--config", config, "--json")
    assert [r["name"] for r in json.loads(out)["indexes"]] == ["mine"]
    assert cli("index", "remove", "mine", "--config", config)[0] == 0
    assert UserConfig(path=config).indexes == []


def test_project_indexes_come_first(tmp_path, monkeypatch):
    graph = _graph(tmp_path)
    config = str(tmp_path / "config.ini")
    UserConfig(path=config).set_indexes([("vendor", graph[1][1])])
    project = tmp_path / "proj"
    project.mkdir()
    (project / "fobos").write_text("[indexes]\nmine = ../mine\n")  # relative to the fobos
    monkeypatch.chdir(project)
    _, out = cli("index", "list", "--config", config, "--json")
    rows = json.loads(out)["indexes"]
    assert [(r["name"], r["scope"]) for r in rows] == [("mine", "project"), ("vendor", "user")]
    assert rows[0]["url"] == str(tmp_path / "mine")


# ── sources, build, search, info ─────────────────────────────────────────────


def test_versions_sorted_semantically():
    assert sort_versions(["v1.10.0", "v1.9.2", "latest", "2.0.0", "v1.10.0-rc1"]) == (
        ["2.0.0", "v1.10.0", "v1.9.2"],
        ["latest", "v1.10.0-rc1"],
    )


def test_probe_git_source(tmp_path):
    url = remote(
        tmp_path,
        "penf",
        fobis_package("penf", "portable kinds", modules=["penf", "penf_b_size"]),
        tags=("v1.0.0",),
        more={"v1.2.0": {"src/penf_stringify.f90": "Module Penf_Stringify ! later\nend module\n"}},
    )
    info = probe(url)
    assert info.provider == "git" and info.versions == ["v1.2.0", "v1.0.0"] and info.latest == "v1.2.0"
    assert info.name == "penf" and info.backend == "fobis" and info.license == "MIT"
    assert info.description == "portable kinds"
    assert info.modules == ["penf", "penf_b_size", "penf_stringify"]  # the newest version's tree


def test_probe_fpm_source(tmp_path):
    url = remote(
        tmp_path,
        "fpmlib",
        {
            "fpm.toml": 'name = "fpmlib"\ndescription = "an fpm library"\nlicense = "BSD-3-Clause"\n',
            "src/fpmlib.f90": "module fpmlib\nend module fpmlib\n",
        },
    )
    info = probe(url)
    assert (info.backend, info.license, info.description) == ("fpm", "BSD-3-Clause", "an fpm library")


def test_probe_unreadable_source(tmp_path):
    with pytest.raises(RegistryError, match="not a readable git repository"):
        probe(f"file://{tmp_path / 'nowhere'}")


def test_scan_modules_skips_module_procedures(tmp_path):
    (tmp_path / "a.F90").write_text(
        "module A\ninterface\nmodule procedure p\nend interface\ncontains\nmodule function f()\nend function\n"
        "end module A\nsubmodule (a) s\nend submodule\n"
    )
    assert scan_modules(tmp_path) == ["a"]


def test_scan_modules_reads_fypp_templates(tmp_path):
    # stdlib writes its sources as fypp templates: a literal name counts, a templated one cannot be known
    (tmp_path / "s.fypp").write_text("#:include 'common.fypp'\nmodule stdlib_strings\nend module\n")
    (tmp_path / "t.fypp").write_text("module stdlib_blas_${k}$\nend module\n")
    assert scan_modules(tmp_path) == ["stdlib_strings"]


@pytest.mark.parametrize(
    ("readme", "expected"),
    [
        # stdlib: a table of contents before the prose
        ("# stdlib\n\n* [Goals](#goals)\n* [Usage](#usage)\n\nFortran Standard Library\n", "Fortran Standard Library"),
        # HASTY: a navigation line of links only
        ("[What is it?](#what) | [Features](#features)\n\nA hash table.\n", "A hash table."),
        # FEATS: a link definition used as a comment
        ("[This document is formatted with GFM.]:#\n\nTask scheduling.\n", "Task scheduling."),
        (
            "**ForDiff**: a library for `numerical` [differentiation](https://x.org)\n",
            "ForDiff: a library for numerical differentiation",
        ),
        ("1. step one\n+ item\n\nProse.\n", "Prose."),
    ],
)
def test_readme_description_skips_what_is_not_prose(tmp_path, readme, expected):
    (tmp_path / "README.md").write_text(readme)
    assert inspect_tree(str(tmp_path), SourceInfo(url="u", provider="git")).description == expected


def test_manifest_description_repeating_the_name_is_ignored(tmp_path):
    (tmp_path / "fpm.toml").write_text('name = "quaff"\ndescription = "quaff"\n')
    (tmp_path / "README.md").write_text("Quantities for Fortran.\n")
    assert inspect_tree(str(tmp_path), SourceInfo(url="u", provider="git")).description == "Quantities for Fortran."


def test_readme_found_in_any_case(tmp_path):
    (tmp_path / "readme.md").write_text("# x\n\nDislocation dynamics.\n")
    assert inspect_tree(str(tmp_path), SourceInfo(url="u", provider="git")).description == "Dislocation dynamics."


@pytest.mark.parametrize("declared", ["license", "LICENSE", "LICENSE.md", "?", "COPYING"])
def test_manifest_license_naming_no_license_gives_way_to_the_file(tmp_path, declared):
    # fpm new writes license = "license"; some manifests name the file instead of the licence
    (tmp_path / "fpm.toml").write_text(f'name = "x"\nlicense = "{declared}"\n')
    (tmp_path / "LICENSE").write_text("MIT License\n\nPermission is hereby granted, free of charge, to any person\n")
    assert inspect_tree(str(tmp_path), SourceInfo(url="u", provider="git")).license == "MIT"


def test_manifest_license_is_kept_when_it_names_one(tmp_path):
    (tmp_path / "fpm.toml").write_text('name = "x"\nlicense = "BSD-3-Clause"\n')
    (tmp_path / "LICENSE").write_text("MIT License\n\nPermission is hereby granted, free of charge, to any person\n")
    assert inspect_tree(str(tmp_path), SourceInfo(url="u", provider="git")).license == "BSD-3-Clause"


def test_index_build_from_seeds_and_ecosystem(tmp_path):
    penf = remote(tmp_path, "PENF", fobis_package("penf", "portable kinds"))
    flap = remote(tmp_path, "FLAP", fobis_package("flap", "command line arguments parser"))
    seeds = tmp_path / "seeds.toml"
    seeds.write_text(f'name = "szaghi"\n[package.penf]\nsource = "{penf}"\ndescription = "written by hand"\n')
    # an ecosystem with FLAP cloned (its origin is the remote) and a project without remote
    projects = tmp_path / "eco"
    projects.mkdir()
    git(projects, "clone", "-q", flap, "FLAP")
    (projects / "local").mkdir()
    git(projects / "local", "init", "-q")
    config = tmp_path / "config.ini"
    config.write_text(f"[ecosystem]\nroot = {projects}\nprojects = FLAP local\n")
    out_file = tmp_path / "index.toml"
    code, out = cli(
        "index", "build", str(seeds), "--from-ecosystem", "--config", str(config), "-o", str(out_file)
    )  # fmt: skip
    assert code == 0 and "Wrote" in out and "no origin remote" in out
    index = load_index(out_file.read_text())
    assert index.name == "szaghi"
    assert index.packages["penf"].description == "written by hand"  # hand-written fields win
    assert index.packages["penf"].provides == ["penf"] and index.packages["penf"].license == "MIT"
    assert index.packages["flap"].description == "command line arguments parser"
    code, out = cli("index", "build", str(seeds), "-o", str(out_file))
    assert code == 2 and "exists" in out
    code, out = cli("index", "check", str(out_file), "--online", "--json")
    assert code == 0 and json.loads(out)["ok"]


def test_search_and_info_across_two_providers(tmp_path):
    """The R1 exit criterion: search across a git index and a static-file index."""
    penf = remote(tmp_path, "PENF", fobis_package("penf", "portable kinds", modules=["penf", "penf_b_size"]))
    json_lib = remote(tmp_path, "json", fobis_package("jsonf", "JSON for Fortran"))
    mine = remote(
        tmp_path,
        "mine-index",
        {"index.toml": f'name = "mine"\n[package.penf]\nsource = "{penf}"\nprovides = ["penf", "penf_b_size"]\n'},
        tags=(),
    )
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.toml").write_text(
        f'name = "vendor"\n[package.json-fortran]\nsource = "{json_lib}"\ndescription = "JSON for Fortran"\n'
        'keywords = ["json", "io"]\n'
    )
    config = str(tmp_path / "config.ini")
    with static_server(site) as base:
        UserConfig(path=config).set_indexes([("mine", mine), ("vendor", f"{base}/index.toml")])
        code, out = cli("search", "json", "--config", config)
        assert code == 0 and "vendor:json-fortran" in out and "JSON for Fortran" in out
        code, out = cli("search", "--module", "PENF_B_SIZE", "--config", config, "--json")
        assert [p["name"] for p in json.loads(out)["packages"]] == ["penf"]
        code, out = cli("info", "penf", "--config", config, "--json")
        info = json.loads(out)
        assert code == 0 and info["index"] == "mine" and info["versions"] == ["v1.0.0"]
        assert info["modules"] == ["penf", "penf_b_size"] and info["backend"] == "fobis"
        code, out = cli("info", "nothing", "--config", config)
        assert code == 2 and "no package nothing" in out
        code, out = cli("info", json_lib, "--config", config)  # a URL needs no index
        assert code == 0 and "versions  : v1.0.0" in out


def test_ambiguous_name_is_an_error(tmp_path):
    config = str(tmp_path / "config.ini")
    UserConfig(path=config).set_indexes(_graph(tmp_path))
    code, out = cli("info", "json", "--config", config)
    assert code == 2 and "is in 2 indexes" in out and "vendor:json" in out and "lab:json" in out


def test_no_index_configured(tmp_path):
    code, out = cli("search", "x", "--config", str(tmp_path / "none.ini"))
    assert code == 2 and "fobis index add" in out


def test_public_url_of_ssh_remotes():
    from fobis.registry.sources import public_url

    assert public_url("git@github.com:szaghi/PENF.git") == "https://github.com/szaghi/PENF"
    assert public_url("ssh://git@gitlab.com/group/sub/lib.git") == "https://gitlab.com/group/sub/lib"
    assert public_url("https://example.org/x") == "https://example.org/x"


def test_tests_examples_and_vendored_modules_are_not_provided(tmp_path):
    for path in ("src/lib.f90", "src/third_party/other.f90", "tests/t.f90", "examples/e.f90"):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(f"module {path.split('/')[-1][:-4]}_m\nend module\n")
    assert scan_modules(tmp_path) == ["lib_m"]
    assert scan_modules(tmp_path, provided=False) == ["e_m", "lib_m", "other_m", "t_m"]


def test_ecosystem_seeds_are_public_urls_and_unreadable_ones_left_out(tmp_path):
    projects = tmp_path / "eco"
    (projects / "gone").mkdir(parents=True)
    git(projects / "gone", "init", "-q")
    git(projects / "gone", "remote", "add", "origin", f"file://{tmp_path / 'deleted-remote'}")
    config = tmp_path / "config.ini"
    config.write_text(f"[ecosystem]\nroot = {projects}\nprojects = gone\n")
    code, out = cli("index", "build", "--from-ecosystem", "--config", str(config), "-o", str(tmp_path / "i.toml"))
    assert code == 0 and "gone: not publicly readable, left out" in out
    assert load_index((tmp_path / "i.toml").read_text()).packages == {}


def test_fpm_package_provides_its_library_dir_only(tmp_path):
    """Found on urbanjost/M_intrinsics: standalone/ bundles and scratch dirs are not part of an fpm library."""
    from fobis.registry.sources import SourceInfo, inspect_tree

    files = {
        "fpm.toml": 'name = "lib"\n',
        "src/lib.f90": "module lib\nend module lib\n",
        "standalone/bundle.F90": "module m_strings\nend module m_strings\n",
        "scratch/try.f90": "module scratch_m\nend module scratch_m\n",
    }
    for path, text in files.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text)
    assert inspect_tree(str(tmp_path), SourceInfo(url="", provider="git")).modules == ["lib"]
    (tmp_path / "fpm.toml").write_text('name = "lib"\n[library]\nsource-dir = "standalone"\n')
    assert inspect_tree(str(tmp_path), SourceInfo(url="", provider="git")).modules == ["m_strings"]
    (tmp_path / "fpm.toml").write_text('name = "app"\n[library]\nsource-dir = "../outside"\n')
    assert inspect_tree(str(tmp_path), SourceInfo(url="", provider="git")).modules == []
