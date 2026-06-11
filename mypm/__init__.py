"""myPM — a persistent engineering memory and reasoning layer.

The graph machinery end to end: capture -> reflect (Gate 1) -> distill/review
(Gates 2+3) -> retrieve, with bootstrap to seed from git history and optional
Claude/semantic upgrades that degrade to the deterministic substrate.
"""

__version__ = "0.4.0"

from .store import Store
from .parser import load_node, load_edge, parse_frontmatter
from .reflect import reflect
from .distill import distill
from .retriever import retrieve
from .index import build_index
from . import validator, constraints

__all__ = [
    "Store", "load_node", "load_edge", "parse_frontmatter",
    "reflect", "distill", "retrieve", "build_index",
    "validator", "constraints",
]