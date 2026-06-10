"""Pluggable semantic embeddings — one way to find entry points into the graph.

The graph is the interesting part. Embeddings are not a search engine bolted on
top of myPM; they are a second seeder feeding the same pipeline:

    lexical seed  +  semantic seed  ->  expand (edges)  ->  rank  ->  ContextBundle

So a node can be *found* by meaning as well as by words, then the typed-edge
expansion and ranking do the real work. Retrieval never becomes "semantic search
-> everything else".

Three design commitments hold this in place:

1. **Optional, silent fallback.** `pip install mypm` stays clean. The embedder is
   an extra (`mypm[semantic]`); when it (or torch/numpy) is absent, retrieval
   falls back to the lexical seed with no warning, no error, no degraded UX.
2. **Content-addressed, file-backed cache.** Each vector is a JSON file named
   `sha256(model + "\\n" + text)` under `knowledge/.index/embeddings/`. Edits and
   model switches both miss naturally; there is no DB, no schema, no migration.
   Delete the index dir and `mypm retrieve` rebuilds it. Embeddings are even more
   disposable than the index.
3. **An Embedder interface.** A small contract so v0.3 can add Ollama / OpenAI /
   Voyage / other local models without retrieval.py turning into an if/else
   chain — every provider is just another `Embedder` subclass.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from abc import ABC, abstractmethod

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def cosine(a, b) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


# ---- the Embedder interface ---------------------------------------------

class Embedder(ABC):
    """Anything that turns text into vectors. `model_name` namespaces the cache
    (so two models never collide on the same content); `enabled` lets a disabled
    embedder flow through retrieval without a branch at the call site."""

    model_name: str = "embedder"
    enabled: bool = True

    @abstractmethod
    def embed(self, texts) -> list:
        """Return one vector (list[float]) per input text."""


class LocalEmbedder(Embedder):
    """sentence-transformers, lazily loaded so importing this module is cheap and
    the dependency is only required when semantic retrieval actually runs."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name
        self._model = None

    def _ensure(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # lazy, optional
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, texts):
        model = self._ensure()
        return [list(map(float, v)) for v in model.encode(list(texts))]


class NullEmbedder(Embedder):
    """The no-op embedder returned when semantics are unavailable or opted out.
    `enabled` is False, so retrieval skips the semantic seed and uses lexical
    only — the silent-fallback path, expressed as a null object rather than None."""

    model_name = "null"
    enabled = False

    def embed(self, texts):
        return [[] for _ in texts]


def load_embedder(env=None) -> Embedder:
    """Return the active embedder — `LocalEmbedder` when the optional dependency
    is installed and not opted out, else `NullEmbedder`. Never raises, never
    returns None; a missing install is a fallback, not an error.

    MYPM_NO_SEMANTIC opts out; MYPM_EMBED_MODEL overrides the local model.
    """
    env = env if env is not None else os.environ
    if env.get("MYPM_NO_SEMANTIC"):
        return NullEmbedder()
    try:
        import sentence_transformers  # noqa: F401  (probe only)
    except ImportError:
        return NullEmbedder()
    return LocalEmbedder(env.get("MYPM_EMBED_MODEL", DEFAULT_MODEL))


# ---- content-addressed file cache ---------------------------------------

def digest(model_name: str, text: str) -> str:
    """sha256 over model + content. Folding the model into the digest means a
    model switch produces different filenames with no extra bookkeeping."""
    return hashlib.sha256(f"{model_name}\n{text or ''}".encode("utf-8")).hexdigest()


class EmbeddingCache:
    """A flat directory of `<digest>` JSON files — the files are the cache. No
    schema, no DB; delete the directory and it rebuilds on the next retrieve."""

    def __init__(self, dir_path: str, model_name: str):
        self.dir = dir_path
        self.model_name = model_name
        os.makedirs(dir_path, exist_ok=True)

    def _path(self, text: str) -> str:
        return os.path.join(self.dir, digest(self.model_name, text))

    def embed_cached(self, texts, embed_fn) -> list:
        """Return a vector per text, reading hits from disk and computing only the
        misses (then writing them back). Order matches `texts`."""
        texts = list(texts)
        out = [None] * len(texts)
        miss_idx, miss_txt = [], []
        for i, t in enumerate(texts):
            path = self._path(t)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    out[i] = json.load(f)
            else:
                miss_idx.append(i)
                miss_txt.append(t)
        if miss_txt:
            for i, t, vec in zip(miss_idx, miss_txt, embed_fn(miss_txt)):
                with open(self._path(t), "w", encoding="utf-8") as f:
                    json.dump(vec, f)
                out[i] = vec
        return out
