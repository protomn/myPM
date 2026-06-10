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
CREATE TABLE nodes (
    id          TEXT PRIMARY KEY,
    type        TEXT,
    title       TEXT,
    scope       TEXT,
    status      TEXT,
    head_id     TEXT,            -- living head of this node's supersession chain
    tags        TEXT,            -- json
    source      TEXT,            -- json
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
    con.executemany(
        "INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(n.id, n.type, n.title, n.scope, n.status, heads.get(n.id, n.id),
          json.dumps(n.tags), json.dumps(n.source), n.body, n.search_text())
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
        if not os.path.exists(store.index_path):
            build_index(store)
        self.con = sqlite3.connect(store.index_path)
        self.con.row_factory = sqlite3.Row

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

    def close(self):
        self.con.close()