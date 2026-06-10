"""Pattern: a prescriptive, reusable solution shape ("when X, do Y")."""

SCHEMA = {
    "type": "pattern",
    "fields": {
        "applicability": str,
        "solution": str,
        "example": str,
        "anti_patterns": list,
    },
    "required_draft": ["applicability", "solution"],
    "required_active": [],
}