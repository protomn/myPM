"""The physical storage layer (docs/architecture/storage.md).

The files are the database of record. Scope is a property of NODES and is
authoritative by directory location; edges are scope-free and live in one flat
directory. This module owns the layout and all disk IO.

    memory/
      inbox/                  raw observations (pre-graph, untyped)
      global/nodes/           global-scoped nodes
      projects/<id>/nodes/    project-scoped nodes
      edges/                  ALL edges, scope-free
      .index/graph.db         derived, rebuildable cache (gitignored)
"""

from __future__ import annotations

import os
import glob

import yaml

from .models import Node, Edge, Observation


class Store:
    def __init__(self, root: str):
        self.root = os.path.abspath(root)

    # ---- paths -----------------------------------------------------------
    @property
    def inbox_dir(self):     return os.path.join(self.root, "inbox")
    @property
    def global_dir(self):    return os.path.join(self.root, "global", "nodes")
    @property
    def projects_dir(self):  return os.path.join(self.root, "projects")
    @property
    def edges_dir(self):     return os.path.join(self.root, "edges")
    @property
    def index_path(self):    return os.path.join(self.root, ".index", "graph.db")
    @property
    def embeddings_dir(self): return os.path.join(self.root, ".index", "embeddings")

    def project_nodes_dir(self, project_id: str):
        return os.path.join(self.projects_dir, project_id, "nodes")

    def project_file(self, project_id: str) -> str:
        return os.path.join(self.projects_dir, project_id, "project.md")

    def ensure_layout(self):
        for d in (self.inbox_dir, self.global_dir, self.projects_dir,
                  self.edges_dir, os.path.dirname(self.index_path)):
            os.makedirs(d, exist_ok=True)

    # ---- scope <-> location (location is authoritative) ------------------
    def scope_to_nodes_dir(self, scope: str) -> str:
        if scope == "global":
            return self.global_dir
        if scope.startswith("project:"):
            return self.project_nodes_dir(scope.split(":", 1)[1])
        raise ValueError(f"bad scope: {scope!r}")

    def scope_from_path(self, path: str) -> str:
        rel = os.path.relpath(os.path.abspath(path), self.root)
        parts = rel.split(os.sep)
        if parts[0] == "global":
            return "global"
        if parts[0] == "projects":
            return f"project:{parts[1]}"
        raise ValueError(f"node outside a scoped location: {path}")

    # ---- frontmatter parsing --------------------------------------------
    @staticmethod
    def parse_frontmatter(text: str):
        if text.startswith("---"):
            _, fm, body = text.split("---", 2)
            meta = yaml.safe_load(fm) or {}
            return meta, body.lstrip("\n")
        return {}, text

    @staticmethod
    def render_frontmatter(meta: dict, body: str) -> str:
        fm = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True,
                            default_flow_style=False).rstrip()
        return f"---\n{fm}\n---\n\n{body.rstrip()}\n"

    # ---- node IO ---------------------------------------------------------
    def load_node(self, path: str) -> Node:
        with open(path, "r", encoding="utf-8") as f:
            meta, body = self.parse_frontmatter(f.read())
        return Node.from_frontmatter(meta, body, path=path)

    def write_node(self, node: Node) -> str:
        if node.type == "project" and node.scope.startswith("project:"):
            project_id = node.scope.split(":", 1)[1]
            project_dir = os.path.join(self.projects_dir, project_id)
            os.makedirs(project_dir, exist_ok=True)
            path = os.path.join(project_dir, "project.md")
        else:
            nodes_dir = self.scope_to_nodes_dir(node.scope)
            os.makedirs(nodes_dir, exist_ok=True)
            path = os.path.join(nodes_dir, f"{node.id}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.render_frontmatter(node.to_frontmatter(), node.body))
        node.path = path
        return path

    def iter_node_paths(self):
        yield from glob.glob(os.path.join(self.global_dir, "*.md"))
        yield from glob.glob(os.path.join(self.projects_dir, "*", "project.md"))
        yield from glob.glob(os.path.join(self.projects_dir, "*", "nodes", "*.md"))

    def all_nodes(self):
        return [self.load_node(p) for p in self.iter_node_paths()]

    def nodes_by_id(self):
        return {n.id: n for n in self.all_nodes()}

    # ---- edge IO ---------------------------------------------------------
    def load_edge(self, path: str) -> Edge:
        with open(path, "r", encoding="utf-8") as f:
            return Edge.from_yaml_dict(yaml.safe_load(f.read()), path=path)

    def write_edge(self, edge: Edge) -> str:
        os.makedirs(self.edges_dir, exist_ok=True)
        path = os.path.join(self.edges_dir, f"{edge.id}.yml")
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(edge.to_yaml_dict(), f, sort_keys=False, allow_unicode=True)
        edge.path = path
        return path

    def edge_exists(self, edge_id: str) -> bool:
        return os.path.exists(os.path.join(self.edges_dir, f"{edge_id}.yml"))

    def all_edges(self):
        return [self.load_edge(p) for p in glob.glob(os.path.join(self.edges_dir, "*.yml"))]

    # ---- inbox IO --------------------------------------------------------
    def write_observation(self, obs: Observation) -> str:
        os.makedirs(self.inbox_dir, exist_ok=True)
        path = os.path.join(self.inbox_dir, f"{obs.id}.yml")
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(obs.to_yaml_dict(), f, sort_keys=False, allow_unicode=True)
        return path

    def all_observations(self):
        out = []
        for p in sorted(glob.glob(os.path.join(self.inbox_dir, "*.yml"))):
            with open(p, "r", encoding="utf-8") as f:
                obs = Observation.from_yaml_dict(yaml.safe_load(f.read()))
            out.append((obs, p))
        return out

    def remove_observation(self, path: str):
        if os.path.exists(path):
            os.remove(path)