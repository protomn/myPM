"""Parser entry points named as the build plan asked for: load_node, load_edge.

These are thin wrappers over the Store IO so the spec's vocabulary maps directly
to callable functions. A Store carries the memory root; these helpers let you
parse a single file without one.
"""

from __future__ import annotations

import yaml

from .models import Node, Edge
from .store import Store


def parse_frontmatter(text: str):
    return Store.parse_frontmatter(text)


def load_node(path: str) -> Node:
    with open(path, "r", encoding="utf-8") as f:
        meta, body = Store.parse_frontmatter(f.read())
    return Node.from_frontmatter(meta, body, path=path)


def load_edge(path: str) -> Edge:
    with open(path, "r", encoding="utf-8") as f:
        return Edge.from_yaml_dict(yaml.safe_load(f.read()), path=path)