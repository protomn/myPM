"""Tests for the Claude integration: availability gating, the LLM proposer, and
the council runner. A fake client stands in for the Anthropic SDK so the whole
surface is exercised with no network, key, or optional dependency.
Runnable with `python tests/test_claude.py`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mypm import claude, council, agents
from mypm.proposer import LLMProposer, RuleProposer, get_proposer, _proposal_schema
from mypm.store import Store
from mypm.models import Node, Observation


class FakeClient:
    def __init__(self, extract_result=None):
        self.completes, self.extracts = [], []
        self._extract = extract_result or {
            "type": "lesson", "title": "allocator overhead",
            "tags": ["performance"], "takeaway": "benchmark before optimizing",
            "body": "allocator cost dominated the hot path"}

    def complete(self, system, user, max_tokens=12000):
        self.completes.append({"system": system, "user": user})
        return f"OUTPUT#{len(self.completes)}"

    def extract(self, system, user, schema, max_tokens=2048):
        self.extracts.append({"user": user, "schema": schema})
        return dict(self._extract)


# ---- availability gating ------------------------------------------------

def test_available_false_without_key():
    assert claude.available(env={}) is False


def test_available_respects_optout():
    assert claude.available(env={"ANTHROPIC_API_KEY": "x", "MYPM_NO_LLM": "1"}) is False


def test_get_proposer_falls_back_without_integration():
    # no key in this env -> rule proposer
    assert isinstance(get_proposer(), RuleProposer)


# ---- LLM proposer -------------------------------------------------------

def test_proposal_schema_excludes_project_and_requires_type_title():
    schema = _proposal_schema()
    assert schema["required"] == ["type", "title"]
    assert "project" not in schema["properties"]["type"]["enum"]
    assert set(schema["properties"]["type"]["enum"]) == {
        "component", "decision", "pattern", "lesson", "preference"}


def test_llm_proposer_types_and_keeps_only_valid_fields():
    fake = FakeClient()
    obs = Observation(id="obs_1", text="allocator overhead dominates the hot path",
                      source="benchmark")
    p = LLMProposer(client=fake).propose(obs)
    assert p["type"] == "lesson"
    assert p["fields"] == {"takeaway": "benchmark before optimizing"}  # root_cause absent, not invented
    assert p["tags"] == ["performance"]
    assert len(fake.extracts) == 1


def test_llm_proposer_honors_explicit_capture_without_calling_model():
    fake = FakeClient()
    obs = Observation(id="obs_2", text="we chose JWTs", source="conversation",
                      proposed={"type": "decision",
                                "fields": {"choice": "JWTs", "rationale": "stateless edge"}})
    p = LLMProposer(client=fake).propose(obs)
    assert p["type"] == "decision"
    assert p["fields"]["choice"] == "JWTs"
    assert fake.extracts == []          # fully specified at capture -> no API call


# ---- council runner -----------------------------------------------------

def test_presets_resolve():
    assert council.resolve_agents(preset="full") == \
        ["research", "principal", "adversarial", "performance", "oss"]
    assert council.resolve_agents("principal, oss") == ["principal", "oss"]
    assert council.resolve_agents(None, None) == council.PRESETS[council.DEFAULT_PRESET]


def test_unknown_agent_rejected():
    try:
        council.resolve_agents("principal,wizard")
    except ValueError as e:
        assert "wizard" in str(e)
    else:
        raise AssertionError("expected ValueError for unknown agent")


def test_doctrine_text_found_for_every_agent():
    for name in agents.AGENT_NAMES:
        assert council._doctrine_text(agents.get(name)), name


def _seed(tmp_path):
    s = Store(str(tmp_path / "knowledge")); s.ensure_layout()
    s.write_node(Node(
        id="lesson_alloc", type="lesson", title="allocator overhead",
        scope="global", status="active", body="allocator cost dominated the hot path",
        fields={"trigger": "x", "root_cause": "x", "takeaway": "benchmark first"}))
    return s


def test_run_agent_recalls_and_reasons_under_doctrine(tmp_path):
    s = _seed(tmp_path)
    fake = FakeClient()
    turn = council.run_agent(s, "principal", "optimize the hot path", client=fake)
    assert turn.agent == "principal"
    assert turn.command == "/architect"
    assert turn.output == "OUTPUT#1"
    assert "nodes" in turn.bundle               # a real ContextBundle was recalled
    # doctrine + guardrails went into the system prompt
    assert "Stay strictly within your mandate" in fake.completes[0]["system"]


def test_run_council_threads_prior_output(tmp_path):
    s = _seed(tmp_path)
    fake = FakeClient()
    turns = council.run_council(s, "optimize the hot path",
                                ["principal", "adversarial"], client=fake)
    assert [t.agent for t in turns] == ["principal", "adversarial"]
    # the second agent sees the first's output as prior context
    assert "Prior council output" in fake.completes[1]["user"]
    assert "OUTPUT#1" in fake.completes[1]["user"]


if __name__ == "__main__":
    import tempfile, pathlib
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            if fn.__code__.co_argcount:
                with tempfile.TemporaryDirectory() as d:
                    fn(pathlib.Path(d))
            else:
                fn()
            print(f"  ok  {name}")
            passed += 1
    print(f"\n{passed} tests passed.")
