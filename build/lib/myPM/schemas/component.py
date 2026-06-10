"""Component: a descriptive fact about something that exists in a system."""

SCHEMA = {
    "type": "component",
    "fields": {
        "kind": str,         # service | module | datastore | interface | dependency | infra
        "description": str,
        "location": str,     # repo path or URL reference
    },
    "required_draft": ["kind", "description"],
    "required_active": [],
}