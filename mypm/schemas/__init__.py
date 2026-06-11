"""Schema registry. Import SCHEMAS to look up any entity's field rules.

    from .schemas import SCHEMAS
    SCHEMAS["lesson"]["required_active"]  -> ["root_cause"]
"""

from . import base
from . import lesson, decision, pattern, component, preference, project

ENTITY_TYPES = base.ENTITY_TYPES
STATUSES = base.STATUSES
CONFIDENCE = base.CONFIDENCE
BASE_FIELDS = base.BASE_FIELDS
BASE_REQUIRED = base.BASE_REQUIRED

SCHEMAS = {
    m.SCHEMA["type"]: m.SCHEMA
    for m in (lesson, decision, pattern, component, preference, project)
}


def coerce_field(node_type: str, fname: str, value):
    """CLI and capture values arrive as strings; list-typed schema fields split
    on ';'. The ONE coercion rule, shared by capture/reflect and review — the
    two paths drifting apart is how `--field alternatives="a; b"` once produced
    a string node where the schema wanted a list."""
    want = SCHEMAS.get(node_type, {}).get("fields", {}).get(fname)
    if want is list and isinstance(value, str):
        return [v.strip() for v in value.split(";") if v.strip()]
    return value


def coerce_fields(node_type: str, fields: dict) -> dict:
    return {k: coerce_field(node_type, k, v) for k, v in (fields or {}).items()}


__all__ = ["SCHEMAS", "ENTITY_TYPES", "STATUSES", "CONFIDENCE", "BASE_FIELDS",
           "BASE_REQUIRED", "coerce_field", "coerce_fields"]