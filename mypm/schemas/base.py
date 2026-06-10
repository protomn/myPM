"""Base constants every node shares.

These mirror the Memory Node envelope from docs/architecture/core-model.md.
Schemas are declarative data so the validator can consume them and so they
remain inspectable without reading code.
"""

ENTITY_TYPES = ("project", "component", "decision", "pattern", "lesson", "preference")
STATUSES = ("draft", "active", "superseded", "deprecated")
CONFIDENCE = ("low", "medium", "high")

# Base frontmatter fields present on every node. `body` is the markdown content
# below the frontmatter, not a frontmatter key (see docs/architecture/storage.md).
BASE_FIELDS = (
    "id", "type", "title", "scope", "status",
    "confidence", "source", "tags", "created_at", "updated_at",
)

# Always required for a node to exist at all.
BASE_REQUIRED = ("id", "type", "title", "scope", "status")