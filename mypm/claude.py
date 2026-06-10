"""The Claude integration seam (docs/architecture/agents.md).

Wraps the Anthropic SDK behind a tiny, swappable surface so the dependency stays
optional and lazily imported: nothing here touches `anthropic` until an
LLM-backed path actually runs. With no `anthropic` install, no API key, or
MYPM_NO_LLM set, `available()` returns False and callers fall back to the
deterministic substrate (RuleProposer, lexical seed) — myPM keeps working
offline exactly as v0.1 did. The AI is an upgrade, never a requirement.

Model defaults to Claude Opus 4.8 (`claude-opus-4-8`); override with
MYPM_CLAUDE_MODEL. Reasoning paths use adaptive thinking at high effort; the
structured-typing path uses a json_schema output constraint.
"""

from __future__ import annotations

import json
import os

DEFAULT_MODEL = "claude-opus-4-8"


def available(env=None) -> bool:
    """True iff an LLM-backed path can run: a key is present, the SDK is
    importable, and the user has not opted out via MYPM_NO_LLM."""
    env = env if env is not None else os.environ
    if env.get("MYPM_NO_LLM"):
        return False
    if not (env.get("ANTHROPIC_API_KEY") or env.get("ANTHROPIC_AUTH_TOKEN")):
        return False
    try:
        import anthropic  # noqa: F401  (probe only)
    except ImportError:
        return False
    return True


class ClaudeClient:
    """Minimal two-method client: `complete` for doctrine reasoning, `extract`
    for structured typing. Constructing it imports and initializes the SDK."""

    def __init__(self, model=None, env=None):
        env = env if env is not None else os.environ
        import anthropic  # lazy, optional
        self.model = model or env.get("MYPM_CLAUDE_MODEL", DEFAULT_MODEL)
        self._client = anthropic.Anthropic()

    def _reasoning_params(self) -> dict:
        """Thinking/effort parameters the active model actually supports.

        Adaptive thinking and the effort parameter exist on Sonnet 4.6+, Opus
        4.6+, and Fable; Haiku supports neither and 400s if they are sent. The
        check is a denylist on haiku so future top-tier models default to the
        full reasoning surface."""
        if "haiku" in self.model:
            return {}
        return {"thinking": {"type": "adaptive"},
                "output_config": {"effort": "high"}}

    def complete(self, system: str, user: str, max_tokens: int = 12000) -> str:
        """Reasoned free-text completion (council agents)."""
        msg = self._client.messages.create(
            model=self.model, max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            **self._reasoning_params(),
        )
        return "".join(b.text for b in msg.content if b.type == "text").strip()

    def extract(self, system: str, user: str, schema: dict,
                max_tokens: int = 2048) -> dict:
        """Prompt-directed JSON extraction (LLMProposer typing). No structured
        output constraint — grammar compilation times out on complex schemas.
        Model is instructed to return a bare JSON object; we strip any fences."""
        msg = self._client.messages.create(
            model=self.model, max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user + "\n\nReturn only a valid JSON object, no markdown fences, no explanation."}],
        )
        text = next(b.text for b in msg.content if b.type == "text").strip()
        # Strip optional ```json ... ``` or ``` ... ``` fences
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0].strip()
        return json.loads(text)
