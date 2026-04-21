"""
Repository scanner that builds the lineage graph.

Parsing strategy
----------------
- All data files (CSV, XLSX, JSON, GraphML, …) are registered as
  ``dataset`` nodes on the first pass.
- On the second pass every notebook cell and Python script is searched
  with regex patterns that match common file I/O calls:
    - pd.read_csv / pd.read_excel / pd.read_json
    - nx.read_graphml / nx.read_gml
    - json.load(open(...))
    - open(...) / open(..., "w")
    - glob.glob(...)
    - df.to_csv / df.to_excel / df.to_json
  Local module imports are also detected and recorded as ``imports``
  edges.

Extending for new file types
-----------------------------
Add patterns to ``READ_PATTERNS`` or ``WRITE_PATTERNS`` at the top of
this module.  Each entry is a 2-tuple ``(regex, edge_type)`` where
``edge_type`` is ``"reads"`` or ``"writes"``.
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional

from .schema import LineageEdge, LineageGraph, LineageNode

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: File extensions that are treated as raw datasets.
DATA_EXTENSIONS: frozenset = frozenset(
    {".csv", ".xlsx", ".xls", ".json", ".graphml", ".gml", ".txt", ".tsv", ".parquet"}
)

#: Python script extension.
SCRIPT_EXTENSION = ".py"

#: Jupyter notebook extension.
NOTEBOOK_EXTENSION = ".ipynb"

#: Directories that are never scanned.
EXCLUDE_DIRS: frozenset = frozenset(
    {".git", "__pycache__", ".ipynb_checkpoints", "node_modules", ".venv", "venv", "lineage"}
)

#: Individual filenames that are never registered as datasets.
EXCLUDE_FILES: frozenset = frozenset({"lineage.json"})

# Regex patterns that signal a *read* from a file.
# Each entry: (compiled_pattern, edge_type)
READ_PATTERNS = [
    (re.compile(r'pd\.read_csv\s*\(\s*["\']([^"\']+)["\']'), "reads"),
    (re.compile(r'pd\.read_excel\s*\(\s*["\']([^"\']+)["\']'), "reads"),
    (re.compile(r'pd\.read_json\s*\(\s*["\']([^"\']+)["\']'), "reads"),
    (re.compile(r'nx\.read_graphml\s*\(\s*["\']([^"\']+)["\']'), "reads"),
    (re.compile(r'nx\.read_gml\s*\(\s*["\']([^"\']+)["\']'), "reads"),
    (re.compile(r'json\.load\s*\(\s*open\s*\(\s*["\']([^"\']+)["\']'), "reads"),
    # plain open() with no mode, or explicit 'r' / 'rb'.
    # Supported forms: open("f"), open("f", "r"), open("f", "rb").
    # Not matched: open("f", "rt"), open("f", mode="r") – document as known gap.
    (re.compile(r'\bopen\s*\(\s*["\']([^"\']+)["\']\s*(?:,\s*["\']r[b]?["\'])?\s*\)'), "reads"),
    (re.compile(r'glob\.glob\s*\(\s*(?:os\.path\.join\s*\([^)]+,\s*)?["\']([^"\']+)["\']'), "reads"),
]

# Regex patterns that signal a *write* to a file.
WRITE_PATTERNS = [
    (re.compile(r'\.to_csv\s*\(\s*["\']([^"\']+)["\']'), "writes"),
    (re.compile(r'\.to_excel\s*\(\s*["\']([^"\']+)["\']'), "writes"),
    (re.compile(r'\.to_json\s*\(\s*["\']([^"\']+)["\']'), "writes"),
    (re.compile(r'\bopen\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']w[b]?["\']'), "writes"),
]

# Pattern for local-module import detection.
_IMPORT_RE = re.compile(
    r'^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))', re.MULTILINE
)


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

class RepoScanner:
    """Walk a repository and build a :class:`~lineage.schema.LineageGraph`."""

    def __init__(self, repo_root: str) -> None:
        self.repo_root = os.path.abspath(repo_root)
        self.graph = LineageGraph(repo_root=self.repo_root)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self) -> LineageGraph:
        """Full two-pass scan: register datasets, then parse code."""
        self._register_datasets()
        self._parse_code_files()
        return self.graph

    # ------------------------------------------------------------------
    # Pass 1: dataset registration
    # ------------------------------------------------------------------

    def _register_datasets(self) -> None:
        for root, dirs, files in os.walk(self.repo_root):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for fname in files:
                if fname in EXCLUDE_FILES:
                    continue
                ext = os.path.splitext(fname)[1].lower()
                if ext in DATA_EXTENSIONS:
                    fpath = os.path.join(root, fname)
                    rel = os.path.relpath(fpath, self.repo_root)
                    self.graph.add_node(
                        LineageNode(
                            id=rel,
                            node_type="dataset",
                            path=rel,
                            description=f"Data file: {fname}",
                        )
                    )

    # ------------------------------------------------------------------
    # Pass 2: code parsing
    # ------------------------------------------------------------------

    def _parse_code_files(self) -> None:
        for root, dirs, files in os.walk(self.repo_root):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for fname in files:
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, self.repo_root)
                ext = os.path.splitext(fname)[1].lower()
                if ext == NOTEBOOK_EXTENSION:
                    self._parse_notebook(fpath, rel)
                elif ext == SCRIPT_EXTENSION:
                    self._parse_script(fpath, rel)

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _ensure_code_node(self, rel_path: str, node_type: str) -> LineageNode:
        """Register a notebook/script node if not already present."""
        if rel_path not in self.graph.nodes:
            self.graph.add_node(
                LineageNode(
                    id=rel_path,
                    node_type=node_type,
                    path=rel_path,
                    description=f"{node_type.capitalize()}: {os.path.basename(rel_path)}",
                )
            )
        return self.graph.nodes[rel_path]

    def _resolve(self, ref: str, source_dir: str) -> Optional[str]:
        """
        Resolve a string literal from source code to a repo-relative path.

        Tries (in order):
          1. Relative to the source file's directory.
          2. Relative to the repo root.

        Returns ``None`` if the file cannot be found on disk.
        Glob patterns and URLs are returned as-is without existence check.
        """
        if ref.startswith(("http://", "https://")):
            return None
        # Glob patterns – return the pattern itself so callers can skip or record
        if any(c in ref for c in ("*", "?")):
            return None
        # Format/template strings
        if "{" in ref:
            return None

        for base in (source_dir, self.repo_root):
            candidate = os.path.normpath(os.path.join(base, ref))
            if os.path.exists(candidate):
                return os.path.relpath(candidate, self.repo_root)
        return None

    def _extract_edges(
        self, code: str, source_id: str, source_dir: str, context: str = ""
    ) -> None:
        """Parse *code* and record read/write/import edges for *source_id*."""

        # ---- reads -------------------------------------------------------
        for pattern, edge_type in READ_PATTERNS:
            for m in pattern.finditer(code):
                ref = m.group(1)
                resolved = self._resolve(ref, source_dir)
                if resolved is None:
                    continue
                if resolved not in self.graph.nodes:
                    self.graph.add_node(
                        LineageNode(
                            id=resolved,
                            node_type="dataset",
                            path=resolved,
                            description=f"Data file (referenced): {os.path.basename(resolved)}",
                        )
                    )
                self.graph.add_edge(
                    LineageEdge(
                        source=source_id,
                        target=resolved,
                        edge_type=edge_type,
                        context=context,
                    )
                )

        # ---- writes ------------------------------------------------------
        for pattern, edge_type in WRITE_PATTERNS:
            for m in pattern.finditer(code):
                ref = m.group(1)
                # For writes the file may not exist yet; resolve best-effort
                resolved = self._resolve(ref, source_dir)
                target_id = resolved if resolved is not None else ref
                if target_id not in self.graph.nodes:
                    self.graph.add_node(
                        LineageNode(
                            id=target_id,
                            node_type="dataset",
                            path=target_id,
                            description=f"Data file (written): {os.path.basename(target_id)}",
                        )
                    )
                self.graph.add_edge(
                    LineageEdge(
                        source=source_id,
                        target=target_id,
                        edge_type=edge_type,
                        context=context,
                    )
                )

        # ---- local imports -----------------------------------------------
        for m in _IMPORT_RE.finditer(code):
            module_name = m.group(1) or m.group(2)
            if not module_name:
                continue
            # Only track modules that exist as local .py files
            module_rel_path = module_name.replace(".", os.sep) + ".py"
            module_abs = os.path.join(source_dir, module_rel_path)
            if os.path.exists(module_abs):
                module_rel = os.path.relpath(module_abs, self.repo_root)
                self._ensure_code_node(module_rel, "script")
                self.graph.add_edge(
                    LineageEdge(
                        source=source_id,
                        target=module_rel,
                        edge_type="imports",
                        context=context,
                    )
                )

    def _parse_notebook(self, fpath: str, rel_path: str) -> None:
        try:
            with open(fpath, encoding="utf-8") as fh:
                nb = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return

        source_node = self._ensure_code_node(rel_path, "notebook")
        source_dir = os.path.dirname(fpath)

        for cell in nb.get("cells", []):
            if cell.get("cell_type") != "code":
                continue
            cell_id = cell.get("id", "")
            raw = cell.get("source", [])
            code = "".join(raw) if isinstance(raw, list) else raw
            context = f"cell_id={cell_id}" if cell_id else ""
            self._extract_edges(code, source_node.id, source_dir, context)

    def _parse_script(self, fpath: str, rel_path: str) -> None:
        try:
            with open(fpath, encoding="utf-8") as fh:
                code = fh.read()
        except OSError:
            return

        source_node = self._ensure_code_node(rel_path, "script")
        source_dir = os.path.dirname(fpath)
        self._extract_edges(code, source_node.id, source_dir)
