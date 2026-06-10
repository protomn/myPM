"""Decision: a recorded intentional choice with alternatives and rationale."""

SCHEMA = {
    "type": "decision",
    "fields": {
        "context": str,
        "choice": str,
        "alternatives": list,
        "rationale": str,
        "consequences": str,
    },
    "required_draft": ["choice", "rationale"],
    "required_active": ["alternatives", "consequences"],
}