"""The capture proposer: turns a raw Observation into a proposed typed node.

This is the one seam where the agent layer (step 7) plugs in. Deciding a raw
remark's TYPE and extracting its semantic fields is reasoning work that belongs
to the Reflection Analyst. Until that exists, RuleProposer does it deterministically
from explicit structure the engineer supplied at capture plus light heuristics.

It is a placeholder, not a mock: it runs, it is deterministic, and it derives
real output from real input. Swap in LLMProposer(observation) -> proposal later
and nothing else in the pipeline changes.
"""

from __future__ import annotations

import re

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