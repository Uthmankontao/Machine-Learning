"""
Lineage schema: node and edge data classes with JSON serialisation.

Node types
----------
- ``dataset``  : any data file (CSV, XLSX, JSON, GraphML, …)
- ``notebook`` : Jupyter ``.ipynb`` file
- ``script``   : plain Python ``.py`` file

Edge types
----------
- ``reads``   : a code artifact reads a dataset
- ``writes``  : a code artifact writes a dataset
- ``imports`` : a code artifact imports a local module
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, List


@dataclass
class LineageNode:
    """A node in the lineage graph (dataset, notebook, or script)."""

    id: str           # repo-relative path used as stable identifier
    node_type: str    # "dataset" | "notebook" | "script"
    path: str         # repo-relative path (same as id for file nodes)
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LineageEdge:
    """A directed edge between two nodes in the lineage graph."""

    source: str       # source node id
    target: str       # target node id
    edge_type: str    # "reads" | "writes" | "imports"
    context: str = "" # e.g. cell_id=<uuid> or line=<n>

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LineageGraph:
    """Container for the full repository lineage graph."""

    nodes: Dict[str, LineageNode] = field(default_factory=dict)
    edges: List[LineageEdge] = field(default_factory=list)
    generated_at: str = ""
    repo_root: str = ""

    def __post_init__(self) -> None:
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def add_node(self, node: LineageNode) -> None:
        """Register a node (overwrites if same id)."""
        self.nodes[node.id] = node

    def add_edge(self, edge: LineageEdge) -> None:
        """Register an edge, silently dropping exact duplicates."""
        key = (edge.source, edge.target, edge.edge_type)
        for existing in self.edges:
            if (existing.source, existing.target, existing.edge_type) == key:
                return
        self.edges.append(edge)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "schema_version": "1.0",
            "generated_at": self.generated_at,
            "repo_root": self.repo_root,
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LineageGraph":
        graph: LineageGraph = cls.__new__(cls)
        graph.nodes = {}
        graph.edges = []
        graph.generated_at = data.get("generated_at", "")
        graph.repo_root = data.get("repo_root", "")
        for k, v in data.get("nodes", {}).items():
            graph.nodes[k] = LineageNode(**v)
        for e in data.get("edges", []):
            graph.edges.append(LineageEdge(**e))
        return graph
