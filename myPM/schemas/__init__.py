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

__all__ = ["SCHEMAS", "ENTITY_TYPES", "STATUSES", "CONFIDENCE", "BASE_FIELDS", "BASE_REQUIRED"]