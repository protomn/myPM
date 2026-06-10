"""The Relationship Model, as enforceable data.

Everything here is a direct transcription of docs/architecture/relationships.md:
the validity table (which (from_type, edge, to_type) triples are legal), the
traversal policy per edge (pull / link / flag), and the acyclicity rules. The
validator and retriever read from this so the spec and the code cannot drift.
"""

from .schemas import ENTITY_TYPES

ANY = set(ENTITY_TYPES)

# policy: pull  -> follow automatically during context assembly
#         link  -> available on demand only (history / lineage)
#         flag  -> surface existence as a warning, never pull content
#         structural -> scope assignment, not a materialized edge (scope is by location)
EDGE_RULES = {
    "belongs_to":     {"from": ANY,                                   "to": {"project"},           "policy": "structural", "materialized": False},
    "part_of":        {"from": {"component"},                          "to": {"component"},          "policy": "pull",  "acyclic": True},
    "depends_on":     {"from": {"component"},                          "to": {"component"},          "policy": "pull",  "acyclic": "warn"},
    "builds_on":      {"from": {"decision"},                           "to": {"decision"},           "policy": "link",  "acyclic": True},
    "motivates":      {"from": {"lesson"},                             "to": {"decision", "pattern"},"policy": "pull"},
    "derived_from":   {"from": {"pattern"},                            "to": {"lesson"},             "policy": "pull"},
    "establishes":    {"from": {"decision"},                           "to": {"pattern"},            "policy": "pull",  "acyclic": True},
    "influences":     {"from": {"preference"},                         "to": {"decision", "pattern"},"policy": "link"},
    "affects":        {"from": {"decision"},                           "to": {"component"},          "policy": "pull"},
    "concerns":       {"from": {"lesson"},                             "to": {"component"},          "policy": "pull"},
    "applies":        {"from": {"decision"},                           "to": {"pattern"},            "policy": "pull"},
    "supersedes":     {"from": ANY - {"project"},                      "to": ANY - {"project"},      "policy": "link",  "acyclic": True, "same_type": True}, #type: ignore
    "conflicts_with": {"from": {"decision", "pattern", "preference"},  "to": {"decision", "pattern", "preference"}, "policy": "flag", "symmetric": True},
    "relates_to":     {"from": ANY,                                    "to": ANY,                    "policy": "link",  "symmetric": True},
}

EDGE_TYPES = tuple(EDGE_RULES.keys())

PULL_EDGES = {e for e, r in EDGE_RULES.items() if r["policy"] == "pull"}
LINK_EDGES = {e for e, r in EDGE_RULES.items() if r["policy"] == "link"}
FLAG_EDGES = {e for e, r in EDGE_RULES.items() if r["policy"] == "flag"}

# Edges whose graph must be a DAG (a cycle fails the build).
ACYCLIC_ENFORCED = {e for e, r in EDGE_RULES.items() if r.get("acyclic") is True}
# Edges where a cycle is allowed but flagged as a smell.
ACYCLIC_WARN = {e for e, r in EDGE_RULES.items() if r.get("acyclic") == "warn"}


def is_legal_edge(edge_type, from_type, to_type):
    """Return (ok, reason). Implements the validity-constraints table."""
    rule = EDGE_RULES.get(edge_type)
    if rule is None:
        return False, f"unknown edge type '{edge_type}'"
    if rule.get("materialized") is False:
        return False, (f"'{edge_type}' is structural (scope is assigned by file "
                       f"location) and must never exist as an edge file")
    if from_type not in rule["from"]:
        return False, f"{edge_type} cannot originate from a {from_type}"
    if to_type not in rule["to"]:
        return False, f"{edge_type} cannot point to a {to_type}"
    if rule.get("same_type") and from_type != to_type:
        return False, f"{edge_type} requires both ends to be the same type"
    return True, ""


def policy_of(edge_type):
    return EDGE_RULES.get(edge_type, {}).get("policy", "link")