"""mypm review — the approval surface.

The gates are deliberately strict: Gate 2 demands substantiation (root_cause,
alternatives, consequences) and a graph link before a draft becomes recallable.
Extraction can never supply those honestly — a human can, in seconds, IF the
tool asks for exactly what's missing and nothing else. That is this module.

Verbs (all per-node, unlike distill's batch):

    pending    what drafts exist and what each one still needs
    approve    fill the missing fields, then promote through the shared
               Gate-2 path (distill.promote_node) — same gate, zero bypass
    reject     delete the draft (it never earned a place in the graph)
    merge      fold a draft into an existing node — the restatement case
    supersede  wire draft--supersedes-->old, retire the old node, promote

Nothing here weakens a gate. Approve runs the identical promotion code distill
runs; review just closes the human gap that batch distill cannot.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# note: `from . import distill` would resolve to the distill FUNCTION, which
# __init__.py re-exports under the same name — import the module explicitly.
from .distill import promote_node, edge_counts, _gate2_check
from .schemas import SCHEMAS
from .index import build_index
from .models import now_iso


@dataclass
class PendingDraft:
    node_id: str
    type: str
    title: str
    missing_fields: list = field(default_factory=list)
    linked: bool = False
    reasons: list = field(default_factory=list)
    path: str | None = None


def pending(store):
    """Every draft with what Gate 2 still demands of it, in stable order."""
    nodes = store.all_nodes()
    nodes_by_id = {n.id: n for n in nodes}
    counts = edge_counts(store.all_edges())
    out = []
    for n in sorted((n for n in nodes if n.status == "draft"), key=lambda n: n.id):
        schema = SCHEMAS[n.type]
        missing = [f for f in (schema["required_draft"] + schema["required_active"])
                   if not n.fields.get(f)]
        valid_links = [l for l in n.proposed_links if l.get("to") in nodes_by_id]
        linked = bool(valid_links) or counts.get(n.id, 0) > 0
        _, reasons = _gate2_check(n, nodes_by_id, n.proposed_links,
                                           counts.get(n.id, 0))
        out.append(PendingDraft(n.id, n.type, n.title, missing, linked,
                                reasons, n.path))
    return out


def _coerce(node_type, fname, value):
    """CLI values arrive as strings; list-typed fields split on ';'."""
    want = SCHEMAS[node_type]["fields"].get(fname)
    if want is list and isinstance(value, str):
        return [v.strip() for v in value.split(";") if v.strip()]
    return value


def _get_draft(store, node_id):
    node = store.nodes_by_id().get(node_id)
    if node is None:
        raise ValueError(f"no node '{node_id}'")
    if node.status != "draft":
        raise ValueError(f"'{node_id}' is {node.status}, not a draft")
    return node


def approve(store, node_id, fields=None, links=None, reindex=True):
    """Fill in the supplied fields/links, then promote through the shared Gate-2
    path. Returns (ok, reasons, edges_created); on failure nothing is promoted
    but supplied fields ARE saved, so progress is never lost."""
    node = _get_draft(store, node_id)
    for k, v in (fields or {}).items():
        node.fields[k] = _coerce(node.type, k, v)
    for link in (links or []):
        if link not in node.proposed_links:
            node.proposed_links.append(link)
    if fields or links:
        node.updated_at = now_iso()
        store.write_node(node)

    nodes_by_id = store.nodes_by_id()
    counts = edge_counts(store.all_edges())
    ok, reasons, created = promote_node(
        store, nodes_by_id[node_id], nodes_by_id,
        counts.get(node_id, 0), source="review")
    if ok and reindex:
        build_index(store)
    return ok, reasons, created


def reject(store, node_id, reindex=True):
    """Delete the draft. Returns the removed path."""
    import os
    node = _get_draft(store, node_id)
    path = node.path
    os.remove(path)
    if reindex:
        build_index(store)
    return path


def merge(store, node_id, into_id, reindex=True):
    """Fold a draft into an existing node: body appended with provenance, tags
    unioned, empty target fields filled from the draft. The draft is removed.
    This is the restatement case — same knowledge, second wording."""
    import os
    node = _get_draft(store, node_id)
    target = store.nodes_by_id().get(into_id)
    if target is None:
        raise ValueError(f"merge target '{into_id}' does not exist")
    if target.type != node.type:
        raise ValueError(f"cannot merge a {node.type} into a {target.type}; "
                         f"types must match")

    if node.body.strip():
        target.body = (target.body.rstrip() +
                       f"\n\n---\n\n{node.body.strip()}\n\n"
                       f"_Merged from draft `{node.id}` ({now_iso()})._")
    for t in node.tags:
        if t not in target.tags:
            target.tags.append(t)
    for k, v in node.fields.items():
        if v and not target.fields.get(k):
            target.fields[k] = v
    target.updated_at = now_iso()
    store.write_node(target)
    os.remove(node.path)
    if reindex:
        build_index(store)
    return target.id


def supersede(store, node_id, replaces_id, fields=None, reindex=True):
    """Approve the draft as the successor of `replaces_id`: wires the
    supersedes edge and (via the shared promotion path) retires the old node."""
    node = _get_draft(store, node_id)
    old = store.nodes_by_id().get(replaces_id)
    if old is None:
        raise ValueError(f"supersession target '{replaces_id}' does not exist")
    if old.type != node.type:
        raise ValueError(f"a {node.type} cannot supersede a {old.type}; "
                         f"supersedes requires matching types")
    links = [{"type": "supersedes", "to": replaces_id,
              "note": "confirmed at review"}]
    return approve(store, node_id, fields=fields, links=links, reindex=reindex)
