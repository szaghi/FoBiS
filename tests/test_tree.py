"""Tests for fobis tree — inter-project dependency tree rendering (issue #167)."""

from __future__ import annotations

import os
import tempfile

from fobis.Fobos import DepNode, render_tree

# ── render_tree() unit tests ─────────────────────────────────────────────────


def test_render_tree_single_node_fetched():
    node = DepNode(name="PENF", spec="tag=v1.5.0", fetched=True, has_fobos=True)
    output = render_tree([node])
    assert "PENF" in output
    assert "tag=v1.5.0" in output
    # No annotations for a fully-present dep
    assert "[not fetched" not in output
    assert "[no fobos" not in output


def test_render_tree_not_fetched_annotation():
    node = DepNode(name="FLAP", spec="", fetched=False, has_fobos=False)
    output = render_tree([node])
    assert "[not fetched" in output


def test_render_tree_no_fobos_annotation():
    node = DepNode(name="stdlib", spec="", fetched=True, has_fobos=False)
    output = render_tree([node])
    assert "[no fobos" in output


def test_render_tree_duplicate_annotation():
    node = DepNode(name="PENF", spec="", fetched=True, has_fobos=True, duplicate=True)
    output = render_tree([node])
    assert "(*)" in output
    assert "[already shown]" in output


def test_render_tree_version_shown():
    node = DepNode(name="PENF", spec="", fetched=True, has_fobos=True, version="v1.5.0")
    output = render_tree([node])
    assert "v1.5.0" in output


def test_render_tree_two_nodes_connectors():
    nodes = [
        DepNode(name="A", spec="", fetched=True, has_fobos=True),
        DepNode(name="B", spec="", fetched=True, has_fobos=True),
    ]
    output = render_tree(nodes)
    assert "├──" in output  # A uses non-last connector
    assert "└──" in output  # B uses last connector


def test_render_tree_single_node_last_connector():
    nodes = [DepNode(name="A", spec="", fetched=True, has_fobos=True)]
    output = render_tree(nodes)
    assert "└──" in output


def test_render_tree_two_levels():
    child = DepNode(name="Child", spec="", fetched=True, has_fobos=True)
    parent = DepNode(name="Parent", spec="", fetched=True, has_fobos=True, children=[child])
    output = render_tree([parent])
    assert "Parent" in output
    assert "Child" in output
    # Child should be indented relative to parent
    lines = output.splitlines()
    parent_line = next(l for l in lines if "Parent" in l)
    child_line = next(l for l in lines if "Child" in l)
    assert len(child_line) > len(parent_line)


def test_render_tree_formatting_snapshot():
    """Snapshot test: known DepNode structure → exact expected output."""
    root = DepNode(name="root", spec="tag=v1.0", fetched=True, has_fobos=True)
    child_a = DepNode(name="depA", spec="branch=main", fetched=True, has_fobos=True)
    child_b = DepNode(name="depB", spec="", fetched=False, has_fobos=False)
    root.children = [child_a, child_b]

    output = render_tree([root])
    assert "└── root" in output
    assert "depA" in output
    assert "depB" in output
    assert "[not fetched" in output


def test_render_tree_depth_limit_respected():
    """Duplicate flag stops children from being rendered."""
    grandchild = DepNode(name="GC", spec="", fetched=True, has_fobos=True)
    child = DepNode(name="Child", spec="", fetched=True, has_fobos=True, duplicate=True, children=[grandchild])
    parent = DepNode(name="Parent", spec="", fetched=True, has_fobos=True, children=[child])
    output = render_tree([parent])
    # Grandchild must not appear because child is marked duplicate
    assert "GC" not in output


def test_render_tree_empty_list():
    output = render_tree([])
    assert output == ""


# ── Fobos.get_dep_tree() integration ────────────────────────────────────────


def test_dep_tree_no_deps():
    """fobos with empty [dependencies] section → tree with only root line."""
    with tempfile.TemporaryDirectory() as root:
        fobos_path = os.path.join(root, "fobos")
        with open(fobos_path, "w") as f:
            f.write("[default]\ncompiler=Gnu\n\n[dependencies]\n")
        import argparse

        from fobis.Fobos import Fobos

        cliargs = argparse.Namespace(
            fobos=fobos_path,
            fobos_case_insensitive=False,
            mode=None,
            which="build",
        )
        fobos = Fobos(cliargs=cliargs)
        nodes = fobos.get_dep_tree(deps_dir=root)
        assert nodes == []


def test_dep_tree_dep_not_fetched():
    """Dependency directory absent → DepNode with fetched=False."""
    with tempfile.TemporaryDirectory() as root:
        fobos_path = os.path.join(root, "fobos")
        with open(fobos_path, "w") as f:
            f.write("[default]\ncompiler=Gnu\n\n[dependencies]\nPENF = https://github.com/szaghi/PENF :: tag=v1.5.0\n")
        import argparse

        from fobis.Fobos import Fobos

        cliargs = argparse.Namespace(
            fobos=fobos_path,
            fobos_case_insensitive=False,
            mode=None,
            which="build",
        )
        fobos = Fobos(cliargs=cliargs)
        nodes = fobos.get_dep_tree(deps_dir=os.path.join(root, ".fobis_deps"))
        assert len(nodes) == 1
        assert nodes[0].name == "PENF"
        assert nodes[0].fetched is False


def test_dep_tree_dep_fetched_no_fobos():
    """Dependency directory present but no fobos file → has_fobos=False."""
    with tempfile.TemporaryDirectory() as root:
        deps_dir = os.path.join(root, ".fobis_deps")
        dep_dir = os.path.join(deps_dir, "PENF")
        os.makedirs(dep_dir)
        fobos_path = os.path.join(root, "fobos")
        with open(fobos_path, "w") as f:
            f.write("[default]\ncompiler=Gnu\n\n[dependencies]\nPENF = https://github.com/szaghi/PENF :: tag=v1.5.0\n")
        import argparse

        from fobis.Fobos import Fobos

        cliargs = argparse.Namespace(
            fobos=fobos_path,
            fobos_case_insensitive=False,
            mode=None,
            which="build",
        )
        fobos = Fobos(cliargs=cliargs)
        nodes = fobos.get_dep_tree(deps_dir=deps_dir)
        assert len(nodes) == 1
        assert nodes[0].fetched is True
        assert nodes[0].has_fobos is False
