"""myPM command line. The architecture's verbs, made operable.

The knowledge root is DISCOVERED: explicit --root, else $MYPM_ROOT, else a
walk up from cwd looking for knowledge/ (the way git finds .git). Only `init`
creates a root; read commands never mkdir.

    python -m mypm init       [--project p]        # the one creating command
    python -m mypm capture    --text "..." --source benchmark --project p --takeaway "..."
    python -m mypm reflect    [--retry-held]       # Gate 1 (LLM proposer if configured)
    python -m mypm distill                         # Gate 2 (+ Gate 3 detection)
    python -m mypm review     [list|fill|approve|reject|merge|supersede|stats] [id]
                              approve --all        # bulk: every draft passing Gate 2
    python -m mypm retrieve   --task "..." [--project p] [--agent role] [--format text]
    python -m mypm orient     [--project p]        # SessionStart hook payload
    python -m mypm show       <node-id>            # one node: fields, body, edges
    python -m mypm search     <terms...>           # lexical search, active + drafts
    python -m mypm feedback   good|bad|partial     # rate the last retrieve
    python -m mypm stats                           # review cost + recall win rate
    python -m mypm doctor                          # diagnose root/index/hooks/extras
    python -m mypm capture-pr [--commit HEAD]      # draft Decision from a merged PR
    python -m mypm hook       install|uninstall    # post-merge auto-capture
    python -m mypm observe    [--transcript p]     # live observer (Claude Code Stop hook)
    python -m mypm council    --task "..."         # EXPERIMENTAL: doctrines as Claude calls
    python -m mypm validate   [--errors-only|--all]
    python -m mypm index

$MYPM_GLOBAL_ROOT points at a shared knowledge repo: its global-scope nodes
ride along in every retrieve/orient/search, so patterns and preferences
genuinely compound across repositories.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import agents, council
from .store import Store
from .models import Node, Observation, now_iso, slugify
from .reflect import reflect as run_reflect
from .distill import distill as run_distill
from .retriever import retrieve as run_retrieve
from .validator import validate_all
from .index import build_index


import os as _os
_TEMPLATES_DIR = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "templates")


def _resolve_root(args):
    """Resolve the knowledge root WITHOUT creating anything.

    Precedence: explicit --root > MYPM_ROOT > walk-up discovery (find_root).
    Returns an absolute path, or None when nothing exists — the caller decides
    whether that is an error (most commands) or a silent no-op (hooks)."""
    from .store import find_root, looks_like_root
    if args.root is not None:                       # explicit flag wins, as-is
        return args.root if _os.path.isdir(args.root) else None
    env = _os.environ.get("MYPM_ROOT")
    if env:
        return env if looks_like_root(env) else None
    return find_root(".")


def _store(args) -> Store:
    """A Store over an EXISTING root, or a remedy and exit 1. Read paths must
    never mkdir: before root discovery existed, a `mypm retrieve` from
    repo/src/ would silently create a stray empty knowledge/ tree there and
    report an empty graph."""
    root = _resolve_root(args)
    if root is None:
        looked = args.root or _os.environ.get("MYPM_ROOT") or \
            f"'{ _os.path.basename(_os.path.abspath('.')) }' and every parent"
        print(f"error: no knowledge root found (looked for {looked})")
        print("  initialize one here:   mypm init")
        print("  or point at one:       mypm --root <path> ...   |   export MYPM_ROOT=<path>")
        sys.exit(1)
    return Store(root)


def _store_quiet(args):
    """Hook-path variant: None instead of an error when no root exists."""
    root = _resolve_root(args)
    return Store(root) if root else None


def _hook_settings():
    """The .claude/settings.json content init generates. One command shape for
    all three hooks: pinned interpreter, hook-safe (`|| true`)."""
    def _cmd(verb, *flags):
        parts = [f'"{sys.executable}"', "-m", "mypm", verb, *flags]
        return " ".join(parts) + " || true"
    return {
        "hooks": {
            "SessionStart": [
                {"hooks": [{"type": "command", "command": _cmd("orient")}]}],
            "Stop": [
                {"hooks": [{"type": "command",
                            "command": _cmd("observe", "--quiet")}]}],
            "SubagentStop": [
                {"hooks": [{"type": "command",
                            "command": _cmd("observe", "--quiet")}]}],
        }
    }


def cmd_init(args):
    import shutil

    project_id = slugify(args.project or _os.path.basename(_os.path.abspath(".")))
    project_name = args.name or project_id.replace("_", "-")
    description = args.description or f"Engineering knowledge for {project_name}."

    # init is the one command that CREATES the root; everything else discovers.
    root = args.root or "knowledge"
    s = Store(root)
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
    ignore_entry = f"{root}/.index/"
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

        # settings.json wires the hooks: Stop/SubagentStop -> `mypm observe`
        # (guaranteed capture) and SessionStart -> `mypm orient` (recall pushed
        # into every session, not hoped for). GENERATED, not copied, so the
        # installing interpreter is pinned — Claude Code hooks do not inherit a
        # venv's PATH, and a bare `mypm` there fails silently forever (the git
        # hook learned this same lesson first). Never merged into an existing
        # settings.json — the user's config wins; we only create, never modify.
        settings_path = _os.path.join(claude_dir, "settings.json")
        if _os.path.exists(settings_path):
            skipped.append(settings_path)
        else:
            _os.makedirs(claude_dir, exist_ok=True)
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(_hook_settings(), f, indent=2)
                f.write("\n")
            installed.append(settings_path)

        for subdir in ("agents", "architecture", "commands"):
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

    print(f"\ninitialized: {root}/  project: {project_id}")
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
    # Anchor to the project node when none of the above linked it, exactly as
    # bootstrap and the observer already do — without one edge the draft can
    # never pass Gate 2, and "capture, reflect, blocked" was the first wall
    # every new user hit.
    if args.project and not proposed.get("links"):
        project_node_id = f"project_{slugify(args.project)}"
        proposed["links"] = [{"type": "relates_to", "to": project_node_id,
                              "note": "captured into this project"}]
        if not _os.path.exists(s.project_file(slugify(args.project))):
            print(f"warning: no project node '{project_node_id}' — the proposed "
                  f"link will dangle. Run: mypm init --project {args.project}")

    import uuid
    obs = Observation(
        # timestamp for human ordering + 6 hex chars so two same-second captures
        # with similar text can never silently overwrite each other
        id=f"obs_{now_iso().replace(':', '').replace('-', '')[:15]}_"
           f"{slugify(args.text, 3)}_{uuid.uuid4().hex[:6]}",
        text=args.text, source=args.source, project=args.project, proposed=proposed,
    )
    path = s.write_observation(obs)
    print(f"captured observation -> {path}")


def cmd_reflect(args):
    s = _store(args)
    results = run_reflect(s, retry_held=args.retry_held)
    if not results:
        print("inbox empty.")
        return
    held_count = 0
    for r in results:
        head = "ADMITTED" if r.admitted else "held"
        print(f"[{head}] {r.observation_id}" + (f" -> draft {r.node_id}" if r.node_id else ""))
        for reason in r.reasons:
            print(f"    - {reason}")
        if r.held_path:
            held_count += 1
            print(f"    quarantined -> {r.held_path}")
    if held_count:
        print(f"\n{held_count} observation(s) quarantined in inbox/held/ — edit the "
              f"file(s), then: mypm reflect --retry-held")


def _gate2_fix_hint(node, reasons):
    """One copy-pasteable command that unblocks this draft — every FAIL names
    its remedy, because 'FAIL linked' with no next step was a dead end."""
    import re as _re
    parts = []
    for r in reasons:
        m = _re.match(r"FAIL substantiated: missing \[(.*)\]", r)
        if m:
            for f in _re.findall(r"'([^']+)'", m.group(1)):
                parts.append(f"--field {f}='...'")
        if r.startswith("FAIL linked"):
            target = (f"project_{node.scope.split(':', 1)[1]}"
                      if node and node.scope.startswith("project:")
                      else "<node-id>")
            parts.append(f"--link relates_to:{target}")
    if not parts:
        return None
    return (f"fix: mypm review approve {node.id} " + " ".join(parts)
            + "   (or `mypm review fill` the same flags to save without promoting)")


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
        nodes_by_id = s.nodes_by_id()
        print("blocked at Gate 2  :")
        for nid, reasons in rep.blocked:
            print(f"    {nid}")
            for reason in reasons:
                print(f"        - {reason}")
            hint = _gate2_fix_hint(nodes_by_id.get(nid), reasons)
            if hint:
                print(f"        {hint}")
    print(f"pattern candidates : {rep.patterns_proposed or '(none)'}")
    print(f"index rebuilt      : {rep.index_path}")


def _global_store(local):
    """The shared cross-repo root (MYPM_GLOBAL_ROOT), when configured and not
    simply the local root again. None means single-root mode."""
    from .store import looks_like_root
    g = _os.environ.get("MYPM_GLOBAL_ROOT")
    if g and looks_like_root(g) \
            and _os.path.abspath(g) != _os.path.abspath(local.root):
        return Store(g)
    return None


def cmd_retrieve(args):
    from . import metrics
    s = _store(args)
    bundle = run_retrieve(s, args.task, project=args.project, agent=args.agent,
                          semantic_weight=args.semantic_weight,
                          global_store=_global_store(s))
    metrics.log_bundle(s, bundle)
    if args.format == "text":
        from .retriever import render_text
        print(render_text(bundle))
        print('rate this recall: mypm feedback good|bad  (tunes nothing yet; '
              'measures everything)')
    else:
        print(json.dumps(bundle.to_dict(), indent=2))


def cmd_orient(args):
    """SessionStart hook payload. Hook-safe: any failure is silence, because a
    traceback injected into every new session is worse than no orientation."""
    try:
        s = _store_quiet(args)
        if s is None:
            return
        from .retriever import orient as run_orient
        text = run_orient(s, project=args.project,
                          global_store=_global_store(s))
        if text:
            print(text)
    except Exception:
        return


def _node_file(s, row):
    if row["type"] == "project":
        return s.project_file(row["scope"].split(":", 1)[1])
    return _os.path.join(s.scope_to_nodes_dir(row["scope"]), row["id"] + ".md")


def cmd_show(args):
    from .index import IndexReader
    s = _store(args)
    stores = [s] + ([_global_store(s)] if _global_store(s) else [])
    row = owner = None
    for st in stores:
        idx = IndexReader(st)
        try:
            row = idx.get_node(args.node_id)
        finally:
            idx.close()
        if row:
            owner = st
            break
    if row is None:
        print(f"no node '{args.node_id}' (try: mypm search <words from its title>)")
        sys.exit(1)

    node = owner.load_node(_node_file(owner, row))
    print(f"{node.id}  [{node.type} / {node.status}]  scope={node.scope}  "
          f"confidence={node.confidence}")
    print(f"title: {node.title}")
    print(f"source: {json.dumps(node.source)}")
    if node.tags:
        print(f"tags: {', '.join(node.tags)}")
    for k, v in node.fields.items():
        print(f"{k}: {v}")
    if node.body.strip():
        print()
        print(node.body.strip())
    idx = IndexReader(owner)
    try:
        outs, ins = idx.out_edges(node.id), idx.in_edges(node.id)
        if outs or ins:
            print()
        for e in outs:
            print(f"  --{e['type']}--> {e['to_id']}")
        for e in ins:
            print(f"  <--{e['type']}-- {e['from_id']}")
        if row["head_id"] != node.id:
            print(f"\nsuperseded by: {row['head_id']}  (mypm show {row['head_id']})")
    finally:
        idx.close()
    print(f"\nfile: {node.path}")


def cmd_search(args):
    from .index import IndexReader
    from .retriever import _tokens, _relevance
    s = _store(args)
    q_tokens = _tokens(" ".join(args.terms))
    rows = []
    for st in [s] + ([_global_store(s)] if _global_store(s) else []):
        idx = IndexReader(st)
        try:
            seen = {r["id"] for r in rows}
            for status in ("active", "draft"):
                rows += [r for r in idx.candidates(idx.scopes(), status=status)
                         if r["id"] not in seen]
        finally:
            idx.close()
    scored = sorted(((r, _relevance(q_tokens, r)) for r in rows),
                    key=lambda x: x[1], reverse=True)
    hits = [(r, sc) for r, sc in scored if sc > 0][:args.limit]
    if not hits:
        print("no matches.")
        return
    for r, sc in hits:
        mark = "" if r["status"] == "active" else f" ({r['status']})"
        print(f"  {sc:0.2f}  [{r['type']}]{mark}  {r['id']}")
        print(f"        {r['title'][:90]}")
    print(f"\ninspect one: mypm show <id>")


WARN_CAP_PER_KIND = 10


def cmd_validate(args):
    s = _store(args)
    errors, warnings = validate_all(s)

    if not args.errors_only:
        # group warnings by kind and cap each group: a six-figure wall of
        # near-duplicate lines teaches people to ignore the build pass
        groups = {}
        for w in warnings:
            groups.setdefault(w.kind or "other", []).append(w)
        for kind in sorted(groups):
            ws = groups[kind]
            shown = ws if args.all else ws[:WARN_CAP_PER_KIND]
            for w in shown:
                print(w)
            if len(ws) > len(shown):
                print(f"[WARNING] ... +{len(ws) - len(shown)} more "
                      f"'{kind}' warning(s) (mypm validate --all shows them)")
    for e in errors:
        print(e)
    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1 if errors else 0)


def cmd_index(args):
    s = _store(args)
    print("index ->", build_index(s))


def cmd_bootstrap(args):
    from . import bootstrap as boot
    if args.enrich:
        from . import claude
        if not claude.available():
            print("--enrich needs the Claude integration: pip install 'mypm-cli[ai]' "
                  "and set ANTHROPIC_API_KEY (or drop --enrich for the free pass).")
            sys.exit(1)
    s = _store(args)
    project = args.project
    if args.write and not project:
        project = slugify(_os.path.basename(_os.path.abspath(args.repo)))
        print(f"(no --project given; defaulting to '{project}')")
    if args.write and project and not _os.path.exists(s.project_file(project)):
        print(f"warning: no project node for '{project}' — candidates will lack a "
              f"graph link and stall at Gate 2. Run: mypm init --project {project}")
    cands = boot.bootstrap(s, repo_dir=args.repo, limit=args.limit,
                           project=project, enrich=args.enrich, write=args.write,
                           model=args.model)

    kept   = [c for c in cands if c.status == "kept"]
    supers = [c for c in cands if c.status == "supersession"]
    dups   = [c for c in cands if c.status == "duplicate"]
    dropped = [c for c in cands if c.status == "dropped"]
    written = kept + supers

    def _row(c):
        tag = {"kept": c.proposal["type"] if c.proposal else "?",
               "supersession": c.proposal["type"] if c.proposal else "?",
               "duplicate": "dup", "dropped": "drop"}.get(c.status, "?")
        note = f"  ({c.reason})" if c.reason else ""
        return f"  {c.status:12} {tag:9} {c.sha}  {c.subject[:57]}{note}"

    print(f"scanned {len(cands)} commits from {args.repo}"
          + ("  [enriched]" if args.enrich else "  [free pass]"))
    print(f"\nCANDIDATES ({len(kept)} novel):")
    for c in kept:
        print(_row(c))
    if supers:
        print(f"\nSUPERSESSIONS ({len(supers)} — likely replace existing decisions):")
        for c in supers:
            print(_row(c))
    if dups:
        print(f"\nDEDUPED ({len(dups)} — already represented):")
        for c in dups:
            print(_row(c))
    if dropped:
        print(f"\nFILTERED ({len(dropped)} — low signal):")
        for c in dropped:
            print(_row(c))

    print(f"\n{len(kept)} novel · {len(supers)} supersede · {len(dups)} deduped · {len(dropped)} filtered")
    if not args.enrich:
        # the free pass only keeps commits whose SUBJECTS carry decision/lesson
        # verbs; on feature/release-style histories it can honestly keep ~zero.
        # Say so, with the escape hatch and its cost, instead of leaving the
        # user with an empty day-1 and no explanation.
        rescuable = [c for c in dropped if c.reason == "no clear decision/lesson"]
        if rescuable and len(written) + len(dups) < max(1, len(cands) // 10):
            print(f"\nthe free pass kept little here: it only types commits whose "
                  f"subjects carry choice/lesson language,\nand {len(rescuable)} "
                  f"prefilter-surviving commit(s) read like features or releases "
                  f"instead. To have Claude type those:\n"
                  f"    mypm bootstrap --limit {args.limit} --enrich "
                  f"{'--write ' if args.write else ''}"
                  f"--model claude-haiku-4-5   "
                  f"(~{len(rescuable) + len(kept) + len(supers)} short calls)")
    if args.write:
        print(f"wrote {len(written)} observation(s) to the inbox; next: mypm reflect")
    else:
        print("(preview only — re-run with --write to land these in the inbox)")


def _parse_fields(field_args):
    fields = {}
    for kv in (field_args or []):
        k, _, v = kv.partition("=")
        fields[k] = v
    return fields


def _parse_links(link_args):
    links = []
    for ln in (link_args or []):
        etype, _, to = ln.partition(":")
        links.append({"type": etype, "to": to})
    return links


def cmd_review(args):
    from . import review

    s = _store(args)

    if args.action == "stats":
        from . import metrics
        _print_review_stats(metrics.stats(s))
        return

    filters = dict(type=args.type, source=args.source, project=args.project)

    if args.action in (None, "list"):
        drafts = review.pending(s, **filters)
        if not drafts:
            print("nothing pending — no drafts await review."
                  + ("  (filters active)" if any(filters.values()) else ""))
            return
        ready = sum(1 for d in drafts if d.ready)
        print(f"{len(drafts)} draft(s) pending ({ready} ready to approve as-is):\n")
        for d in drafts:
            print(f"  {d.node_id}  [{d.type}]  {d.title[:60]}")
            needs = []
            if d.missing_fields:
                needs.append(f"missing fields: {', '.join(d.missing_fields)}")
            if not d.linked:
                needs.append("no graph link")
            print(f"      needs: {'; '.join(needs) if needs else 'nothing — ready to approve'}")
        if args.action is None:
            _review_interactive(s, review, drafts)
        else:
            print("\nfill:      mypm review fill <id> --field root_cause='...'   (saves, never promotes)")
            print("approve:   mypm review approve <id> --field root_cause='...'")
            print("           mypm review approve --all   (every draft already passing Gate 2)")
            print("reject:    mypm review reject <id>")
            print("merge:     mypm review merge <id> --into <existing-id>")
            print("supersede: mypm review supersede <id> --replaces <old-id>")
            print("stats:     mypm review stats   (time-to-decision, filled vs bare)")
        return

    if args.action == "approve" and args.all:
        promoted, skipped = review.approve_ready(s, **filters)
        for nid in promoted:
            print(f"promoted {nid} -> active")
        for nid, reasons in skipped:
            print(f"skipped  {nid}: "
                  + "; ".join(r for r in reasons if r.startswith("FAIL")))
        print(f"\n{len(promoted)} promoted, {len(skipped)} still need a human "
              f"({'mypm review' if skipped else 'done'})")
        return

    if not args.node_id:
        print(f"error: '{args.action}' needs a node id (or `approve --all`)")
        sys.exit(1)

    try:
        if args.action == "fill":
            missing = review.fill(s, args.node_id,
                                  fields=_parse_fields(args.field),
                                  links=_parse_links(args.link))
            print(f"saved (still a draft)")
            if missing:
                print(f"still needs: {', '.join(missing)}")
            else:
                print("complete — ready for human approval (mypm review approve "
                      f"{args.node_id} or mypm distill)")
        elif args.action == "approve":
            ok, reasons, created = review.approve(s, args.node_id,
                                                  fields=_parse_fields(args.field),
                                                  links=_parse_links(args.link))
            if ok:
                print(f"promoted {args.node_id} -> active")
                for e in created:
                    print(f"  edge: {e}")
            else:
                print(f"still blocked at Gate 2 (supplied fields were saved):")
                for r in reasons:
                    print(f"  - {r}")
                hint = _gate2_fix_hint(s.nodes_by_id().get(args.node_id), reasons)
                if hint:
                    print(f"  {hint}")
                sys.exit(1)
        elif args.action == "reject":
            path = review.reject(s, args.node_id)
            print(f"rejected; removed {path}")
        elif args.action == "merge":
            if not args.into:
                print("error: merge needs --into <existing-node-id>")
                sys.exit(1)
            target = review.merge(s, args.node_id, args.into)
            print(f"merged {args.node_id} into {target}")
        elif args.action == "supersede":
            if not args.replaces:
                print("error: supersede needs --replaces <old-node-id>")
                sys.exit(1)
            ok, reasons, created = review.supersede(
                s, args.node_id, args.replaces, fields=_parse_fields(args.field),
                links=_parse_links(args.link))
            if ok:
                print(f"promoted {args.node_id}; {args.replaces} is now superseded")
                for e in created:
                    print(f"  edge: {e}")
            else:
                print("still blocked at Gate 2 (supersedes link was saved):")
                for r in reasons:
                    print(f"  - {r}")
                sys.exit(1)
    except ValueError as e:
        print(f"error: {e}")
        sys.exit(1)


def cmd_feedback(args):
    from . import metrics
    s = _store(args)
    task = metrics.log_feedback(s, args.verdict, note=args.note or "")
    if task is None:
        print("no bundle to rate yet — run a retrieve first.")
        sys.exit(1)
    print(f"recorded: {args.verdict} for the last recall ('{task[:60]}...')"
          if len(task) > 60 else
          f"recorded: {args.verdict} for the last recall ('{task}')")


def cmd_stats(args):
    """The two loops, measured: what promotion costs (review) and whether
    recall earns its keep (bundles -> ratings -> citations)."""
    from . import metrics
    s = _store(args)

    print("== the write path: review")
    _print_review_stats(metrics.stats(s))

    r = metrics.recall_stats(s)
    print("\n== the read path: recall")
    if not r["bundles"]:
        print("no bundles logged yet — recall telemetry starts with the first "
              "mypm retrieve.")
        return
    print(f"bundles produced : {r['bundles']}")
    if r["verdicts"]:
        v = ", ".join(f"{k} {n}" for k, n in sorted(r["verdicts"].items()))
        wr = f"{r['win_rate']:.0%}" if r["win_rate"] is not None else "n/a"
        print(f"human ratings    : {v}   (win rate: {wr})")
    else:
        print("human ratings    : none yet — mypm feedback good|bad after a retrieve")
    cr = f"{r['citation_rate']:.0%}" if r["citation_rate"] is not None else "n/a"
    print(f"bundles cited    : {r['bundles_cited']} of {r['bundles']} ({cr}) — "
          f"a later session named one of the bundle's nodes")
    print(f"distinct nodes cited: {r['nodes_cited']}")


def _print_review_stats(report):
    """The adoption metric: does fill turn a 2-minute approval into a
    10-second one? Two cohorts, side by side."""
    if not report["decisions"]:
        print("no review decisions logged yet — decisions are timed "
              "automatically once you review (interactive or per-verb).")
        return

    verbs = ", ".join(f"{n} {v}" for v, n in sorted(report["by_verb"].items()))
    print(f"{report['decisions']} decision(s) logged ({verbs})\n")

    def _s(x):
        return f"{x:.1f}s" if x is not None else "-"

    def _f(x):
        return f"{x:.1f}" if x is not None else "-"

    print(f"{'cohort':<16}{'n':>4}{'timed':>7}{'median':>9}{'mean':>9}"
          f"{'fields typed':>14}")
    for label, key in (("filled first", "filled"), ("bare draft", "unfilled")):
        c = report[key]
        print(f"{label:<16}{c['n']:>4}{c['timed']:>7}{_s(c['median_s']):>9}"
              f"{_s(c['mean_s']):>9}{_f(c['mean_fields_typed']):>14}")
    print("\n(median/mean cover timed decisions only — those shown in "
          "interactive review; 'fields typed' is what the human supplied "
          "at decision time.)")


def _show_draft(d):
    """Print what the human is actually approving: the content and its
    provenance, not just a title and a list of gaps. An authorship gate where
    the author cannot see the text is a rubber stamp."""
    print(f"\n--- {d.node_id}  [{d.type}]  "
          f"(source: {d.source.get('type', '?')}, {d.scope})")
    print(f"    {d.title}")
    for k, v in d.fields.items():
        v = " ".join(str(v).split())
        print(f"      {k}: {v[:120]}")
    body = " ".join(d.body.split())
    if body and body not in (d.title,):
        print(f"      | {body[:240]}")
    for reason in d.reasons:
        print(f"    {reason}")


def _review_interactive(s, review, drafts):
    """Walk pending drafts one at a time. Plain input(); quits cleanly on EOF."""
    import subprocess
    from . import metrics

    print("\ninteractive review — [a]pprove [r]eject [m]erge [s]upersede "
          "[e]dit [k]skip [q]uit")
    for d in drafts:
        _show_draft(d)
        # starts the time-to-decision clock for `review stats`
        metrics.log_event(s, "shown", d.node_id)
        try:
            choice = input("    action [a/r/m/s/e/k/q]> ").strip().lower()
        except EOFError:
            return
        if choice == "q":
            return
        if choice in ("", "k"):
            continue
        try:
            if choice == "a":
                fields = {}
                for f in d.missing_fields:
                    val = input(f"    {f} (';' separates list items)> ").strip()
                    if val:
                        fields[f] = val
                links = []
                if not d.linked:
                    default = (f"relates_to:project_{d.scope.split(':', 1)[1]}"
                               if d.scope.startswith("project:") else "")
                    raw = input(f"    link (type:node-id)"
                                + (f" [{default}]" if default else "")
                                + "> ").strip() or default
                    if raw:
                        etype, _, to = raw.partition(":")
                        links.append({"type": etype, "to": to})
                ok, reasons, _ = review.approve(s, d.node_id, fields=fields,
                                                links=links)
                print(f"    {'promoted -> active' if ok else 'still blocked: ' + '; '.join(r for r in reasons if r.startswith('FAIL'))}")
            elif choice == "r":
                review.reject(s, d.node_id)
                print("    rejected")
            elif choice == "m":
                into = input("    merge into node id> ").strip()
                if into:
                    review.merge(s, d.node_id, into)
                    print(f"    merged into {into}")
            elif choice == "s":
                old = input("    supersedes node id> ").strip()
                if old:
                    ok, reasons, _ = review.supersede(s, d.node_id, old)
                    print(f"    {'promoted; old node superseded' if ok else 'still blocked: ' + '; '.join(r for r in reasons if r.startswith('FAIL'))}")
            elif choice == "e" and d.path:
                editor = _os.environ.get("EDITOR", "vi")
                subprocess.call([editor, d.path])
        except ValueError as e:
            print(f"    error: {e}")


def cmd_doctor(args):
    """Diagnose the wiring. Every silent-by-design path (hooks especially) gets
    a loud check here — silence is a feature in a hook and a bug in a doctor."""
    import shutil

    failed = warned = False

    def ok(area, msg):
        print(f"  ok    {area:<14} {msg}")

    def warn(area, msg, fix=None):
        nonlocal warned
        warned = True
        print(f"  warn  {area:<14} {msg}")
        if fix:
            print(f"        {'':<14} fix: {fix}")

    def fail(area, msg, fix=None):
        nonlocal failed
        failed = True
        print(f"  FAIL  {area:<14} {msg}")
        if fix:
            print(f"        {'':<14} fix: {fix}")

    # -- root ---------------------------------------------------------------
    root = _resolve_root(args)
    if root is None:
        fail("root", "no knowledge root found from here",
             "mypm init   |   mypm --root <path> doctor   |   export MYPM_ROOT=<path>")
        print("\n1 failure — fix the root first; the other checks need it.")
        sys.exit(1)
    s = Store(root)
    ok("root", root)

    nodes = s.all_nodes()
    by_status = {}
    for n in nodes:
        by_status[n.status] = by_status.get(n.status, 0) + 1
    inbox = len(s.all_observations())
    import glob as _glob
    held = len(_glob.glob(_os.path.join(s.held_dir, "*.yml")))
    edges = len(_glob.glob(_os.path.join(s.edges_dir, "*.yml")))
    ok("graph", f"{by_status.get('active', 0)} active, "
                f"{by_status.get('draft', 0)} draft, "
                f"{by_status.get('superseded', 0)} superseded · {edges} edges "
                f"· inbox {inbox} (+{held} held)")
    if by_status.get("draft", 0) > 25:
        warn("graph", f"{by_status['draft']} drafts pending review",
             "mypm review   (or /enrich-drafts then bulk-approve)")

    # -- index --------------------------------------------------------------
    from .index import IndexReader
    if not _os.path.exists(s.index_path):
        warn("index", "not built yet (first retrieve builds it)", "mypm index")
    elif IndexReader._stale(s):
        warn("index", "stale (self-heals on next retrieve)", "mypm index")
    else:
        ok("index", "fresh")

    # -- validate -----------------------------------------------------------
    errors, warnings = validate_all(s)
    if errors:
        fail("validate", f"{len(errors)} error(s)", "mypm validate")
    elif warnings:
        warn("validate", f"{len(warnings)} warning(s)", "mypm validate")
    else:
        ok("validate", "clean")

    # -- hooks: git post-merge ----------------------------------------------
    from . import githook
    repo = githook.repo_root()
    if repo is None:
        warn("git-hook", "not inside a git repository")
    else:
        hp = githook.hook_path(repo)
        if not _os.path.exists(hp):
            warn("git-hook", "post-merge capture hook not installed",
                 "mypm hook install")
        else:
            with open(hp, "r", encoding="utf-8") as f:
                ok("git-hook", "installed (ours)") if githook.HOOK_MARKER in f.read() \
                    else warn("git-hook", "a foreign post-merge hook is present",
                              "mypm hook install --force  (replaces it)")

    # -- hooks: Claude Code settings.json ------------------------------------
    settings = _os.path.join(repo or _os.path.abspath("."), ".claude", "settings.json")
    if not _os.path.exists(settings):
        warn("claude-hooks", ".claude/settings.json missing — live observer "
             "and session recall are not wired", "mypm init  (creates it)")
    else:
        try:
            with open(settings, "r", encoding="utf-8") as f:
                text = f.read()
            cfg = json.loads(text)
        except (OSError, json.JSONDecodeError) as e:
            fail("claude-hooks", f"settings.json unreadable: {e}")
            cfg, text = {}, ""
        import shlex
        cmds = []
        for entries in (cfg.get("hooks") or {}).values():
            for entry in entries or []:
                for h in (entry.get("hooks") or []):
                    c = h.get("command", "")
                    if "mypm" in c:
                        cmds.append(c)
        if not cmds:
            warn("claude-hooks", "settings.json exists but wires no mypm hooks",
                 "add Stop/SubagentStop -> mypm observe, SessionStart -> mypm orient")
        else:
            # the failure this check exists for: a bare `mypm` in a hook
            # command resolves against Claude Code's PATH, not your venv's
            broken = []
            for c in cmds:
                try:
                    exe = shlex.split(c)[0]
                except ValueError:
                    exe = c.split()[0] if c.split() else ""
                if not (_os.path.isabs(exe) and _os.path.exists(exe)) \
                        and shutil.which(exe) is None:
                    broken.append(exe)
            if broken:
                fail("claude-hooks", f"hook executable not resolvable: "
                     f"{sorted(set(broken))} — the hooks fail silently",
                     "regenerate with a pinned interpreter: "
                     "rm .claude/settings.json && mypm init")
            elif not any("orient" in c for c in cmds):
                warn("claude-hooks", "observe wired, but no SessionStart orient "
                     "hook (recall is not pushed into sessions)",
                     "rm .claude/settings.json && mypm init  (or add it by hand)")
            else:
                ok("claude-hooks", "observe + orient wired, executables resolve")

    # -- AI + semantic extras -------------------------------------------------
    from . import claude as _claude
    if _os.environ.get("MYPM_NO_LLM"):
        ok("claude", "disabled by MYPM_NO_LLM (deterministic substrate)")
    elif _claude.available():
        ok("claude", "available (proposer, --enrich, council)")
    else:
        warn("claude", "unavailable — rule-based typing only",
             "pip install 'mypm-cli[ai]' && export ANTHROPIC_API_KEY=...")
    if _os.environ.get("MYPM_NO_SEMANTIC"):
        ok("semantic", "disabled by MYPM_NO_SEMANTIC (lexical retrieval)")
    else:
        try:
            import sentence_transformers  # noqa: F401
            ok("semantic", "local embeddings available")
        except ImportError:
            warn("semantic", "lexical retrieval only (synonym misses possible)",
                 "pip install 'mypm-cli[semantic]'")

    # -- global root ----------------------------------------------------------
    groot = _os.environ.get("MYPM_GLOBAL_ROOT")
    if groot:
        from .store import looks_like_root
        if looks_like_root(groot):
            ok("global-root", groot)
        else:
            fail("global-root", f"MYPM_GLOBAL_ROOT={groot} is not a knowledge root",
                 "point it at a directory created by mypm init")
    else:
        ok("global-root", "not set (single-root mode; set MYPM_GLOBAL_ROOT to "
                          "share global knowledge across repos)")

    print()
    if failed:
        print("doctor: failures found — the marked items are broken right now.")
        sys.exit(1)
    print("doctor: healthy" + (" (with warnings)" if warned else "") + ".")


def cmd_observe(args):
    """Hook-safe by construction: exits 0 no matter what (a non-zero exit from
    a Stop hook would block the session from stopping), creates nothing in
    repos that don't use myPM, and says nothing unless asked."""
    from . import observe as obs_mod

    root = _resolve_root(args)
    if root is None:
        return                                   # not a myPM repo: silent no-op

    transcript, session = args.transcript, None
    if not transcript:
        try:
            payload = json.load(sys.stdin)       # Claude Code hook input
        except (json.JSONDecodeError, OSError):
            return
        transcript = payload.get("transcript_path")
        session = payload.get("session_id")
    if not transcript or not _os.path.exists(transcript):
        return

    try:
        s = Store(root)
        results = obs_mod.observe(s, transcript, session=session)
    except Exception as e:
        if not args.quiet:
            print(f"observe: {e}")
        return

    captured = [r for r in results if r.status == "captured"]
    if args.quiet:
        return
    if not results:
        print("observe: no capture blocks found.")
        return
    for r in results:
        note = f"  ({r.reason})" if r.reason else ""
        print(f"  {r.status:9} {r.title[:60]}{note}")
    if captured:
        print(f"\n{len(captured)} observation(s) to the inbox; next: mypm reflect")


def cmd_council(args):
    from . import claude, council
    if not claude.available():
        print("Claude integration unavailable. To run the council:")
        print("  - pip install 'mypm-cli[ai]'")
        print("  - export ANTHROPIC_API_KEY=...   (and unset MYPM_NO_LLM if set)")
        sys.exit(1)
    s = _store(args)
    try:
        names = council.resolve_agents(args.agents, args.preset)
    except ValueError as e:
        print(f"error: {e}")
        sys.exit(1)
    print(f"council: {' -> '.join(names)}  (task: {args.task})")
    turns = council.run_council(s, args.task, names, project=args.project)
    for t in turns:
        print(f"\n===== {t.agent} ({t.command}) — {t.mandate} =====\n")
        print(t.output)
        for r in (t.captured or []):
            if r.status == "captured":
                print(f"\n  [captured -> inbox] {r.title}")


def cmd_capture_pr(args):
    from . import githook
    s = _store(args)
    project = args.project or slugify(_os.path.basename(_os.path.abspath(".")))
    path = githook.capture_pr(s, project=project, commit=args.commit,
                              allow_plain=args.any_merge)
    if path:
        print(f"captured draft Decision from merge -> {path}")
        print("next: mypm reflect   # Gate 1: type it into a draft")
    elif not args.quiet:
        print(f"no PR merge at {args.commit}; nothing captured")


def cmd_hook(args):
    from . import githook
    repo = githook.repo_root() or _os.path.abspath(".")
    if args.action == "install":
        # the hook script runs from the repo root, so embed the root relative
        # to it (portable when the checkout moves); discovery finds it first
        knowledge_root = _store(args).root
        try:
            rel = _os.path.relpath(knowledge_root, repo)
            if not rel.startswith(".."):
                knowledge_root = rel
            path, action = githook.install_hook(repo, knowledge_root,
                                                force=args.force)
        except ValueError as e:
            print(f"error: {e}")
            sys.exit(1)
        if action == "skipped":
            print(f"a post-merge hook already exists and is not myPM's: {path}")
            print("re-run with --force to replace it")
            sys.exit(1)
        print(f"{action}       -> {path}")
        print("merges into this repo will now capture draft Decisions to the inbox")
    else:  # uninstall
        result = githook.uninstall_hook(repo)
        msg = {"removed": "removed post-merge hook",
               "absent": "no post-merge hook to remove",
               "foreign": "post-merge hook is not myPM's; left untouched"}[result]
        print(msg)


def cmd_migrate(args):
    old_root = "memory"
    new_root = args.root or "knowledge"

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
    from . import __version__
    p = argparse.ArgumentParser(prog="mypm")
    p.add_argument("--version", action="version", version=f"mypm {__version__}")
    p.add_argument("--root", default=None,
                   help="knowledge root (default: $MYPM_ROOT, else walk up "
                        "from cwd looking for knowledge/)")
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

    rf = sub.add_parser("reflect", help="Gate 1: admit + type observations into drafts")
    rf.add_argument("--retry-held", dest="retry_held", action="store_true",
                    help="re-run quarantined observations from inbox/held/")
    rf.set_defaults(func=cmd_reflect)
    sub.add_parser("distill", help="Gate 2/3: promote, link, generalize, reindex").set_defaults(func=cmd_distill)

    rv = sub.add_parser("review", help="approve/reject/merge/supersede pending drafts")
    rv.add_argument("action", nargs="?", default=None,
                    choices=("list", "fill", "approve", "reject", "merge",
                             "supersede", "stats"),
                    help="omit for interactive review; 'fill' saves fields "
                         "without promoting; 'stats' prices the human gate")
    rv.add_argument("node_id", nargs="?", default=None)
    rv.add_argument("--field", action="append",
                    help="fill a field as key=value (';' separates list items)")
    rv.add_argument("--link", action="append",
                    help="propose an edge as type:target_id (saved, not materialized)")
    rv.add_argument("--into", default=None, help="merge target node id")
    rv.add_argument("--replaces", default=None, help="node id this draft supersedes")
    rv.add_argument("--all", action="store_true",
                    help="with approve: promote every draft already passing Gate 2")
    rv.add_argument("--type", default=None, choices=("decision", "lesson",
                    "pattern", "component", "preference"),
                    help="filter pending drafts by node type")
    rv.add_argument("--source", default=None,
                    help="filter by source type (pr, commit, observer, ...)")
    rv.add_argument("--project", default=None, help="filter by project id")
    rv.set_defaults(func=cmd_review)

    ob = sub.add_parser("observe",
                        help="capture mypm-capture blocks from a session transcript "
                             "(wired as a Claude Code Stop hook by mypm init)")
    ob.add_argument("--transcript", default=None,
                    help="transcript path (omit when run as a hook: read from stdin JSON)")
    ob.add_argument("--quiet", action="store_true", help="hook mode: never print")
    ob.set_defaults(func=cmd_observe)

    r = sub.add_parser("retrieve", help="assemble a ContextBundle for a task")
    r.add_argument("--task", required=True)
    r.add_argument("--project", default=None)
    r.add_argument("--agent", default=None, choices=agents.AGENT_NAMES,
                   help="bias ranking toward this agent's declared reads")
    r.add_argument("--semantic-weight", dest="semantic_weight", type=float, default=None,
                   help="semantic share of the seed blend, 0-1 (default: lexical-first 0.2)")
    r.add_argument("--format", default="json", choices=("json", "text"),
                   help="json for models (default), text for humans")
    r.set_defaults(func=cmd_retrieve)

    o = sub.add_parser("orient",
                       help="compact orientation bundle (the SessionStart hook payload)")
    o.add_argument("--project", default=None)
    o.set_defaults(func=cmd_orient)

    sh = sub.add_parser("show", help="display one node: fields, body, edges, lineage")
    sh.add_argument("node_id")
    sh.set_defaults(func=cmd_show)

    se = sub.add_parser("search", help="lexical search over the graph (active + drafts)")
    se.add_argument("terms", nargs="+")
    se.add_argument("--limit", type=int, default=10)
    se.set_defaults(func=cmd_search)

    fb = sub.add_parser("feedback",
                        help="rate the most recent retrieve (the Recall Win Rate KPI)")
    fb.add_argument("verdict", choices=("good", "bad", "partial"))
    fb.add_argument("--note", default=None)
    fb.set_defaults(func=cmd_feedback)

    sub.add_parser("stats",
                   help="both loops measured: review cost + recall win/citation rate"
                   ).set_defaults(func=cmd_stats)

    v = sub.add_parser("validate", help="run the build pass")
    v.add_argument("--errors-only", dest="errors_only", action="store_true",
                   help="suppress warnings (CI mode)")
    v.add_argument("--all", action="store_true",
                   help="show every warning instead of capping per kind")
    v.set_defaults(func=cmd_validate)
    sub.add_parser("index", help="rebuild the SQLite index").set_defaults(func=cmd_index)
    sub.add_parser("doctor",
                   help="diagnose the wiring: root, index, hooks, extras"
                   ).set_defaults(func=cmd_doctor)

    i = sub.add_parser("init", help="initialize a repository with myPM")
    i.add_argument("--project", default=None,
                   help="project id slug (default: current directory name)")
    i.add_argument("--name", default=None,
                   help="human-readable project name (default: derived from project id)")
    i.add_argument("--description", default=None,
                   help="one-line project description")
    i.set_defaults(func=cmd_init)

    b = sub.add_parser("bootstrap", help="seed the inbox with candidates from git history")
    b.add_argument("--repo", default=".", help="repo to read git log from (default: cwd)")
    b.add_argument("--limit", type=int, default=20, help="how many recent commits to scan")
    b.add_argument("--project", default=None, help="project scope for candidates")
    b.add_argument("--enrich", action="store_true",
                   help="use the LLM to type novel survivors (costs tokens; off by default)")
    b.add_argument("--model", default=None, help="model for --enrich (e.g. claude-haiku-4-5)")
    b.add_argument("--write", action="store_true",
                   help="write candidates to the inbox (default: preview only)")
    b.set_defaults(func=cmd_bootstrap)

    co = sub.add_parser("council",
                        help="EXPERIMENTAL: run agent doctrines as sequential "
                             "Claude calls (needs ANTHROPIC_API_KEY; one full "
                             "recall+completion per agent — mind the bill). "
                             "The doctrines also work as plain Claude Code "
                             "subagents, which is the supported path.")
    co.add_argument("--task", required=True)
    co.add_argument("--project", default=None)
    co.add_argument("--agents", default=None,
                    help="comma-separated agent names (overrides --preset)")
    co.add_argument("--preset", default=None, choices=sorted(council.PRESETS),
                    help=f"agent assembly (default: {council.DEFAULT_PRESET})")
    co.set_defaults(func=cmd_council)

    cp = sub.add_parser("capture-pr", help="capture a draft Decision from a merged PR")
    cp.add_argument("--project", default=None,
                    help="project scope (default: current directory name)")
    cp.add_argument("--commit", default="HEAD", help="commit to inspect (default: HEAD)")
    cp.add_argument("--any-merge", action="store_true",
                    help="also capture plain branch merges, not just PR merges")
    cp.add_argument("--quiet", action="store_true", help="say nothing when skipping")
    cp.set_defaults(func=cmd_capture_pr)

    h = sub.add_parser("hook", help="install/remove the post-merge capture hook")
    h.add_argument("action", choices=("install", "uninstall"))
    h.add_argument("--force", action="store_true",
                   help="replace an existing non-myPM post-merge hook")
    h.set_defaults(func=cmd_hook)

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