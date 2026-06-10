"""Preference: a standing, subjective stance about how the engineer works."""

SCHEMA = {
    "type": "preference",
    "fields": {
        "statement": str,
        "strength": str,        # strong | weak | default
        "rationale": str,
        "overridable": bool,
    },
    "required_draft": ["statement", "strength"],
    "required_active": [],
}