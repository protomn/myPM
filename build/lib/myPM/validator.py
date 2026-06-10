"""The build/lint pass (docs/architecture/storage.md + relationships.md).

Turns the model's rules into guarantees about the bytes: schema validation,
ID/scope format, edge validity, referential integrity, and acyclicity. Returns
structured errors and warnings; callers decide whether to block.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .schemas import SCHEMAS, STATUSES, CONFIDENCE, ENTITY_TYPES
from . import constraints

ID_RE = re.compile(r"^[a-z]+_[a-z0-9_]+$")
EDGE_ID_RE = re.compile(r"^.+--[a-z_]+--.+$")


@dataclass
class Issue:
    level: str        # "error" | "warning"
    where: str        # node/edge id
    message: str

    def __str__(self):
        return f"[{self.level.upper():7}] {self.where}: {self.message}"


def validate_node(node, store=None):
    issues = []
    if node.type not in ENTITY_TYPES:
        issues.append(Issue("error", node.id, f"unknown type '{node.type}'"))
        return issues
    if not ID_RE.match(node.id):
        issues.append(Issue("error", node.id, "id must match <type>_<slug> (lowercase)"))
    if not node.id.startswith(node.type + "_"):
        issues.append(Issue("error", node.id, f"id prefix must be '{node.type}_'"))
    if node.status not in STATUSES:
        issues.append(Issue("error", node.id, f"invalid status '{node.status}'"))
    if node.confidence not in CONFIDENCE:
        issues.append(Issue("error", node.id, f"invalid confidence '{node.confidence}'"))
    if not (node.scope == "global" or node.scope.startswith("project:")):
        issues.append(Issue("error", node.id, f"invalid scope '{node.scope}'"))

    # scope must match directory location (location is authoritative)
    if store is not None and node.path is not None:
        try:
            loc_scope = store.scope_from_path(node.path)
            if loc_scope != node.scope:
                issues.append(Issue("error", node.id,
                    f"scope '{node.scope}' disagrees with location '{loc_scope}'"))
        except ValueError as e:
            issues.append(Issue("error", node.id, str(e)))

    # schema: gate-aware required fields
    schema = SCHEMAS[node.type]
    required = list(schema["required_draft"])
    if node.status == "active":
        required += list(schema["required_active"])
    for fld in required:
        if not node.fields.get(fld):
            gate = "Gate 2 (active)" if fld in schema["required_active"] else "Gate 1 (draft)"
            issues.append(Issue("error", node.id, f"missing required field '{fld}' for {gate}"))

    # unknown entity fields
    for fld in node.fields:
        if fld not in schema["fields"]:
            issues.append(Issue("warning", node.id, f"unknown field '{fld}' for {node.type}"))
    return issues


def validate_edge(edge, nodes_by_id):
    issues = []
    if not EDGE_ID_RE.match(edge.id):
        issues.append(Issue("error", edge.id, "edge id must be <from>--<type>--<to>"))
    frm = nodes_by_id.get(edge.from_id)
    to = nodes_by_id.get(edge.to_id)
    if frm is None:
        issues.append(Issue("error", edge.id, f"dangling 'from' -> {edge.from_id}"))
    if to is None:
        issues.append(Issue("error", edge.id, f"dangling 'to' -> {edge.to_id}"))
    if frm and to:
        ok, reason = constraints.is_legal_edge(edge.type, frm.type, to.type)
        if not ok:
            issues.append(Issue("error", edge.id, f"illegal edge: {reason}"))
    return issues


def _has_cycle(adj):
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in adj}

    def visit(n):
        color[n] = GRAY
        for m in adj.get(n, ()):
            if color.get(m, WHITE) == GRAY:
                return True
            if color.get(m, WHITE) == WHITE and visit(m):
                return True
        color[n] = BLACK
        return False

    return any(color[n] == WHITE and visit(n) for n in list(adj))


def validate_graph(nodes, edges):
    """Whole-graph checks: acyclicity per edge type."""
    issues = []
    by_type = {}
    for e in edges:
        by_type.setdefault(e.type, []).append(e)

    for etype, elist in by_type.items():
        adj = {}
        for e in elist:
            adj.setdefault(e.from_id, []).append(e.to_id)
            adj.setdefault(e.to_id, adj.get(e.to_id, []))
        if etype in constraints.ACYCLIC_ENFORCED and _has_cycle(adj):
            issues.append(Issue("error", etype, f"'{etype}' graph must be acyclic but contains a cycle"))
        elif etype in constraints.ACYCLIC_WARN and _has_cycle(adj):
            issues.append(Issue("warning", etype, f"'{etype}' contains a cycle (architectural smell; candidate Lesson)"))
    return issues


def validate_all(store):
    """Run the full build pass over the store. Returns (errors, warnings)."""
    nodes = store.all_nodes()
    edges = store.all_edges()
    nodes_by_id = {n.id: n for n in nodes}
    issues = []
    for n in nodes:
        issues += validate_node(n, store)
    for e in edges:
        issues += validate_edge(e, nodes_by_id)
    issues += validate_graph(nodes, edges)
    errors = [i for i in issues if i.level == "error"]
    warnings = [i for i in issues if i.level == "warning"]
    return errors, warnings