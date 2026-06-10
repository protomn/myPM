"""Tests for semantic retrieval: the embedder seam, the lexical/semantic blend,
the content-addressed cache, and the silent fallback. Runnable with
`python tests/test_semantic.py`. A deterministic fake embedder stands in for the
optional sentence-transformers dependency.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from myPM import embeddings
from myPM.store import Store
from myPM.models import Node
from myPM.retriever import retrieve


class FakeEmbedder:
    """Maps text onto three concept axes (latency / cache / auth). Two phrases
    that share a concept but no words get cosine 1.0 — exactly the synonymy the
    lexical seed misses. Counts how many texts it embeds, to prove caching."""

    model_name = "fake-concept-v1"

    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        texts = list(texts)
        self.calls += len(texts)
        return [self._vec(t) for t in texts]

    @staticmethod
    def _vec(t):
        t = t.lower()
        return [
            float(any(w in t for w in ("latency", "slow", "speed", "fast", "throughput"))),
            float(any(w in t for w in ("cache", "redis", "stampede"))),
            float(any(w in t for w in ("auth", "token", "jwt"))),
        ]


def _seed_two(tmp_path):
    s = Store(str(tmp_path / "knowledge")); s.ensure_layout()
    s.write_node(Node(
        id="lesson_serialization_latency", type="lesson",
        title="reduce serialization latency", scope="global", status="active",
        body="throughput improved after batching writes",
        fields={"trigger": "x", "root_cause": "x", "takeaway": "batch writes"}))
    s.write_node(Node(
        id="lesson_jwt_rotation", type="lesson",
        title="rotate auth tokens often", scope="global", status="active",
        body="short-lived jwt limited blast radius",
        fields={"trigger": "x", "root_cause": "x", "takeaway": "rotate tokens"}))
    return s


def test_semantic_surfaces_synonym(tmp_path):
    """'speed up the writes' shares no words with 'reduce serialization latency',
    so lexical alone cannot find it; the semantic seed should."""
    s = _seed_two(tmp_path)
    task = "make it faster"            # shares no words with either node

    # lexical only (force the fallback regardless of whether a model is installed)
    os.environ["MYPM_NO_SEMANTIC"] = "1"
    try:
        lexical_only = retrieve(s, task)
    finally:
        del os.environ["MYPM_NO_SEMANTIC"]
    assert "lesson_serialization_latency" not in [n["id"] for n in lexical_only.nodes]

    with_sem = retrieve(s, task, embedder=FakeEmbedder())
    ids = [n["id"] for n in with_sem.nodes]
    assert "lesson_serialization_latency" in ids
    # the off-concept auth lesson should not be pulled by this query
    assert "lesson_jwt_rotation" not in ids


def test_lexical_dominates_semantic_rescues(tmp_path):
    """A node with a real lexical hit must outrank a purely-semantic match — the
    0.8/0.2 blend makes semantic a rescue signal, not primary retrieval."""
    s = Store(str(tmp_path / "knowledge")); s.ensure_layout()
    # lexical hit: shares words with the query
    s.write_node(Node(
        id="lesson_redis_cache_invalidation", type="lesson",
        title="redis cache invalidation strategy", scope="global", status="active",
        body="cache invalidation tuning", tags=["cache"],
        fields={"trigger": "x", "root_cause": "x", "takeaway": "invalidate carefully"}))
    # semantic-only: same concept (cache axis via 'stampede'), no shared words
    s.write_node(Node(
        id="lesson_thundering_stampede", type="lesson",
        title="thundering stampede on expiry", scope="global", status="active",
        body="herd reformed on expiry", tags=["herd"],
        fields={"trigger": "x", "root_cause": "x", "takeaway": "stagger expiry"}))

    b = retrieve(s, "redis cache invalidation", embedder=FakeEmbedder())
    ids = [n["id"] for n in b.nodes]
    assert ids[0] == "lesson_redis_cache_invalidation"     # lexical hit leads
    assert "lesson_thundering_stampede" in ids             # semantic still rescues it in


def test_embedding_cache_persists_and_reuses(tmp_path):
    s = _seed_two(tmp_path)
    e1 = FakeEmbedder()
    retrieve(s, "cache stampede", embedder=e1)
    assert os.path.isdir(s.embeddings_dir)
    assert os.listdir(s.embeddings_dir)          # one content-addressed file per node
    assert e1.calls >= 2                          # both candidate nodes embedded once

    # a fresh embedder (same model name) reuses the cached vectors: it should only
    # embed the query, not re-embed the unchanged nodes.
    e2 = FakeEmbedder()
    retrieve(s, "cache stampede", embedder=e2)
    assert e2.calls == 1                          # query only; node vectors came from cache


def test_cache_files_are_content_addressed(tmp_path):
    s = _seed_two(tmp_path)
    retrieve(s, "cache stampede", embedder=FakeEmbedder())
    names = os.listdir(s.embeddings_dir)
    # filenames are sha256 hex digests (64 chars), no schema/extension
    assert all(len(n) == 64 and all(c in "0123456789abcdef" for c in n) for n in names)


def test_load_embedder_optout_is_null_not_none():
    e = embeddings.load_embedder(env={"MYPM_NO_SEMANTIC": "1"})
    assert isinstance(e, embeddings.NullEmbedder)
    assert e.enabled is False


def test_load_embedder_null_without_dependency():
    # sentence-transformers is not installed in this env -> NullEmbedder, never None
    e = embeddings.load_embedder(env={})
    assert isinstance(e, embeddings.NullEmbedder)
    assert e.enabled is False


def test_cosine_basics():
    assert embeddings.cosine([1, 0], [1, 0]) == 1.0
    assert embeddings.cosine([1, 0], [0, 1]) == 0.0
    assert embeddings.cosine([], [1]) == 0.0


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
