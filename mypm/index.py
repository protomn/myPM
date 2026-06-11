"""The derived index (docs/architecture/storage.md).

The files are the truth; this is a disposable read-optimization. It is rebuilt
from the files by scanning the tree, holds the node table (with the precomputed
head of each supersession chain), the edge adjacency, and the searchable text,
and is gitignored so it never conflicts. Delete it and rebuild; nothing of value
lives only here.
"""

from __future__ import annotations

import os
import json
import sqlite3


SCHEMA_SQL = """
CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE nodes (
    id          TEXT PRIMARY KEY,
    type        TEXT,
    title       TEXT,
    scope       TEXT,
    status      TEXT,
    head_id     TEXT,            -- living head of this node's supersession chain
    tags        TEXT,            -- json
    source      TEXT,            -- json
    created_at  TEXT,            -- provenance + recency ranking (ranking.py)
    updated_at  TEXT,
    body        TEXT,
    search_text TEXT
);
CREATE TABLE edges (
    id      TEXT PRIMARY KEY,
    type    TEXT,
    from_id TEXT,
    to_id   TEXT
);
CREATE INDEX idx_nodes_scope_status ON nodes(scope, status);
CREATE INDEX idx_edges_from ON edges(from_id);
CREATE INDEX idx_edges_to   ON edges(to_id);
"""


def _resolve_heads(nodes_by_id, edges):
    """For each node, find the living head of its supersession chain.

    Edge supersedes: from=newer, to=older. So 'what replaced X' = edges with
    to==X and type==supersedes; follow .from forward while it stays active.
    """
    replaced_by = {}  # older_id -> [newer_id, ...]
    for e in edges:
        if e.type == "supersedes":
            replaced_by.setdefault(e.to_id, []).append(e.from_id)

    heads = {}
    for nid in nodes_by_id:
        cur = nid
        guard = 0
        while guard < 1000:
            guard += 1
            succ = [s for s in replaced_by.get(cur, [])
                    if nodes_by_id.get(s) and nodes_by_id[s].status == "active"]
            if not succ:
                break
            cur = succ[0]            # linear chain; M:N handled by retriever if needed
        heads[nid] = cur
    return heads


def fingerprint(store) -> str:
    """A cheap content fingerprint over the source files: count + max mtime_ns.

    The files are the database of record and are hand-editable; the index must
    notice when they change. One os.stat sweep — milliseconds at this scale."""
    import glob as _glob
    paths = list(store.iter_node_paths())
    paths += _glob.glob(os.path.join(store.edges_dir, "*.yml"))
    latest = 0
    for p in paths:
        try:
            mt = os.stat(p).st_mtime_ns
        except OSError:
            continue
        if mt > latest:
            latest = mt
    return f"{len(paths)}:{latest}"


def build_index(store) -> str:
    nodes = store.all_nodes()
    edges = store.all_edges()
    nodes_by_id = {n.id: n for n in nodes}
    heads = _resolve_heads(nodes_by_id, edges)

    os.makedirs(os.path.dirname(store.index_path), exist_ok=True)
    if os.path.exists(store.index_path):
        os.remove(store.index_path)

    con = sqlite3.connect(store.index_path)
    con.executescript(SCHEMA_SQL)
    con.execute("INSERT INTO meta VALUES ('fingerprint', ?)", (fingerprint(store),))
    con.executemany(
        "INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [(n.id, n.type, n.title, n.scope, n.status, heads.get(n.id, n.id),
          json.dumps(n.tags), json.dumps(n.source), n.created_at, n.updated_at,
          n.body, n.search_text())
         for n in nodes],
    )
    con.executemany(
        "INSERT INTO edges VALUES (?,?,?,?)",
        [(e.id, e.type, e.from_id, e.to_id) for e in edges],
    )
    con.commit()
    con.close()
    return store.index_path


class IndexReader:
    def __init__(self, store):
        self.store = store
        if not os.path.exists(store.index_path) or self._stale(store):
            build_index(store)
        self.con = sqlite3.connect(store.index_path)
        self.con.row_factory = sqlite3.Row

    @staticmethod
    def _stale(store) -> bool:
        """True when the source files changed since the index was built (or the
        index predates the meta table). Never raises — a broken index is just a
        stale one."""
        try:
            con = sqlite3.connect(store.index_path)
            row = con.execute(
                "SELECT value FROM meta WHERE key='fingerprint'").fetchone()
            con.close()
        except sqlite3.Error:
            return True
        return row is None or row[0] != fingerprint(store)

    def candidates(self, scopes, status="active", type_in=None):
        q = "SELECT * FROM nodes WHERE status = ? AND scope IN (%s)" % \
            ",".join("?" * len(scopes))
        args = [status, *scopes]
        if type_in:
            q += " AND type IN (%s)" % ",".join("?" * len(type_in))
            args += list(type_in)
        return [dict(r) for r in self.con.execute(q, args)]

    def get_node(self, node_id):
        r = self.con.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
        return dict(r) if r else None

    def out_edges(self, node_id):
        return [dict(r) for r in self.con.execute(
            "SELECT * FROM edges WHERE from_id = ?", (node_id,))]

    def in_edges(self, node_id):
        return [dict(r) for r in self.con.execute(
            "SELECT * FROM edges WHERE to_id = ?", (node_id,))]

    def degree(self, node_id):
        return self.con.execute(
            "SELECT COUNT(*) FROM edges WHERE from_id=? OR to_id=?",
            (node_id, node_id)).fetchone()[0]

    def degrees(self):
        """Every node's edge degree in one pass: {node_id: degree}."""
        out = {}
        for nid, n in self.con.execute(
                "SELECT id, COUNT(*) FROM ("
                "  SELECT from_id AS id FROM edges"
                "  UNION ALL SELECT to_id AS id FROM edges) GROUP BY id"):
            out[nid] = n
        return out

    def scopes(self):
        """Every distinct scope present in the graph."""
        return [r[0] for r in self.con.execute(
            "SELECT DISTINCT scope FROM nodes")]

    def close(self):
        self.con.close()


class CombinedIndex:
    """Read-only union of a local root and the shared global root
    (MYPM_GLOBAL_ROOT). The secondary contributes ONLY its global-scope nodes:
    other repositories' project scopes must never leak into this repo's
    recall. On id collision the local root wins — your repo's reading of a
    fact beats the commons'. Edges are unioned; cross-root edges do not exist
    by construction (each root's edge files reference its own nodes)."""

    def __init__(self, primary: IndexReader, secondary: IndexReader):
        self.primary = primary
        self.secondary = secondary

    def candidates(self, scopes, status="active", type_in=None):
        rows = self.primary.candidates(scopes, status=status, type_in=type_in)
        if "global" not in scopes:
            return rows
        seen = {r["id"] for r in rows}
        rows += [r for r in
                 self.secondary.candidates(["global"], status=status,
                                           type_in=type_in)
                 if r["id"] not in seen]
        return rows

    def get_node(self, node_id):
        return self.primary.get_node(node_id) or self.secondary.get_node(node_id)

    def out_edges(self, node_id):
        return self.primary.out_edges(node_id) + self.secondary.out_edges(node_id)

    def in_edges(self, node_id):
        return self.primary.in_edges(node_id) + self.secondary.in_edges(node_id)

    def degree(self, node_id):
        return self.primary.degree(node_id) + self.secondary.degree(node_id)

    def degrees(self):
        out = dict(self.secondary.degrees())
        out.update(self.primary.degrees())
        return out

    def scopes(self):
        return sorted(set(self.primary.scopes()) | {"global"})

    def close(self):
        self.primary.close()
        self.secondary.close()