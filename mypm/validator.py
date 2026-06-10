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

# Two same-type nodes whose content token sets overlap by at least this much are
# flagged as near-duplicates. Tuned to catch restatements without firing on two
# nodes that merely share a domain vocabulary.
DUP_SIMILARITY = 0.6

_DUP_STOP = set("the a an is are was were be to of in on at for and or with this "
                "that it its as from by we i you they our not no but if then so".split())


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

    # unknown entity fields + declared-type mismatches (the schemas carry python
    # types — str/list/bool — so a string where a list belongs is caught here;
    # warning level because legacy graphs may predate the check)
    for fld, val in node.fields.items():
        if fld not in schema["fields"]:
            issues.append(Issue("warning", node.id, f"unknown field '{fld}' for {node.type}"))
        elif val is not None and not isinstance(val, schema["fields"][fld]):
            issues.append(Issue("warning", node.id,
                f"field '{fld}' should be {schema['fields'][fld].__name__}, "
                f"got {type(val).__name__}"))
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


def _content_tokens(node):
    """Stopword-stripped token set over a node's title, body, and field values —
    the surface a near-duplicate would restate."""
    text = " ".join([node.title, node.body,
                     *(str(v) for v in node.fields.values())])
    return {w for w in re.findall(r"[a-z0-9]+", text.lower())
            if w not in _DUP_STOP and len(w) > 2}


def validate_duplicates(nodes):
    """Warn on near-duplicate live nodes of the same type (Jaccard token overlap).

    Gate 1 already blocks exact id collisions; this catches the harder case of
    the same finding restated as a second node, which Recall would surface twice.
    A duplicate is a warning, not an error: the fix is human judgment — supersede,
    link with relates_to, or let one evaporate — not a build failure.
    """
    issues = []
    live = [n for n in nodes if n.status in ("draft", "active")]
    by_type = {}
    for n in live:
        by_type.setdefault(n.type, []).append((n, _content_tokens(n)))
    for items in by_type.values():
        for i in range(len(items)):
            ni, ti = items[i]
            if not ti:
                continue
            for nj, tj in items[i + 1:]:
                if not tj:
                    continue
                jac = len(ti & tj) / len(ti | tj)
                if jac >= DUP_SIMILARITY:
                    issues.append(Issue("warning", ni.id,
                        f"near-duplicate of {nj.id} ({jac:.0%} content overlap); "
                        f"supersede, link via relates_to, or let one evaporate"))
    return issues


def validate_scope_drift(nodes, edges, nodes_by_id):
    """Warn when scope and content disagree (docs/architecture/core-model.md).

    Two drift shapes:
      - a cross-project edge — project-scoped knowledge reaching into another
        project's private scope, which Recall (scoped to one project + global)
        can never traverse anyway;
      - a global node that names a specific project — knowledge filed as
        universal that reads as belonging to one context.
    """
    issues = []
    project_ids = {n.scope.split(":", 1)[1]
                   for n in nodes if n.scope.startswith("project:")}

    for e in edges:
        frm, to = nodes_by_id.get(e.from_id), nodes_by_id.get(e.to_id)
        if not (frm and to):
            continue
        if (frm.scope.startswith("project:") and to.scope.startswith("project:")
                and frm.scope != to.scope):
            issues.append(Issue("warning", e.id,
                f"cross-project edge {frm.scope} -> {to.scope}; project-scoped "
                f"knowledge should connect within a project or promote to global"))

    for n in nodes:
        if n.scope != "global":
            continue
        hay = n.search_text().lower()
        for pid in project_ids:
            if pid in hay or pid.replace("_", " ") in hay:
                issues.append(Issue("warning", n.id,
                    f"global node names project '{pid}'; consider scoping it to "
                    f"project:{pid} or removing the project-specific reference"))
                break
    return issues


def validate_all(store):
    """Run the full build pass over the store. Returns (errors, warnings).

    A malformed file is reported as an error on that file, never a crash of the
    whole pass — the files are hand-editable, so the build must survive a typo."""
    nodes, edges, issues = [], [], []
    for p in store.iter_node_paths():
        try:
            nodes.append(store.load_node(p))
        except Exception as e:
            issues.append(Issue("error", p, str(e)))
    import glob as _glob, os as _os
    for p in _glob.glob(_os.path.join(store.edges_dir, "*.yml")):
        try:
            edges.append(store.load_edge(p))
        except Exception as e:
            issues.append(Issue("error", p, f"unparseable edge file: {e}"))
    nodes_by_id = {n.id: n for n in nodes}
    for n in nodes:
        issues += validate_node(n, store)
    for e in edges:
        issues += validate_edge(e, nodes_by_id)
    issues += validate_graph(nodes, edges)
    issues += validate_duplicates(nodes)
    issues += validate_scope_drift(nodes, edges, nodes_by_id)
    errors = [i for i in issues if i.level == "error"]
    warnings = [i for i in issues if i.level == "warning"]
    return errors, warnings