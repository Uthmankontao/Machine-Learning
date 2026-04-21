"""
Lineage validation checks.

Checks performed
----------------
BROKEN_REF
    A node whose ``path`` no longer exists on disk.

ORPHAN_DATASET
    A dataset node that is not referenced by any edge (neither read
    nor written), indicating it may be undocumented or stale.

Staleness
---------
:func:`check_stale` compares the modification time of ``lineage.json``
against every tracked source file and returns ``True`` when the graph
may be out of date.
"""

from __future__ import annotations

import os
from typing import List

from .schema import LineageGraph

#: Directories ignored during staleness checks.
_IGNORE_DIRS = frozenset({".git", "__pycache__", ".ipynb_checkpoints"})


class ValidationIssue:
    """A single validation finding."""

    def __init__(self, issue_type: str, code: str, node_id: str = "") -> None:
        self.issue_type = issue_type  # "ERROR" or "WARNING"
        self.code = code              # short code, e.g. "BROKEN_REF"
        self.node_id = node_id

    def __str__(self) -> str:
        prefix = f"[{self.issue_type}] "
        if self.node_id:
            return f"{prefix}{self.node_id}: {self.code}"
        return f"{prefix}{self.code}"


class LineageValidator:
    """Run validation rules against a :class:`~lineage.schema.LineageGraph`."""

    def __init__(self, graph: LineageGraph, repo_root: str) -> None:
        self.graph = graph
        self.repo_root = os.path.abspath(repo_root)

    def validate(self) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        issues.extend(self._check_broken_refs())
        issues.extend(self._check_orphan_datasets())
        return issues

    # ------------------------------------------------------------------
    # Rules
    # ------------------------------------------------------------------

    def _check_broken_refs(self) -> List[ValidationIssue]:
        """Every file-backed node must still exist on disk."""
        issues = []
        for node_id, node in self.graph.nodes.items():
            if node.node_type in ("dataset", "notebook", "script"):
                abs_path = os.path.join(self.repo_root, node.path)
                if not os.path.exists(abs_path):
                    issues.append(
                        ValidationIssue(
                            "ERROR",
                            f"BROKEN_REF – file not found: {abs_path}",
                            node_id,
                        )
                    )
        return issues

    def _check_orphan_datasets(self) -> List[ValidationIssue]:
        """Dataset nodes that appear in no edge are flagged as orphans."""
        issues = []
        referenced: set = set()
        for edge in self.graph.edges:
            referenced.add(edge.source)
            referenced.add(edge.target)
        for node_id, node in self.graph.nodes.items():
            if node.node_type == "dataset" and node_id not in referenced:
                issues.append(
                    ValidationIssue(
                        "WARNING",
                        "ORPHAN_DATASET – not referenced by any tracked code",
                        node_id,
                    )
                )
        return issues


def check_stale(lineage_file: str, repo_root: str) -> bool:
    """
    Return ``True`` when *lineage_file* is older than any source file
    under *repo_root*, meaning the graph may need to be regenerated.
    """
    if not os.path.exists(lineage_file):
        return True
    lineage_mtime = os.path.getmtime(lineage_file)
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
        for fname in files:
            if fname == "lineage.json":
                continue
            fpath = os.path.join(root, fname)
            if os.path.getmtime(fpath) > lineage_mtime:
                return True
    return False
