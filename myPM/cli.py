"""myPM command line. The architecture's verbs, made operable.

    python -m mypm capture  --text "..." --source benchmark --project p --takeaway "..."
    python -m mypm reflect   [--root memory]      # Gate 1
    python -m mypm distill   [--root memory]      # Gate 2 (+ Gate 3 detection)
    python -m mypm retrieve  --task "..." [--project p]
    python -m mypm validate  [--root memory]      # the build pass
    python -m mypm index      [--root memory]
"""

from __future__ import annotations

import argparse
import json
import sys

from .store import Store
from .models import Node, Observation, now_iso, slugify
from .reflect import reflect as run_reflect
from .distill import distill as run_distill
from .retriever import retrieve as run_retrieve
from .validator import validate_all
from .index import build_index


import os as _os
_TEMPLATES_DIR = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "templates")


def _store(args):
    s = Store(args.root)
    s.ensure_layout()
    return s


def cmd_init(args):
    import shutil

    project_id = slugify(args.project or _os.path.basename(_os.path.abspath(".")))
    project_name = args.name or project_id.replace("_", "-")
    description = args.description or f"Engineering knowledge for {project_name}."

    s = Store(args.root)
    s.ensure_layout()
    _os.makedirs(s.project_nodes_dir(project_id), exist_ok=True)

    project_node = Node(
        id=f"project_{project_id}",
        type="project",
        title=project_name,
        scope=f"project:{project_id}",
        status="active",
        body=description,
        fields={
            "name": project_name,
            "description": description,
            "stack": [],
            "repos": [],
            "lifecycle": "active",
        },
    )
    proj_path = s.write_node(project_node)
    print(f"project node   -> {proj_path}")

    # .gitignore: add the index dir so it is never committed
    ignore_entry = f"{args.root}/.index/"
    gi_path = _os.path.join(_os.path.abspath("."), ".gitignore")
    needs_entry = True
    if _os.path.exists(gi_path):
        with open(gi_path, "r", encoding="utf-8") as f:
            needs_entry = ignore_entry not in f.read()
    if needs_entry:
        with open(gi_path, "a", encoding="utf-8") as f:
            f.write(f"\n{ignore_entry}\n")
        print(f".gitignore     -> added {ignore_entry}")

    # .claude/ — install bundled templates, skip files that already exist
    if not _os.path.isdir(_TEMPLATES_DIR):
        print("warning: bundled templates not found; skipping .claude/ installation")
    else:
        claude_dir = _os.path.join(_os.path.abspath("."), ".claude")
        installed, skipped = [], []

        def _install(src, dst):
            if _os.path.exists(dst):
                skipped.append(dst)
            else:
                _os.makedirs(_os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                installed.append(dst)

        for fname in ("CLAUDE.md", "council.md"):
            src = _os.path.join(_TEMPLATES_DIR, fname)
            if _os.path.exists(src):
                _install(src, _os.path.join(claude_dir, fname))

        for subdir in ("agents", "architecture"):
            src_dir = _os.path.join(_TEMPLATES_DIR, subdir)
            dst_dir = _os.path.join(claude_dir, subdir)
            if _os.path.isdir(src_dir):
                for fname in sorted(_os.listdir(src_dir)):
                    if fname.endswith(".md"):
                        _install(_os.path.join(src_dir, fname),
                                 _os.path.join(dst_dir, fname))

        cwd = _os.path.abspath(".")
        for p in installed:
            print(f"installed      -> {_os.path.relpath(p, cwd)}")
        for p in skipped:
            print(f"skipped        -> {_os.path.relpath(p, cwd)}  (already exists)")

    print(f"\ninitialized: {args.root}/  project: {project_id}")
    print(f"next: mypm retrieve --task '<your task>' --project {project_id}")


def cmd_capture(args):
    s = _store(args)
    proposed = {}
    if args.type:
        proposed["type"] = args.type
    fields = {}
    for kv in (args.field or []):
        k, _, v = kv.partition("=")
        fields[k] = v
    if args.takeaway:
        fields["takeaway"] = args.takeaway
    if args.root_cause:
        fields["root_cause"] = args.root_cause
    if args.trigger:
        fields["trigger"] = args.trigger
    if fields:
        proposed["fields"] = fields
    if args.tags:
        proposed["tags"] = [t.strip() for t in args.tags.split(",")]
    if args.motivates:
        proposed.setdefault("links", []).append({"type": "motivates", "to": args.motivates})
    for ln in (args.link or []):
        etype, _, to = ln.partition(":")
        proposed.setdefault("links", []).append({"type": etype, "to": to})

    obs = Observation(
        id=f"obs_{now_iso().replace(':', '').replace('-', '')[:15]}_{slugify(args.text, 3)}",
        text=args.text, source=args.source, project=args.project, proposed=proposed,
    )
    path = s.write_observation(obs)
    print(f"captured observation -> {path}")


def cmd_reflect(args):
    s = _store(args)
    results = run_reflect(s)
    if not results:
        print("inbox empty.")
        return
    for r in results:
        head = "ADMITTED" if r.admitted else "held"
        print(f"[{head}] {r.observation_id}" + (f" -> draft {r.node_id}" if r.node_id else ""))
        for reason in r.reasons:
            print(f"    - {reason}")


def cmd_distill(args):
    s = _store(args)
    rep = run_distill(s)
    if rep.build_errors:
        print("build pass failed; refusing to distill:")
        for e in rep.build_errors:
            print("   ", e)
        sys.exit(1)
    print(f"promoted to active : {rep.promoted or '(none)'}")
    print(f"edges created      : {rep.edges_created or '(none)'}")
    if rep.blocked:
        print("blocked at Gate 2  :")
        for nid, reasons in rep.blocked:
            print(f"    {nid}")
            for reason in reasons:
                print(f"        - {reason}")
    print(f"pattern candidates : {rep.patterns_proposed or '(none)'}")
    print(f"index rebuilt      : {rep.index_path}")


def cmd_retrieve(args):
    s = _store(args)
    bundle = run_retrieve(s, args.task, project=args.project)
    print(json.dumps(bundle.to_dict(), indent=2))


def cmd_validate(args):
    s = _store(args)
    errors, warnings = validate_all(s)
    for w in warnings:
        print(w)
    for e in errors:
        print(e)
    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1 if errors else 0)


def cmd_index(args):
    s = _store(args)
    print("index ->", build_index(s))


def cmd_migrate(args):
    old_root = "memory"
    new_root = args.root  # defaults to "knowledge"

    cwd = _os.path.abspath(".")
    old_path = _os.path.join(cwd, old_root)
    new_path = _os.path.join(cwd, new_root)

    if not _os.path.isdir(old_path):
        if _os.path.isdir(new_path):
            print(f"nothing to migrate: {new_root}/ already exists")
        else:
            print(f"nothing to migrate: {old_root}/ not found")
        return

    if _os.path.exists(new_path):
        print(f"error: both {old_root}/ and {new_root}/ exist; resolve manually before migrating")
        sys.exit(1)

    old_entry = f"{old_root}/.index/"
    new_entry = f"{new_root}/.index/"
    gi_path = _os.path.join(cwd, ".gitignore")

    if args.dry_run:
        print(f"[dry-run] rename  {old_root}/  ->  {new_root}/")
        if _os.path.exists(gi_path):
            with open(gi_path, "r", encoding="utf-8") as f:
                content = f.read()
            if old_entry in content:
                print(f"[dry-run] .gitignore: {old_entry!r}  ->  {new_entry!r}")
            elif new_entry not in content:
                print(f"[dry-run] .gitignore: add {new_entry!r}")
        return

    _os.rename(old_path, new_path)
    print(f"renamed        {old_root}/  ->  {new_root}/")

    if _os.path.exists(gi_path):
        with open(gi_path, "r", encoding="utf-8") as f:
            content = f.read()
        if old_entry in content:
            with open(gi_path, "w", encoding="utf-8") as f:
                f.write(content.replace(old_entry, new_entry))
            print(f".gitignore     {old_entry!r}  ->  {new_entry!r}")
        elif new_entry not in content:
            with open(gi_path, "a", encoding="utf-8") as f:
                f.write(f"\n{new_entry}\n")
            print(f".gitignore     added {new_entry!r}")

    print(f"\nmigrated: {old_root}/  ->  {new_root}/")
    print(f"next: git add -A && git commit -m 'chore: migrate myPM root to {new_root}/'")


def build_parser():
    p = argparse.ArgumentParser(prog="mypm")
    p.add_argument("--root", default="knowledge", help="knowledge root (default: knowledge)")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("capture", help="write a raw observation to the inbox")
    c.add_argument("--text", required=True)
    c.add_argument("--source", default="conversation")
    c.add_argument("--project", default=None)
    c.add_argument("--type", default=None)
    c.add_argument("--takeaway", default=None)
    c.add_argument("--root-cause", dest="root_cause", default=None)
    c.add_argument("--trigger", default=None)
    c.add_argument("--tags", default=None, help="comma-separated")
    c.add_argument("--field", action="append", help="extra field as key=value")
    c.add_argument("--motivates", default=None, help="target node id for a motivates edge")
    c.add_argument("--link", action="append", help="proposed edge as type:target_id")
    c.set_defaults(func=cmd_capture)

    sub.add_parser("reflect", help="Gate 1: admit + type observations into drafts").set_defaults(func=cmd_reflect)
    sub.add_parser("distill", help="Gate 2/3: promote, link, generalize, reindex").set_defaults(func=cmd_distill)

    r = sub.add_parser("retrieve", help="assemble a ContextBundle for a task")
    r.add_argument("--task", required=True)
    r.add_argument("--project", default=None)
    r.set_defaults(func=cmd_retrieve)

    sub.add_parser("validate", help="run the build pass").set_defaults(func=cmd_validate)
    sub.add_parser("index", help="rebuild the SQLite index").set_defaults(func=cmd_index)

    i = sub.add_parser("init", help="initialize a repository with myPM")
    i.add_argument("--project", default=None,
                   help="project id slug (default: current directory name)")
    i.add_argument("--name", default=None,
                   help="human-readable project name (default: derived from project id)")
    i.add_argument("--description", default=None,
                   help="one-line project description")
    i.set_defaults(func=cmd_init)

    m = sub.add_parser("migrate", help="rename memory/ to knowledge/ (one-time migration)")
    m.add_argument("--dry-run", action="store_true",
                   help="preview what would change without applying it")
    m.set_defaults(func=cmd_migrate)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()