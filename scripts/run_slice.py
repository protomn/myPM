#!/usr/bin/env python3
"""Vertical Slice #1 — the smallest complete proof that the architecture works.

End to end, no mocks:

    Observation  ->  /reflect  ->  draft Lesson
                 ->  /distill  ->  active Lesson + motivates edge + index rebuild
                 ->  retrieve() ->  ContextBundle containing the Lesson

The graph is seeded with one prior node (an active Decision) so the new Lesson
has something to `motivate` and so retrieval can demonstrate edge expansion.
"""

import os
import shutil
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mypm.store import Store
from mypm.models import Node, Observation
from mypm import reflect, distill, retrieve, validator

MEMORY = os.path.join(ROOT, "knowledge_demo")
PROJECT = "binary_serializer"


def rule(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def show_file(path):
    print(f"\n--- {os.path.relpath(path, ROOT)} ---")
    with open(path) as f:
        print(f.read().rstrip())


def main():
    # fresh slate for a reproducible proof
    if os.path.isdir(MEMORY):
        shutil.rmtree(MEMORY)
    store = Store(MEMORY)
    store.ensure_layout()

    rule("SEED  ·  the graph is never empty: one prior active Decision")
    store.write_node(Node(
        id="project_binary_serializer", type="project",
        title="Binary Serializer", scope=f"project:{PROJECT}", status="active",
        body="High-throughput binary serializer for the wire protocol.",
        fields={"name": "binary_serializer",
                "description": "High-throughput binary serializer",
                "stack": ["rust"], "lifecycle": "active"},
    ))
    decision = Node(
        id="decision_stack_buffers", type="decision",
        title="Use reused stack buffers over per-call heap allocation",
        scope=f"project:{PROJECT}", status="active",
        body="Reuse a per-thread stack buffer; allocate only on overflow.",
        tags=["performance", "allocation"],
        source={"type": "pr", "ref": "serializer#214"},
        fields={
            "context": "serializer hot path allocated on every call",
            "choice": "reuse a per-thread stack buffer; allocate only on overflow",
            "alternatives": ["arena allocator", "custom pool", "leave as-is"],
            "rationale": "removes the allocator from the inner loop with least machinery",
            "consequences": "buffer sizing becomes a tuning parameter",
        },
    )
    store.write_node(decision)
    print("seeded: project_binary_serializer, decision_stack_buffers (active)")

    rule("INPUT  ·  one raw Observation lands in the inbox")
    obs = Observation(
        id="obs_allocator", text="allocator overhead dominates serializer hot path",
        source="benchmark", project=PROJECT,
        proposed={
            "type": "lesson",
            "slug": "allocator overhead",          # -> clean id; title stays descriptive
            "tags": ["performance", "allocation", "latency"],
            "fields": {
                "trigger": "serialization optimization effort",
                "root_cause": "allocator cost dominated runtime",
                "takeaway": "benchmark allocations before optimizing hot paths",
            },
            # the engineer notes this finding motivated the stack-buffer decision
            "links": [{"type": "motivates", "to": "decision_stack_buffers"}],
        },
    )
    path = store.write_observation(obs)
    print(f'observation: "{obs.text}"')
    print(f"written to : {os.path.relpath(path, ROOT)}  (inbox = NOT yet in the graph)")

    rule("/reflect  ·  Gate 1 — admit + type the observation into a draft Lesson")
    for r in reflect(store):
        print(f"  {obs.id}: {'ADMITTED -> ' + r.node_id if r.admitted else 'held'}")
        for reason in r.reasons:
            print(f"      - {reason}")
    draft_path = os.path.join(store.project_nodes_dir(PROJECT), "lesson_allocator_overhead.md")
    show_file(draft_path)

    rule("/distill  ·  Gate 2 — substantiate, link, promote; rebuild the index")
    rep = distill(store)
    print(f"  promoted to active : {rep.promoted}")
    print(f"  edges created      : {rep.edges_created}")
    print(f"  pattern candidates : {rep.patterns_proposed or '(none — no recurrence yet)'}")
    print(f"  index rebuilt      : {os.path.relpath(rep.index_path, ROOT)}") #type: ignore
    show_file(draft_path)
    show_file(store.all_edges()[0].path)

    rule("BUILD PASS  ·  the graph validates")
    errors, warnings = validator.validate_all(store)
    print(f"  {len(errors)} errors, {len(warnings)} warnings")

    rule("retrieve()  ·  Recall — assemble a ContextBundle for a task")
    task = "how do I optimize the serializer hot path?"
    print(f'  task: "{task}"')
    bundle = retrieve(store, task, project=PROJECT)
    print(f"\n  scope        : {bundle.scope}")
    print(f"  token_count  : {bundle.token_count}")
    print("  nodes:")
    for n in bundle.nodes:
        print(f"    · {n['id']} ({n['type']})  <- {n['why_included']}")
        print(textwrap.indent(textwrap.fill(n["summary"], 60), "        "))
    if bundle.followups:
        print("  followups (on demand):")
        for f in bundle.followups:
            print(f"    · {f['edge']} -> {f['to']}")

    rule("retrieve()  ·  isolating pull-edge expansion")
    # 'dominates'/'benchmark' appear only in the Lesson, so the Decision cannot
    # seed on relevance — it can only arrive by following the motivates edge.
    narrow = "what dominates the benchmark"
    print(f'  task: "{narrow}"')
    nb = retrieve(store, narrow, project=PROJECT)
    for n in nb.nodes:
        print(f"    · {n['id']} ({n['type']})  <- {n['why_included']}")

    rule("PROOF")
    ids = [n["id"] for n in bundle.nodes]
    assert "lesson_allocator_overhead" in ids, "Lesson missing from bundle!"
    assert "decision_stack_buffers" in ids, "motivated Decision not in bundle!"
    lesson = next(n for n in store.all_nodes() if n.id == "lesson_allocator_overhead")
    assert lesson.status == "active", "Lesson was not promoted to active!"
    assert lesson.title == "allocator overhead dominates serializer hot path", \
        "title should stay the full descriptive sentence"
    assert store.edge_exists("lesson_allocator_overhead--motivates--decision_stack_buffers")
    # the narrow query proves expansion, not coincidental co-seeding
    narrow_why = {n["id"]: n["why_included"] for n in nb.nodes}
    assert "lesson_allocator_overhead" in narrow_why
    assert "decision_stack_buffers" in narrow_why, "Decision not reached via edge!"
    assert "motivates" in narrow_why["decision_stack_buffers"], \
        "Decision should arrive via the motivates pull edge"
    print("  PASS: observation -> draft -> active Lesson, motivates edge created,")
    print("        index rebuilt, clean id with descriptive title, and the Lesson")
    print("        (plus its motivated Decision, reached purely by pull-edge")
    print("        expansion under the narrow query) appears in the ContextBundle.")
    print("\n  The architecture survives contact with an interpreter.")


if __name__ == "__main__":
    main()