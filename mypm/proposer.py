"""The capture proposer: turns a raw Observation into a proposed typed node.

This is the one seam where the agent layer plugs in. Deciding a raw remark's
TYPE and extracting its semantic fields is reasoning work that belongs to the
Reflection Analyst (docs/agents/reflection-analyst.md). Two proposers implement
the same `.propose(obs) -> dict` contract:

  - RuleProposer  — deterministic typing + field fill from explicit capture
    structure plus light heuristics. Always available, offline, free.
  - LLMProposer   — types and extracts fields with Claude when the optional
    integration is configured. Falls back through `get_proposer()` to the rule
    proposer when no key/dependency is present.

Nothing else in the pipeline changes between the two — reflect() asks the
factory for whichever is available.
"""

from __future__ import annotations

import re

from .schemas import SCHEMAS, ENTITY_TYPES

# Sources that, by their ceremony, tend to produce empirical findings (Lessons).
_FINDING_SOURCES = {"benchmark", "incident", "conversation"}

_STOPWORDS = set("the a an is are was were be to of in on at for and or with "
                 "this that it its as from by we i you they our".split())


def _keywords(text, k=5):
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower())
             if w not in _STOPWORDS and len(w) > 2]
    seen, out = set(), []
    for w in words:
        if w not in seen:
            seen.add(w); out.append(w)
    return out[:k]


class RuleProposer:
    """Deterministic typing + field fill. Honors explicit `proposed` structure
    from the observation; fills gaps with rules; never invents a root cause."""

    name = "rule"

    def propose(self, obs) -> dict:
        p = dict(obs.proposed or {})

        # type: explicit, else inferred from source ceremony
        node_type = p.get("type")
        if not node_type:
            node_type = "lesson" if obs.source in _FINDING_SOURCES else "component"

        title = p.get("title") or obs.text.strip().rstrip(".")
        tags = p.get("tags") or _keywords(obs.text)
        fields = dict(p.get("fields") or {})

        # For a lesson, the minimal Gate-1 structure is a takeaway. If the
        # engineer didn't supply one, the raw finding IS the provisional takeaway.
        if node_type == "lesson" and not fields.get("takeaway"):
            fields["takeaway"] = obs.text.strip().rstrip(".")
        # We deliberately do NOT fabricate root_cause; if absent, Gate 2 will
        # correctly refuse to promote the draft until it's supplied.

        return {
            "type": node_type,
            "title": title,
            # a clean, stable id handle distinct from the descriptive title
            # (docs/architecture/core-model.md: id is immutable, title is the label)
            "id": p.get("id"),
            "slug": p.get("slug"),
            "tags": tags,
            "fields": fields,
            "links": p.get("links", []),
            "body": p.get("body") or obs.text.strip(),
            "confidence": p.get("confidence", "medium"),
        }


# Types the proposer may assign. `project` is excluded: project nodes are created
# by `mypm init`, never typed from an inbox observation.
_TYPEABLE = tuple(t for t in ENTITY_TYPES if t != "project")

# One-line cognitive description per typeable entity; the field lists themselves
# are generated from SCHEMAS below so the prompt can never drift from the gates.
_TYPE_NOTES = {
    "component": "descriptive: a thing that exists and how it's wired",
    "decision": "a recorded intentional choice and its rationale",
    "pattern": "a prescriptive, reusable rule",
    "lesson": "empirical learning, often corrective",
    "preference": "a standing subjective default",
}

_FIELD_HINTS = {
    "kind": "one of: service | module | datastore | interface | dependency | infra",
    "strength": "one of: strong | weak | default",
}


def _system_prompt():
    lines = []
    for t in _TYPEABLE:
        s = SCHEMAS[t]
        fields = ", ".join(s["fields"].keys())
        required = ", ".join(s["required_draft"]) or "none"
        lines.append(f"- {t} — {_TYPE_NOTES.get(t, t)}\n"
                     f"  fields: {fields}\n"
                     f"  REQUIRED (the draft is rejected without these): {required}")
    hints = "\n".join(f"- {k}: {v}" for k, v in _FIELD_HINTS.items())
    return f"""You are the Reflection Analyst's Gate-1 typer for myPM, a typed
engineering knowledge graph. Given one raw observation, decide which single
entity type it is and extract the minimal structured fields that type requires.

The typeable entity types (pick exactly one):
{chr(10).join(lines)}

Field value hints:
{hints}

Rules:
- ALWAYS fill every REQUIRED field for the type you pick — derive it from the
  observation text. If you cannot honestly fill a required field, pick a type
  whose required fields the observation does support.
- Beyond required fields, fill only what the observation actually supports.
  Never invent a root_cause, rationale, or evidence the text does not contain —
  leaving an optional field empty is correct and lets the human supply it later.
- Write a short, specific title and 3-5 lowercase tags.
- Return the structured object only."""


_SYSTEM = _system_prompt()


def _proposal_schema():
    """A json_schema covering the union of fields across the TYPEABLE entities
    (project is excluded — it isn't typed from observations). The model fills the
    ones relevant to the type it picks; propose() keeps only the valid ones.
    Restricting to typeable types also keeps the optional-parameter count under
    the API's structured-output limit (24)."""
    field_names = set()
    for t in _TYPEABLE:
        field_names |= set(SCHEMAS[t]["fields"].keys())
    props = {
        "type": {"type": "string", "enum": list(_TYPEABLE)},
        "title": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "body": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    }
    for f in sorted(field_names):
        props[f] = ({"type": "array", "items": {"type": "string"}}
                    if f == "alternatives" else {"type": "string"})
    return {"type": "object", "properties": props,
            "required": ["type", "title"], "additionalProperties": False}


class LLMProposer:
    """Types an observation with Claude. Honors explicit capture structure (so a
    fully-specified `mypm capture --type ... --field ...` needs no API call), and
    keeps every engineer-supplied value over the model's."""

    name = "llm"

    def __init__(self, client=None, model=None):
        self._client = client  # injectable; lazily constructed on first use
        self._model = model    # explicit model beats MYPM_CLAUDE_MODEL/default

    def _client_or_default(self):
        if self._client is None:
            from .claude import ClaudeClient
            self._client = ClaudeClient(model=self._model)
        return self._client

    def propose(self, obs) -> dict:
        explicit = dict(obs.proposed or {})
        # If the engineer already typed and filled it at capture, trust that and
        # skip the model entirely (RuleProposer honors the same explicit structure).
        if explicit.get("type") and (explicit.get("fields") or {}):
            return RuleProposer().propose(obs)

        raw = self._client_or_default().extract(
            system=_SYSTEM, user=f"Observation (source: {obs.source}):\n{obs.text}",
            schema=_proposal_schema())

        node_type = raw.get("type") if raw.get("type") in SCHEMAS else "lesson"
        schema = SCHEMAS[node_type]
        fields = {f: raw[f] for f in schema["fields"] if raw.get(f)}
        fields.update(explicit.get("fields") or {})       # engineer's fields win

        return {
            "type": node_type,
            "title": explicit.get("title") or raw.get("title") or obs.text.strip()[:80],
            "id": explicit.get("id"),
            "slug": explicit.get("slug"),
            "tags": explicit.get("tags") or raw.get("tags") or _keywords(obs.text),
            "fields": fields,
            "links": explicit.get("links", []),
            "body": explicit.get("body") or raw.get("body") or obs.text.strip(),
            "confidence": explicit.get("confidence") or raw.get("confidence", "medium"),
        }


def get_proposer(prefer_llm: bool = True, model=None):
    """Return the LLM proposer when the integration is available, else the rule
    proposer. The single decision point reflect() uses, so the rest of the
    pipeline never needs to know which one ran."""
    if prefer_llm:
        from . import claude
        if claude.available():
            return LLMProposer(model=model)
    return RuleProposer()