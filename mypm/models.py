"""In-memory representations of the things on disk.

A Node is a markdown file (YAML frontmatter + markdown body). An Edge is a YAML
file. An Observation is a pre-graph inbox entry. A ContextBundle is what
retrieve() returns and what an agent reasons over.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from .schemas import BASE_FIELDS


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(text: str, max_words: int = 6) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return "_".join(words[:max_words]) or "untitled"


def make_node_id(node_type: str, basis: str) -> str:
    return f"{node_type}_{slugify(basis)}"


def make_edge_id(from_id: str, edge_type: str, to_id: str) -> str:
    # Deterministic => idempotent and merge-safe (docs/architecture/storage.md).
    return f"{from_id}--{edge_type}--{to_id}"


@dataclass
class Node:
    id: str
    type: str
    title: str
    scope: str                      # "global" | "project:<id>"
    status: str = "draft"
    body: str = ""                  # markdown content below the frontmatter
    confidence: str = "medium"
    source: dict = field(default_factory=lambda: {"type": "manual"})
    tags: list = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    fields: dict = field(default_factory=dict)          # entity-specific frontmatter
    proposed_links: list = field(default_factory=list)  # transient: [{type, to, note?}]
    path: str | None = None

    def to_frontmatter(self) -> dict:
        """Ordered frontmatter dict: base fields, then entity fields, then proposals."""
        fm = {
            "id": self.id, "type": self.type, "title": self.title,
            "scope": self.scope, "status": self.status,
            "confidence": self.confidence, "source": self.source,
            "tags": self.tags, "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        for k, v in self.fields.items():
            fm[k] = v
        if self.proposed_links:
            fm["proposed_links"] = self.proposed_links
        return fm

    @classmethod
    def from_frontmatter(cls, meta: dict, body: str, path: str | None = None) -> "Node":
        meta = dict(meta)
        known = set(BASE_FIELDS) | {"proposed_links"}
        entity_fields = {k: v for k, v in meta.items() if k not in known}
        return cls(
            id=meta["id"], type=meta["type"], title=meta["title"],
            scope=meta["scope"], status=meta.get("status", "draft"),
            body=body, confidence=meta.get("confidence", "medium"),
            source=meta.get("source", {"type": "manual"}),
            tags=meta.get("tags", []) or [],
            created_at=meta.get("created_at", now_iso()),
            updated_at=meta.get("updated_at", now_iso()),
            fields=entity_fields,
            proposed_links=meta.get("proposed_links", []) or [],
            path=path,
        )

    def search_text(self) -> str:
        parts = [self.title, self.body, " ".join(self.tags)]
        parts += [str(v) for v in self.fields.values()]
        return "\n".join(p for p in parts if p)


@dataclass
class Edge:
    id: str
    type: str
    from_id: str
    to_id: str
    created_at: str = field(default_factory=now_iso)
    source: dict = field(default_factory=lambda: {"type": "manual"})
    note: str = ""
    attributes: dict = field(default_factory=dict)
    path: str | None = None

    def to_yaml_dict(self) -> dict:
        d = {
            "id": self.id, "type": self.type,
            "from": self.from_id, "to": self.to_id,
            "created_at": self.created_at, "source": self.source,
        }
        if self.note:
            d["note"] = self.note
        if self.attributes:
            d["attributes"] = self.attributes
        return d

    @classmethod
    def from_yaml_dict(cls, d: dict, path: str | None = None) -> "Edge":
        return cls(
            id=d["id"], type=d["type"], from_id=d["from"], to_id=d["to"],
            created_at=d.get("created_at", now_iso()),
            source=d.get("source", {"type": "manual"}),
            note=d.get("note", ""), attributes=d.get("attributes", {}) or {},
            path=path,
        )


@dataclass
class Observation:
    id: str
    text: str
    source: str = "conversation"
    project: str | None = None        # project id, or None for global
    created_at: str = field(default_factory=now_iso)
    proposed: dict = field(default_factory=dict)  # {type, title, fields, tags, links}

    def to_yaml_dict(self) -> dict:
        return {
            "id": self.id, "text": self.text, "source": self.source,
            "project": self.project, "created_at": self.created_at,
            "proposed": self.proposed,
        }

    @classmethod
    def from_yaml_dict(cls, d: dict) -> "Observation":
        return cls(
            id=d["id"], text=d["text"], source=d.get("source", "conversation"),
            project=d.get("project"), created_at=d.get("created_at", now_iso()),
            proposed=d.get("proposed", {}) or {},
        )


@dataclass
class BundleEntry:
    id: str
    type: str
    title: str
    summary: str
    why_included: str
    source: dict


@dataclass
class ContextBundle:
    scope: list
    task: str
    agent: str | None = None
    nodes: list = field(default_factory=list)        # list[BundleEntry]
    conflicts: list = field(default_factory=list)
    followups: list = field(default_factory=list)
    token_count: int = 0
    generated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d