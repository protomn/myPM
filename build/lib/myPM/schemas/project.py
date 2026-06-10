"""Project: a bounded engineering context that scopes knowledge."""

SCHEMA = {
    "type": "project",
    "fields": {
        "name": str,
        "description": str,
        "stack": list,
        "repos": list,
        "lifecycle": str,       # active | maintenance | archived
    },
    "required_draft": ["name", "description"],
    "required_active": [],
}