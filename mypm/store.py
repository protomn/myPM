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
import re
import glob

import yaml

from .models import Node, Edge, Observation


# The on-disk layout version. Bump when the file shapes change (frontmatter
# fields, directory structure) so a future `mypm migrate` can find graphs that
# predate the change. Written once at layout creation, never touched after.
LAYOUT_VERSION = 1

# The default name of the knowledge root directory inside a repository.
DEFAULT_ROOT_NAME = "knowledge"


def looks_like_root(path: str) -> bool:
    """True if `path` is a knowledge root: the meta.yml marker, or (for graphs
    that predate the marker) the layout's signature directories."""
    if not os.path.isdir(path):
        return False
    if os.path.isfile(os.path.join(path, "meta.yml")):
        return True
    return (os.path.isdir(os.path.join(path, "edges"))
            and (os.path.isdir(os.path.join(path, "projects"))
                 or os.path.isdir(os.path.join(path, "global"))))


def find_root(start: str = ".", name: str = DEFAULT_ROOT_NAME) -> str | None:
    """Walk up from `start` looking for a knowledge root, the way git finds
    .git. Checks `<dir>/<name>` at every level (and `start` itself, so running
    from inside the knowledge tree works). Returns the absolute root path, or
    None — never creates anything.

    This is what makes `mypm retrieve` from repo/src/deep/ find repo/knowledge/
    instead of silently inventing an empty graph where it stands."""
    cur = os.path.abspath(start)
    while True:
        if looks_like_root(os.path.join(cur, name)):
            return os.path.join(cur, name)
        if os.path.basename(cur) == name and looks_like_root(cur):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


class Store:
    def __init__(self, root: str):
        self.root = os.path.abspath(root)

    # ---- paths -----------------------------------------------------------
    @property
    def inbox_dir(self):     return os.path.join(self.root, "inbox")
    @property
    def held_dir(self):      return os.path.join(self.inbox_dir, "held")
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

    @property
    def meta_path(self):     return os.path.join(self.root, "meta.yml")

    def ensure_layout(self):
        for d in (self.inbox_dir, self.global_dir, self.projects_dir,
                  self.edges_dir, os.path.dirname(self.index_path)):
            os.makedirs(d, exist_ok=True)
        if not os.path.exists(self.meta_path):
            with open(self.meta_path, "w", encoding="utf-8") as f:
                yaml.safe_dump({"layout_version": LAYOUT_VERSION}, f)

    def layout_version(self) -> int:
        if not os.path.exists(self.meta_path):
            return 1                     # pre-marker graphs are layout 1
        with open(self.meta_path, "r", encoding="utf-8") as f:
            return int((yaml.safe_load(f.read()) or {}).get("layout_version", 1))

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
        # Line-anchored: only a line that is exactly '---' delimits frontmatter,
        # so a '---' inside a YAML value or the markdown body cannot truncate it.
        if text.startswith("---"):
            m = re.match(r"^---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)", text, re.S)
            if m is None:
                raise ValueError("unterminated frontmatter: file opens with '---' "
                                 "but has no closing '---' line")
            meta = yaml.safe_load(m.group(1)) or {}
            return meta, text[m.end():].lstrip("\n")
        return {}, text

    @staticmethod
    def render_frontmatter(meta: dict, body: str) -> str:
        fm = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True,
                            default_flow_style=False).rstrip()
        return f"---\n{fm}\n---\n\n{body.rstrip()}\n"

    # ---- node IO ---------------------------------------------------------
    def load_node(self, path: str) -> Node:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        try:
            meta, body = self.parse_frontmatter(text)
            return Node.from_frontmatter(meta, body, path=path)
        except (ValueError, KeyError, yaml.YAMLError) as e:
            raise ValueError(f"unparseable node file {path}: {e}") from e

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

    # ---- held quarantine ---------------------------------------------------
    # Observations that fail Gate 1 move to inbox/held/ with their failure
    # reasons embedded, instead of being re-processed (and, with an LLM
    # proposer, re-billed) on every subsequent reflect run. The engineer edits
    # the file and runs `mypm reflect --retry-held` to re-enter the gate.
    def hold_observation(self, obs: Observation, path: str, reasons: list) -> str:
        os.makedirs(self.held_dir, exist_ok=True)
        held_path = os.path.join(self.held_dir, os.path.basename(path))
        d = obs.to_yaml_dict()
        d["held_reasons"] = list(reasons)
        with open(held_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(d, f, sort_keys=False, allow_unicode=True)
        self.remove_observation(path)
        return held_path

    def release_held(self) -> list:
        """Move every held observation back into the inbox (dropping the
        embedded reasons). Returns the released inbox paths."""
        released = []
        for p in sorted(glob.glob(os.path.join(self.held_dir, "*.yml"))):
            with open(p, "r", encoding="utf-8") as f:
                d = yaml.safe_load(f.read())
            d.pop("held_reasons", None)
            obs = Observation.from_yaml_dict(d)
            released.append(self.write_observation(obs))
            os.remove(p)
        return released