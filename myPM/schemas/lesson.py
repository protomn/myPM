"""Lesson: empirical knowledge gained from experience (incident-derived included).

`required_draft` is what Gate 1 demands (minimal structure to enter the graph).
`required_active` is the ADDITIONAL substantiation Gate 2 demands before a draft
becomes recallable. This is how the schema encodes the capture gates directly.
"""

SCHEMA = {
    "type": "lesson",
    "fields": {
        "trigger": str,      # what happened: the incident, mistake, or surprise
        "root_cause": str,   # why it happened
        "takeaway": str,     # the durable learning
    },
    "required_draft": ["takeaway"],       # Gate 1: minimal structure
    "required_active": ["root_cause"],    # Gate 2: substantiation
}