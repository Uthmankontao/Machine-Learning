"""
Data Lineage Agent – command-line interface.

Subcommands
-----------
extract
    Scan the repository and write ``lineage/lineage.json``.

query <node>
    Show upstream and/or downstream lineage for a node.

validate
    Check for broken file references, orphan datasets, and staleness.

visualize
    Export the lineage graph as a Graphviz DOT file.

Examples
--------
::

    # Rebuild the lineage graph
    python -m lineage.agent extract

    # Query a specific node (partial name match is supported)
    python -m lineage.agent query MMM_data.xlsx
    python -m lineage.agent query ML_advanced/MMM/main.ipynb --direction downstream

    # Validate the stored graph
    python -m lineage.agent validate

    # Export a DOT graph for rendering with Graphviz
    python -m lineage.agent visualize --output lineage/lineage.dot
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .extractor import RepoScanner
from .schema import LineageGraph
from .validator import LineageValidator, check_stale

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO_ROOT = os.path.dirname(_HERE)
DEFAULT_LINEAGE_FILE = os.path.join(_HERE, "lineage.json")
DEFAULT_DOT_FILE = os.path.join(_HERE, "lineage.dot")


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_extract(args: argparse.Namespace) -> None:
    repo_root = os.path.abspath(args.repo_root)
    output = os.path.abspath(args.output)

    print(f"Scanning repository: {repo_root}")
    scanner = RepoScanner(repo_root)
    graph = scanner.scan()

    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as fh:
        json.dump(graph.to_dict(), fh, indent=2, ensure_ascii=False)

    print(f"Lineage graph written to: {output}")
    print(f"  Nodes : {len(graph.nodes)}")
    print(f"  Edges : {len(graph.edges)}")


def cmd_query(args: argparse.Namespace) -> None:
    graph = _load_graph(args.lineage_file)
    node_id = _resolve_node_id(graph, args.node)

    node = graph.nodes[node_id]
    print(f"Node  : {node_id}")
    print(f"Type  : {node.node_type}")
    print(f"Path  : {node.path}")
    if node.description:
        print(f"Desc  : {node.description}")
    print()

    direction = args.direction

    if direction in ("upstream", "both"):
        upstream = [
            (e.source, e.edge_type, e.context)
            for e in graph.edges
            if e.target == node_id
        ]
        if upstream:
            print(f"Upstream – what produces / reads into '{os.path.basename(node_id)}':")
            for src, etype, ctx in upstream:
                ctx_str = f"  [{ctx}]" if ctx else ""
                print(f"  {src}  --[{etype}]--> {node_id}{ctx_str}")
        else:
            print(f"No upstream sources found for '{node_id}'.")
        print()

    if direction in ("downstream", "both"):
        downstream = [
            (e.target, e.edge_type, e.context)
            for e in graph.edges
            if e.source == node_id
        ]
        if downstream:
            print(f"Downstream – what '{os.path.basename(node_id)}' reads / writes:")
            for tgt, etype, ctx in downstream:
                ctx_str = f"  [{ctx}]" if ctx else ""
                print(f"  {node_id}  --[{etype}]--> {tgt}{ctx_str}")
        else:
            print(f"No downstream targets found for '{node_id}'.")


def cmd_validate(args: argparse.Namespace) -> None:
    lineage_file = os.path.abspath(args.lineage_file)
    repo_root = os.path.abspath(args.repo_root)

    if not os.path.exists(lineage_file):
        print(f"ERROR: lineage file not found: {lineage_file}")
        print("Run 'python -m lineage.agent extract' first.")
        sys.exit(1)

    if check_stale(lineage_file, repo_root):
        print("WARNING: lineage.json may be stale – re-run 'extract' to refresh.\n")

    graph = _load_graph(lineage_file)
    validator = LineageValidator(graph, repo_root)
    issues = validator.validate()

    if not issues:
        print("Validation passed: no issues found.")
        return

    errors = [i for i in issues if i.issue_type == "ERROR"]
    warnings = [i for i in issues if i.issue_type == "WARNING"]

    if errors:
        print(f"ERRORS ({len(errors)}):")
        for issue in errors:
            print(f"  {issue}")

    if warnings:
        print(f"\nWARNINGS ({len(warnings)}):")
        for issue in warnings:
            print(f"  {issue}")

    if errors:
        sys.exit(1)


def cmd_visualize(args: argparse.Namespace) -> None:
    graph = _load_graph(args.lineage_file)
    output = os.path.abspath(args.output)

    _NODE_SHAPES = {
        "dataset":  "cylinder",
        "notebook": "note",
        "script":   "component",
    }

    lines = [
        "digraph lineage {",
        "  rankdir=LR;",
        '  graph [fontname="Helvetica"];',
        '  node  [fontname="Helvetica", style=filled, fillcolor="#f5f5f5"];',
        '  edge  [fontname="Helvetica"];',
    ]

    for node_id, node in graph.nodes.items():
        label = os.path.basename(node_id).replace('"', '\\"')
        tooltip = node_id.replace('"', '\\"').replace("\\", "/")
        shape = _NODE_SHAPES.get(node.node_type, "box")
        safe_id = node_id.replace('"', '\\"').replace("\\", "/")
        lines.append(
            f'  "{safe_id}" [shape={shape}, label="{label}", tooltip="{tooltip}"];'
        )

    for edge in graph.edges:
        src = edge.source.replace('"', '\\"').replace("\\", "/")
        tgt = edge.target.replace('"', '\\"').replace("\\", "/")
        lines.append(f'  "{src}" -> "{tgt}" [label="{edge.edge_type}"];')

    lines.append("}")
    dot_content = "\n".join(lines)

    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    with open(output, "w", encoding="utf-8") as fh:
        fh.write(dot_content)

    print(f"DOT graph written to: {output}")
    print("Render with Graphviz: dot -Tpng lineage/lineage.dot -o lineage/lineage.png")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_graph(lineage_file: str) -> LineageGraph:
    path = os.path.abspath(lineage_file)
    if not os.path.exists(path):
        print(f"ERROR: lineage file not found: {path}")
        print("Run 'python -m lineage.agent extract' first.")
        sys.exit(1)
    with open(path, encoding="utf-8") as fh:
        return LineageGraph.from_dict(json.load(fh))


def _resolve_node_id(graph: LineageGraph, node_ref: str) -> str:
    """Return the canonical node id, resolving partial matches."""
    if node_ref in graph.nodes:
        return node_ref
    # Case-insensitive partial match
    matches = [n for n in graph.nodes if node_ref.lower() in n.lower()]
    if not matches:
        print(f"Node '{node_ref}' not found in the lineage graph.")
        sys.exit(1)
    if len(matches) == 1:
        print(f"Matched node: {matches[0]}\n")
        return matches[0]
    print(f"Ambiguous node '{node_ref}'. Did you mean one of:")
    for m in matches:
        print(f"  {m}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m lineage.agent",
        description="Data Lineage Agent for the Machine-Learning repository.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ---- extract ---------------------------------------------------------
    p_ext = sub.add_parser("extract", help="Scan repo and write lineage.json")
    p_ext.add_argument(
        "--repo-root",
        default=DEFAULT_REPO_ROOT,
        help="Repository root directory (default: auto-detected)",
    )
    p_ext.add_argument(
        "--output",
        default=DEFAULT_LINEAGE_FILE,
        help="Destination path for lineage.json",
    )
    p_ext.set_defaults(func=cmd_extract)

    # ---- query -----------------------------------------------------------
    p_qry = sub.add_parser("query", help="Query lineage for a node")
    p_qry.add_argument(
        "node",
        help="Node id (repo-relative path) or partial name",
    )
    p_qry.add_argument(
        "--direction",
        choices=["upstream", "downstream", "both"],
        default="both",
        help="Traversal direction (default: both)",
    )
    p_qry.add_argument(
        "--lineage-file",
        default=DEFAULT_LINEAGE_FILE,
        help="Path to lineage.json",
    )
    p_qry.set_defaults(func=cmd_query)

    # ---- validate --------------------------------------------------------
    p_val = sub.add_parser("validate", help="Validate the lineage graph")
    p_val.add_argument(
        "--lineage-file",
        default=DEFAULT_LINEAGE_FILE,
        help="Path to lineage.json",
    )
    p_val.add_argument(
        "--repo-root",
        default=DEFAULT_REPO_ROOT,
        help="Repository root (used for file-existence checks)",
    )
    p_val.set_defaults(func=cmd_validate)

    # ---- visualize -------------------------------------------------------
    p_viz = sub.add_parser("visualize", help="Export lineage as a DOT graph")
    p_viz.add_argument(
        "--lineage-file",
        default=DEFAULT_LINEAGE_FILE,
        help="Path to lineage.json",
    )
    p_viz.add_argument(
        "--output",
        default=DEFAULT_DOT_FILE,
        help="Destination path for the .dot file",
    )
    p_viz.set_defaults(func=cmd_visualize)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
