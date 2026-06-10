"""/distill — runs the Distill phase: Gate 2 and Gate 3.

Gate 2 (substantiation): verifies each draft is well-formed, substantiated, and
LINKED, then promotes it to `active`. Running /distill IS the human's act of
authorship/approval. Materializes each draft's proposed links into first-class
edge files. Rebuilds the index.

Gate 3 (generalization): detects Lessons that have recurred across contexts and
proposes promotion to a Pattern. Implemented honestly; it simply does not fire
until a recurrence exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .schemas import SCHEMAS
from . import constraints, validator
from .models import Edge, make_edge_id, now_iso
from .index import build_index


@dataclass
class DistillReport:
    promoted: list = field(default_factory=list)     # node ids draft->active
    blocked: list = field(default_factory=list)      # (node_id, reasons)
    edges_created: list = field(default_factory=list)
    patterns_proposed: list = field(default_factory=list)
    index_path: str | None = None
    build_errors: list = field(default_factory=list)


def _gate2_check(node, nodes_by_id, proposed_links, real_edge_count=0):
    """Substantiation test. Returns (ok, reasons)."""
    reasons = []
    schema = SCHEMAS[node.type]

    missing = [f for f in (schema["required_draft"] + schema["required_active"])
               if not node.fields.get(f)]
    if missing:
        reasons.append(f"FAIL substantiated: missing {missing}")
    else:
        reasons.append("ok substantiated")

    # linked: must have at least one valid (existing-target) edge, real or proposed
    valid_links = [l for l in proposed_links if l.get("to") in nodes_by_id]
    if valid_links or real_edge_count:
        reasons.append(f"ok linked: {len(valid_links)} proposed + "
                       f"{real_edge_count} existing edge(s)")
    else:
        reasons.append("FAIL linked: no edge connects this node to the graph")

    ok = not any(r.startswith("FAIL") for r in reasons)
    return ok, reasons


def edge_counts(edges):
    """How many materialized edges touch each node id."""
    counts = {}
    for e in edges:
        counts[e.from_id] = counts.get(e.from_id, 0) + 1
        counts[e.to_id] = counts.get(e.to_id, 0) + 1
    return counts


def promote_node(store, node, nodes_by_id, real_edge_count=0, source="distill"):
    """Run one draft through Gate 2: check, materialize links, promote.

    The single promotion path shared by distill (batch) and review (per-node).
    Returns (ok, reasons, edges_created). Nothing is written unless every
    proposed link is legal — an illegal edge is a Gate 2 failure, not something
    to promote past.
    """
    ok, reasons = _gate2_check(node, nodes_by_id, node.proposed_links,
                               real_edge_count)
    if not ok:
        return False, reasons, []

    illegal = []
    materializable = []
    for link in node.proposed_links:
        etype, to_id = link.get("type"), link.get("to")
        target = nodes_by_id.get(to_id)
        if target is None:
            continue              # dangling proposal; gate2 already ignored it
        legal, why = constraints.is_legal_edge(etype, node.type, target.type)
        if legal:
            materializable.append((etype, to_id, link, target))
        else:
            illegal.append(f"FAIL edge: {why}")
    if illegal:
        return False, illegal, []

    created = []
    for etype, to_id, link, target in materializable:
        edge = Edge(
            id=make_edge_id(node.id, etype, to_id),
            type=etype, from_id=node.id, to_id=to_id,
            source={"type": source}, note=link.get("note", ""),
        )
        if not store.edge_exists(edge.id):
            store.write_edge(edge)
            created.append(edge.id)
        # a materialized supersession retires the old node
        if etype == "supersedes" and target.status == "active":
            target.status = "superseded"
            target.updated_at = now_iso()
            store.write_node(target)

    node.status = "active"
    node.updated_at = now_iso()
    node.proposed_links = []
    store.write_node(node)
    return True, reasons, created


def distill(store):
    report = DistillReport()

    # build pass first: never promote into an invalid graph
    errors, _ = validator.validate_all(store)
    # only block on errors that aren't "draft is missing active-only fields"
    hard = [e for e in errors if "Gate 2 (active)" not in e.message]
    if hard:
        report.build_errors = [str(e) for e in hard]
        return report

    nodes = store.all_nodes()
    nodes_by_id = {n.id: n for n in nodes}
    drafts = [n for n in nodes if n.status == "draft"]
    real_edge_counts = edge_counts(store.all_edges())

    for node in drafts:
        ok, reasons, created = promote_node(store, node, nodes_by_id,
                                            real_edge_counts.get(node.id, 0))
        if ok:
            report.promoted.append(node.id)
            report.edges_created.extend(created)
        else:
            report.blocked.append((node.id, reasons))

    # Gate 3: recurrence detection across active Lessons
    report.patterns_proposed = _detect_pattern_candidates(store)

    # rebuild the derived index from the now-current files
    report.index_path = build_index(store)
    return report


def _detect_pattern_candidates(store, min_occurrences=2, min_projects=2):
    """Group active Lessons by shared tags; a group spanning >= min_projects is a
    Pattern candidate. Returns human-readable proposals (never auto-promotes)."""
    lessons = [n for n in store.all_nodes()
               if n.type == "lesson" and n.status == "active"]
    by_tag = {}
    for l in lessons:
        for t in l.tags:
            by_tag.setdefault(t, []).append(l)

    proposals = []
    seen = set()
    for tag, group in by_tag.items():
        # only project scopes count toward recurrence-across-contexts; a global
        # lesson is context-free and would inflate the count
        projects = {l.scope for l in group if l.scope.startswith("project:")}
        if len(group) >= min_occurrences and len(projects) >= min_projects:
            key = tuple(sorted(l.id for l in group))
            if key in seen:
                continue
            seen.add(key)
            proposals.append({
                "tag": tag,
                "lessons": [l.id for l in group],
                "projects": sorted(projects),
                "suggestion": f"promote recurring '{tag}' lessons to a global Pattern",
            })
    return proposals