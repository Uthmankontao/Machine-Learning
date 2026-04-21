# Data Lineage Agent

This package provides automated **data lineage tracking** for the
`Machine-Learning` repository.  It scans every Jupyter notebook and
Python script, detects file I/O operations and local module imports, and
builds a persistent directed graph of source-to-target relationships.

---

## Directory layout

```
lineage/
  __init__.py       Public API (LineageNode, LineageEdge, LineageGraph)
  schema.py         Data-class definitions and JSON serialisation
  extractor.py      Repository scanner (pattern matching)
  validator.py      Validation rules
  agent.py          CLI entry point
  lineage.json      ← generated artefact (committed, reviewable in PRs)
  lineage.dot       ← optional Graphviz export
  README.md         This file
```

---

## Quick start

```bash
# Regenerate the lineage graph after changes
python -m lineage.agent extract

# Query what a notebook reads / writes
python -m lineage.agent query "ML_advanced/MMM/main.ipynb"

# Query where a dataset is used
python -m lineage.agent query MMM_data.xlsx

# Validate the stored graph
python -m lineage.agent validate

# Export a DOT graph (render with Graphviz)
python -m lineage.agent visualize
dot -Tpng lineage/lineage.dot -o lineage/lineage.png
```

---

## Subcommand reference

### `extract`

Scans the repository and writes `lineage/lineage.json`.

| Flag | Default | Description |
|------|---------|-------------|
| `--repo-root` | repo root (auto-detected) | Path to scan |
| `--output` | `lineage/lineage.json` | Output path |

```bash
python -m lineage.agent extract
python -m lineage.agent extract --repo-root /path/to/repo --output /tmp/lineage.json
```

---

### `query <node>`

Prints upstream and/or downstream lineage for a node.
A **partial, case-insensitive** match is accepted when the full id is not
provided.

| Flag | Default | Description |
|------|---------|-------------|
| `node` | (required) | Node id or partial name |
| `--direction` | `both` | `upstream`, `downstream`, or `both` |
| `--lineage-file` | `lineage/lineage.json` | Lineage file to read |

```bash
# What does this notebook read?
python -m lineage.agent query "ML_graphs/PART I/TP2_Algorithms/practical.ipynb" --direction downstream

# Where is pandemic_europe.graphml used?
python -m lineage.agent query pandemic_europe.graphml --direction upstream
```

**Interpreting the output**

- **Upstream** – edges where the queried node is the *target* (i.e., something reads/writes *into* this node, or code that produces it).
- **Downstream** – edges where the queried node is the *source* (i.e., what this code reads or writes to).

---

### `validate`

Checks the stored lineage graph for issues.

| Issue type | Severity | Meaning |
|------------|----------|---------|
| `BROKEN_REF` | ERROR | A node's file no longer exists on disk |
| `ORPHAN_DATASET` | WARNING | A dataset has no lineage edges |
| Stale graph | WARNING | `lineage.json` is older than a tracked source file |

```bash
python -m lineage.agent validate
```

Exit code is non-zero when any ERROR is present.

---

### `visualize`

Exports the lineage graph as a [Graphviz](https://graphviz.org/) DOT
file.

| Flag | Default | Description |
|------|---------|-------------|
| `--lineage-file` | `lineage/lineage.json` | Lineage file to read |
| `--output` | `lineage/lineage.dot` | Output DOT file |

```bash
python -m lineage.agent visualize
dot -Tpng lineage/lineage.dot -o lineage/lineage.png
dot -Tsvg lineage/lineage.dot -o lineage/lineage.svg
```

Node shapes: **cylinder** = dataset, **note** = notebook, **component** = script.

---

## Lineage schema (`lineage.json`)

```jsonc
{
  "schema_version": "1.0",
  "generated_at": "<ISO-8601 UTC timestamp>",
  "repo_root": "<absolute path on generating machine>",
  "nodes": {
    "<repo-relative-path>": {
      "id":          "<repo-relative-path>",
      "node_type":   "dataset | notebook | script",
      "path":        "<repo-relative-path>",
      "description": "<human-readable label>"
    }
  },
  "edges": [
    {
      "source":    "<node-id>",
      "target":    "<node-id>",
      "edge_type": "reads | writes | imports",
      "context":   "cell_id=<uuid>  (or empty)"
    }
  ]
}
```

---

## Extending the parser

Open `lineage/extractor.py` and add an entry to **`READ_PATTERNS`** or
**`WRITE_PATTERNS`**:

```python
# Example: detect scipy.io.loadmat("file.mat")
(re.compile(r'scipy\.io\.loadmat\s*\(\s*["\']([^"\']+)["\']'), "reads"),
```

Each entry is a 2-tuple `(compiled_regex, edge_type)`.  The first capture
group must match the file path string literal.

To support a new data-file extension (so that files are auto-registered
as dataset nodes), add the extension to **`DATA_EXTENSIONS`**:

```python
DATA_EXTENSIONS: frozenset = frozenset({
    ".csv", ".xlsx", ...,
    ".mat",   # ← add here
})
```

---

## Limitations and known gaps

| Gap | Reason | Workaround |
|-----|--------|------------|
| `glob.glob(os.path.join(path, "*.json"))` not resolved | The path is a variable, not a string literal | Manually annotate with a comment or refactor to use a literal path |
| `pd.read_csv(var)` not resolved | Path is dynamic | Same as above |
| Notebook magic / shell commands (`!cp …`) | Not parsed | Add a regex to `extractor._extract_edges` |
| Binary / pickle files | Not registered | Add `.pkl`, `.npy`, etc. to `DATA_EXTENSIONS` |
