"""Tests for bin/fx. Run from plugins/factory: python3 -m unittest discover -s tests -v

They build a throwaway origin + clone, install the factory into it, swap the
tracker and forge for in-memory fakes, and play the agents' parts by writing
their files. Adapter tests talk to a local HTTP server and a fake `gh`.
"""
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout, redirect_stderr
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

PKG = Path(__file__).resolve().parents[1]
FX = PKG / "bin" / "fx"
loader = importlib.machinery.SourceFileLoader("fx", str(FX))
spec = importlib.util.spec_from_loader("fx", loader)
fx = importlib.util.module_from_spec(spec)
loader.exec_module(fx)


def run(*args, cwd):
    return subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True).stdout.strip()


class FakeTracker:
    kind = "jira"
    prefix = None

    def __init__(self):
        self.issues, self.comments_, self.labels_ = {}, {}, {}
        self.transitions, self.created, self.next_id = [], [], 1000

    def add(self, key, title, body="", labels=("factory",), reporter="rep", components=()):
        self.issues[key] = {"title": title, "body": body, "reporter": reporter, "components": list(components)}
        self.labels_[key] = set(labels)
        self.comments_.setdefault(key, [])

    def queue(self):
        return [{"key": k, "title": v["title"]} for k, v in self.issues.items() if "factory" in self.labels_[k]]

    def in_queue(self, key):
        return key in self.issues and "factory" in self.labels_[key]

    def issue(self, key):
        i = self.issues[key]
        return {"key": key, "title": i["title"], "body": i["body"], "type": "Story", "status": "To Do",
                "labels": sorted(self.labels_[key]), "components": i["components"], "priority": "", "parent": "",
                "reporter_id": i["reporter"], "reporter": i["reporter"], "url": f"https://jira/browse/{key}"}

    def comments(self, key):
        return list(self.comments_.get(key, []))

    def me(self, key=None):
        return "op"

    def comment(self, key, body, author="op"):
        self.next_id += 1
        self.comments_.setdefault(key, []).append({"id": self.next_id, "author_id": author, "author": author,
                                                   "created": "now", "body": body})
        return self.next_id

    def labels(self, key, add=(), remove=()):
        s = self.labels_.setdefault(key, set())
        s.update(add)
        s.difference_update(remove)

    def transition(self, key, which):
        self.transitions.append((key, which))
        return True

    def create(self, title, body, labels, parent=None, project=None, issue_type=None):
        key = f"{project or 'ABC'}-{100 + len(self.created)}"
        self.add(key, title, body, labels)
        self.created.append((key, parent))
        return key

    def url_for(self, key):
        return f"https://jira/browse/{key}"

    def closing_line(self, key):
        return f"**Jira:** {key}"


class FakeForge:
    kind, word = "gitlab", "MR"

    def __init__(self):
        self.mrs, self.notes = {}, []

    def find(self, branch, base):
        for m in self.mrs.values():
            if m["branch"] == branch and m["state"] == "open":
                return dict(m)
        return None

    def create(self, branch, base, title, body, labels, draft=True):
        iid = len(self.mrs) + 1
        self.mrs[iid] = {"iid": iid, "url": f"https://gl/mr/{iid}", "state": "open", "draft": draft,
                         "branch": branch, "title": title, "body": body, "labels": set(labels)}
        return dict(self.mrs[iid])

    def update(self, iid, title=None, body=None, draft=None, add_labels=()):
        m = self.mrs[iid]
        if title is not None:
            m["title"] = title
        if body is not None:
            m["body"] = body
        if draft is not None:
            m["draft"] = draft
        m["labels"].update(add_labels)

    def get(self, iid):
        return dict(self.mrs[iid])

    def note(self, iid, body):
        self.notes.append((iid, body))

    def close(self, iid):
        self.mrs[iid]["state"] = "closed"

    def ping(self):
        return "fake"


CHECKS = """#!/usr/bin/env bash
set -euo pipefail
if grep -q BROKEN app.py; then echo "test_app FAILED: app is broken"; exit 1; fi
echo "all good"
"""


class FactoryCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.origin = self.tmp / "origin.git"
        run("git", "init", "--quiet", "--bare", "-b", "main", str(self.origin), cwd=self.tmp)
        self.root = self.tmp / "repo"
        run("git", "clone", "--quiet", str(self.origin), str(self.root), cwd=self.tmp)
        for k, v in (("user.email", "t@t"), ("user.name", "t")):
            run("git", "config", k, v, cwd=self.root)
        run("git", "checkout", "--quiet", "-b", "main", cwd=self.root)
        os.environ["FX_ROOT"] = str(self.root)
        with redirect_stdout(io.StringIO()):
            fx.init_cmd(self.root, "work", False)
        cfg = json.loads((self.root / "factory/config.json").read_text())
        cfg["jira"]["transitions"] = {"started": "In Progress", "ready": "In Review", "merged": None}
        (self.root / "factory/config.json").write_text(json.dumps(cfg))
        (self.root / "factory/checks.sh").write_text(CHECKS)
        (self.root / "app.py").write_text("def add(a, b):\n    return a + b\n")
        run("git", "add", "-A", cwd=self.root)
        run("git", "commit", "--quiet", "-m", "init", cwd=self.root)
        run("git", "push", "--quiet", "-u", "origin", "main", cwd=self.root)
        self.tracker, self.forge = FakeTracker(), FakeForge()
        self.p1 = mock.patch.object(fx, "make_tracker", lambda *a, **k: self.tracker)
        self.p2 = mock.patch.object(fx, "make_forge", lambda *a, **k: self.forge)
        self.p1.start()
        self.p2.start()

    def tearDown(self):
        self.p1.stop()
        self.p2.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)
        os.environ.pop("FX_ROOT", None)

    # helpers
    def fx(self):
        return fx.Fx(self.root)

    def step(self, key):
        f = self.fx()
        out = f.step(key)
        return f.log + out

    def jd(self, key):
        return self.root / "factory" / "jobs" / key

    def job(self, key):
        return json.loads((self.jd(key) / "job.json").read_text())

    def write(self, key, name, text):
        p = self.jd(key) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def intake(self, key, lane="feature", risk="low", surfaces="none", decision="ACCEPT", skills="none",
               extra=""):
        self.write(key, "intake.md", f"DECISION: {decision}\nLANE: {lane}\nRISK: {risk}\nSURFACES: {surfaces}\n"
                                     f"TYPE: feat\nSLUG: add subtract\nTITLE: Add subtract\nSKILLS: {skills}\n\n"
                                     f"## Summary\n- adds subtract\n\n{extra}")

    def build(self, key, content="def sub(a, b):\n    return a - b\n", status="READY", skills="none", commit=True):
        job = self.job(key)
        wt = Path(job["worktree"])
        if commit:
            with open(wt / "app.py", "a") as fh:
                fh.write(content)
            run("git", "add", "-A", cwd=wt)
            run("git", "commit", "--quiet", "-m", f"{key}: change r{job['round']}", cwd=wt)
        self.write(key, "build.md", f"STATUS: {status}\nROUND: {job['round']}\nSKILLS: {skills}\n\n"
                                    f"## What\nAdds sub.\n\n## Blocked\nNeed a decision on X.\n")

    def gate(self, key):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.fx().gate(key)
        return buf.getvalue()

    def review(self, key, r, verdict="PASS", skills="none"):
        n = self.job(key)["round"]
        self.write(key, f"round-{n}/review-{r}.md", f"VERDICT: {verdict}\nSKILLS: {skills}\n\n## Summary\n- ok\n\n"
                                                    f"## Findings\n- [major] app.py:1 — x → y\n")

    def start(self, key="ABC-1", title="Add subtract"):
        self.tracker.add(key, title, "Please add a subtract function")
        with redirect_stdout(io.StringIO()):
            self.fx().create(key)
        return key


class TestHappyPaths(FactoryCase):
    def test_feature_lane_end_to_end(self):
        k = self.start()
        self.assertIn("AGENT factory:intake | model=sonnet", "\n".join(self.step(k)))
        issue = (self.jd(k) / "issue.md").read_text()
        self.assertIn("<<<DATA-", issue)
        self.assertIn("Please add a subtract function", issue)

        self.intake(k, lane="feature", risk="medium", surfaces="ui")
        out = "\n".join(self.step(k))
        self.assertIn("AGENT factory:spec-writer | model=opus", out)
        job = self.job(k)
        self.assertEqual(job["branch"], "ABC-1-feat/add-subtract")
        self.assertEqual(job["reviewers"], {"code": "sonnet", "ui": "sonnet", "docs": "sonnet"})
        self.assertTrue((Path(job["worktree"]) / ".git").exists())
        self.assertIn(("ABC-1", "started"), self.tracker.transitions)

        self.write(k, "spec.md", "SPEC: READY\nSKILLS: none\n\n## Summary\n- x\n")
        out = "\n".join(self.step(k))
        self.assertIn("AGENT factory:builder | model=sonnet | name=builder-ABC-1", out)
        self.assertNotIn("resume=yes", out)
        self.assertIn("Commit messages: ABC-1: <short summary>.", out)
        self.assertIn("work from spec.md", out)

        self.build(k)
        out = self.step(k)
        self.assertEqual(out[-1], "NEXT gate")
        mr = self.forge.mrs[1]
        self.assertTrue(mr["draft"])
        self.assertEqual(mr["title"], "ABC-1: Add subtract")
        self.assertIn("Adds sub.", mr["body"])
        self.assertIn(run("git", "rev-parse", "HEAD", cwd=self.job(k)["worktree"]),
                      run("git", "ls-remote", "origin", "ABC-1-feat/add-subtract", cwd=self.root))

        self.assertIn("GATE: PASS", self.gate(k))
        out = "\n".join(self.step(k))
        self.assertIn("AGENT factory:reviewer-code | model=sonnet", out)
        self.assertIn("AGENT factory:reviewer-ui | model=sonnet", out)
        self.assertIn("Port: 5111.", out)

        self.review(k, "code")
        out = "\n".join(self.step(k))
        self.assertIn("AGENT factory:reviewer-ui", out)
        self.assertNotIn("factory:reviewer-code", out)
        self.assertIn("AGENT factory:reviewer-docs | model=sonnet", out)
        self.assertIn("Docs: changelog CHANGELOG.md; ADRs in docs/adr.", out)
        self.review(k, "ui")
        self.review(k, "docs")
        out = self.step(k)
        self.assertTrue(out[-1].startswith("NEXT wait ready"))
        self.assertFalse(self.forge.mrs[1]["draft"])
        self.assertIn("factory-in-review", self.forge.mrs[1]["labels"])
        self.assertIn(("ABC-1", "ready"), self.tracker.transitions)
        self.assertTrue(any("Ready for human review" in n for _, n in self.forge.notes))

        self.forge.mrs[1]["state"] = "merged"
        lines = self.fx().queue()
        self.assertIn("done ABC-1 merged", lines)
        self.assertEqual(self.job(k)["stage"], "merged")
        self.assertFalse(Path(self.job(k)["worktree"]).exists())

    def test_hotfix_lane_skips_spec_and_routes_cheap(self):
        k = self.start()
        self.step(k)
        self.intake(k, lane="hotfix", risk="low")
        out = "\n".join(self.step(k))
        self.assertIn("AGENT factory:builder | model=sonnet", out)
        self.assertIn("work from issue.md and intake.md", out)
        self.assertEqual(self.job(k)["reviewers"], {"code": "haiku"})
        self.assertEqual(self.job(k)["round_limit"], 2)

    def test_builder_is_sonnet_even_at_high_risk_unless_configured(self):
        k = self.start()
        self.step(k)
        self.intake(k, lane="feature", risk="high", surfaces="security, data")
        self.step(k)
        job = self.job(k)
        self.assertEqual(job["models"]["builder"], "sonnet")
        self.assertEqual(job["reviewers"], {"code": "opus", "security": "opus", "data": "sonnet", "docs": "sonnet"})


class TestLoops(FactoryCase):
    def to_build(self, lane="hotfix"):
        k = self.start()
        self.step(k)
        self.intake(k, lane=lane)
        self.step(k)
        return k

    def test_gate_failure_returns_to_builder_with_log(self):
        k = self.to_build()
        self.build(k, content="# BROKEN\n")
        self.step(k)
        out = self.gate(k)
        self.assertIn("GATE: FAIL", out)
        checks = (self.jd(k) / "round-1/checks.md").read_text()
        self.assertIn("test_app FAILED", checks)
        out = "\n".join(self.step(k))
        self.assertIn("resume=yes", out)
        self.assertIn("read round-1/checks.md", out)
        self.assertEqual(self.job(k)["round"], 2)

    def test_protected_paths_fail_the_gate(self):
        k = self.to_build()
        wt = Path(self.job(k)["worktree"])
        (wt / "factory/checks.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
        self.build(k)
        self.step(k)
        out = self.gate(k)
        self.assertIn("GATE: FAIL", out)
        self.assertIn("factory/checks.sh", out)

    def test_branch_cannot_edit_the_checks_it_is_judged_by(self):
        k = self.to_build()
        wt = Path(self.job(k)["worktree"])
        (wt / "factory/checks.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
        self.build(k, content="# BROKEN\n")
        self.step(k)
        self.assertIn("GATE: FAIL", self.gate(k))
        self.assertIn("test_app FAILED", (self.jd(k) / "round-1/checks.md").read_text())

    def test_review_changes_then_max_rounds_escalates(self):
        k = self.to_build()
        for n in (1, 2):
            self.build(k, content=f"# change {n}\n")
            self.step(k)
            self.gate(k)
            self.step(k)
            self.review(k, "code", "CHANGES")
            out = self.step(k)
        self.assertEqual(self.job(k)["stage"], "needs-human")
        self.assertIn("used all 2 build rounds", self.job(k)["escalation"])
        self.assertIn("factory-needs-human", self.tracker.labels_[k])
        self.assertTrue(out[-1].startswith("NEXT wait needs-human"))

        with redirect_stdout(io.StringIO()):
            self.fx().feedback(k, "Use a lambda instead.")
        job = self.job(k)
        self.assertEqual((job["stage"], job["round"], job["round_limit"]), ("build", 3, 4))
        self.assertTrue(self.forge.mrs[1]["draft"])
        out = "\n".join(self.step(k))
        self.assertIn("read feedback-1.md", out)

    def test_sensitive_paths_are_flagged_on_the_mr(self):
        k = self.to_build()
        wt = Path(self.job(k)["worktree"])
        (wt / "deploy").mkdir()
        (wt / "deploy/prod.yml").write_text("replicas: 2\n")
        self.build(k)
        self.step(k)
        self.gate(k)
        self.step(k)
        self.review(k, "code")
        self.step(k)
        self.assertIn("factory-sensitive", self.forge.mrs[1]["labels"])
        self.assertIn("deploy/prod.yml", self.forge.mrs[1]["body"])

    def test_conflicts_with_base_send_the_job_back(self):
        k = self.to_build()
        self.build(k, content="def sub(a, b):\n    return a - b\n")
        self.step(k)
        self.gate(k)
        self.step(k)
        (self.root / "app.py").write_text("def add(a, b):\n    return a + b\ndef mul(a, b):\n    return a * b\n")
        run("git", "commit", "--quiet", "-am", "other change", cwd=self.root)
        run("git", "push", "--quiet", "origin", "main", cwd=self.root)
        self.review(k, "code")
        out = "\n".join(self.step(k))
        self.assertIn("no longer merges cleanly", out)
        self.assertEqual(self.job(k)["stage"], "build")

    def test_builder_refusals_retry_once_then_escalate(self):
        k = self.to_build()
        self.build(k, commit=False)
        out = "\n".join(self.step(k))
        self.assertIn("no commits ahead", out)
        self.assertTrue((self.jd(k) / "build.md.refused-1").exists())
        self.build(k, commit=False)
        self.step(k)
        self.assertEqual(self.job(k)["stage"], "needs-human")

    def test_blocked_builder_escalates_with_question(self):
        k = self.to_build()
        self.build(k, status="BLOCKED", commit=False)
        self.step(k)
        self.assertEqual(self.job(k)["stage"], "needs-human")
        self.assertIn("Need a decision on X", self.job(k)["escalation"])


class TestIntakeAndQueue(FactoryCase):
    def test_needs_info_waits_for_reporter_then_reruns_intake(self):
        k = self.start()
        self.step(k)
        self.intake(k, decision="NEEDS-INFO", extra="## Question\n1. Which module?\n")
        out = self.step(k)
        self.assertEqual(out[-1], "NEXT wait needs-info (question posted on the issue)")
        self.assertIn("Which module?", self.tracker.comments_[k][-1]["body"])
        self.assertIn("factory-needs-info", self.tracker.labels_[k])
        self.tracker.comment(k, "[factory] my own note", author="op")
        self.tracker.comment(k, "Some stranger", author="mallory")
        self.assertEqual(self.step(k)[-1], "NEXT wait needs-info (question posted on the issue)")
        self.tracker.comment(k, "The math module.", author="rep")
        self.assertIn(f"step {k} needs-info (reply arrived)", self.fx().queue())
        out = "\n".join(self.step(k))
        self.assertIn("AGENT factory:intake", out)
        self.assertTrue((self.jd(k) / "intake-1.md").exists())
        issue = (self.jd(k) / "issue.md").read_text()
        self.assertIn("The math module.", issue)
        self.assertNotIn("Some stranger", issue)

    def test_reject_removes_queue_label(self):
        k = self.start()
        self.step(k)
        self.intake(k, decision="REJECT", extra="## Reason\nNot this repo.\n")
        self.assertEqual(self.step(k), ["ABC-1 intake -> rejected: Not this repo.", "NEXT done rejected"])
        self.assertNotIn("factory", self.tracker.labels_[k])

    def test_queue_respects_concurrency_and_trust_boundary(self):
        for i in range(1, 4):
            self.tracker.add(f"ABC-{i}", f"Item {i}")
        self.tracker.add("ABC-9", "Unlabeled", labels=())
        lines = self.fx().queue()
        self.assertEqual([l.split()[0] for l in lines], ["start", "start", "hold", "slots"])
        with redirect_stdout(io.StringIO()):
            self.fx().create("ABC-1")
            self.fx().create("ABC-2")
        with self.assertRaises(fx.FxError):
            self.fx().create("ABC-3")
        with self.assertRaises(fx.FxError):
            self.fx().create("ABC-9")

    def test_operator_reject_closes_mr(self):
        k = self.start()
        self.step(k)
        self.intake(k, lane="hotfix")
        self.step(k)
        self.build(k)
        self.step(k)
        with redirect_stdout(io.StringIO()):
            self.fx().reject(k, "Superseded.")
        self.assertEqual(self.job(k)["stage"], "rejected")
        self.assertEqual(self.forge.mrs[1]["state"], "closed")
        self.assertEqual(self.step(k), ["NEXT done rejected"])


class TestEpic(FactoryCase):
    PLAN = """PLAN: READY
SKILLS: none

## Summary
- two stories

```json
{"stories": [
  {"title": "Add table", "description": "Create table", "acceptance": ["exists"], "depends_on": []},
  {"title": "Export CSV", "description": "Export it", "lane": "feature", "depends_on": [0]}
]}
```
"""

    def test_plan_review_approval_creates_children_with_dependencies(self):
        k = self.start(title="Audit log")
        self.step(k)
        self.intake(k, lane="epic", risk="medium")
        self.assertIn("AGENT factory:planner | model=opus", "\n".join(self.step(k)))
        self.write(k, "plan.md", self.PLAN)
        self.assertTrue(self.step(k)[-1].startswith("NEXT wait plan-review"))
        with redirect_stdout(io.StringIO()):
            self.fx().approve_plan(k)
        self.assertEqual(self.job(k)["stage"], "planned")
        self.assertEqual([c[1] for c in self.tracker.created], [k, k])
        a, b = [c[0] for c in self.tracker.created]
        lines = self.fx().queue()
        self.assertIn(f"blocked {b} (waits on {a})", lines)
        self.assertTrue(any(l.startswith(f"start {a}") for l in lines))
        self.assertIn("## Acceptance criteria", self.tracker.issues[a]["body"])

    def test_bad_plan_is_refused(self):
        k = self.start()
        self.step(k)
        self.intake(k, lane="epic")
        self.step(k)
        self.write(k, "plan.md", "PLAN: READY\nSKILLS: none\n\n```json\n{\"stories\": [{\"title\": \"x\"}]}\n```\n")
        out = "\n".join(self.step(k))
        self.assertIn("needs title and description", out)


class TestSkills(FactoryCase):
    def enable(self, roles):
        cfg = json.loads((self.root / "factory/config.json").read_text())
        cfg["skills"]["library"] = {"name": "acme", "install": None, "update": None, "verify": "true",
                                    "protected_paths": [".claude/skills/acme-*/**"]}
        cfg["skills"]["roles"] = roles
        (self.root / "factory/config.json").write_text(json.dumps(cfg))
        for name in {n for v in roles.values() for n in v if "*" not in n}:
            d = self.root / ".claude/skills" / name
            d.mkdir(parents=True, exist_ok=True)
            (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n---\nbody\n")

    def test_off_by_default_and_toggle(self):
        k = self.start()
        self.assertIn("Skills: none.", "\n".join(self.step(k)))
        self.enable({"builder": ["acme-dev-story"], "reviewer-code": ["acme-review"]})
        with redirect_stdout(io.StringIO()) as buf:
            rc = fx.skills_cmd(self.fx(), "on")
        self.assertEqual(rc, 0, buf.getvalue())
        f = self.fx()
        self.assertIn(".claude/skills/acme-*/**", f.protected())
        self.assertEqual(f.role_skills("builder"), ["acme-dev-story"])
        with redirect_stdout(io.StringIO()):
            fx.skills_cmd(self.fx(), "off")
        self.assertEqual(self.fx().role_skills("builder"), [])
        self.assertFalse((self.root / ".claude/agents").exists(), "plugin mode never writes agent files")

    def test_pins_not_installed_here_are_skipped_unless_strict(self):
        self.enable({"builder": ["acme-dev-story"]})
        cfg = json.loads((self.root / "factory/config.json").read_text())
        cfg["skills"]["roles"]["spec-writer"] = ["acme-ghost"]
        (self.root / "factory/config.json").write_text(json.dumps(cfg))
        with redirect_stdout(io.StringIO()) as buf:
            rc = fx.skills_cmd(self.fx(), "on")
        self.assertEqual(rc, 0)
        self.assertIn("not installed here: acme-ghost", buf.getvalue())
        self.assertEqual(self.fx().role_skills("spec-writer"), [])
        cfg["skills"]["strict"] = True
        cfg["skills"]["enabled"] = True
        (self.root / "factory/config.json").write_text(json.dumps(cfg))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(fx.skills_cmd(self.fx(), "check"), 1)

    def test_patterns_resolve_and_resync_when_the_library_changes(self):
        self.enable({"reviewer-code": ["acme-*review*"], "builder": ["acme-dev-story"]})
        (self.root / ".valhalla.lock").write_text("v1")
        cfg = json.loads((self.root / "factory/config.json").read_text())
        cfg["skills"]["library"]["lock_file"] = ".valhalla.lock"
        (self.root / "factory/config.json").write_text(json.dumps(cfg))
        d = self.root / ".claude/skills/acme-code-review"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("---\nname: acme-code-review\ndescription: >\n  Review code against\n  the standards\n---\n")
        with redirect_stdout(io.StringIO()):
            fx.skills_cmd(self.fx(), "on")
        self.assertEqual(self.fx().role_skills("reviewer-code"), ["acme-code-review"])
        f = self.fx()
        self.assertEqual(f.queue()[-1], "slots 0/2")
        self.assertFalse(any("re-synced" in l for l in f.log))
        d2 = self.root / ".claude/skills/acme-ui-review"
        d2.mkdir()
        (d2 / "SKILL.md").write_text("---\nname: acme-ui-review\ndescription: UI review\n---\n")
        (self.root / ".valhalla.lock").write_text("v2")
        f = self.fx()
        f.queue()
        self.assertTrue(any("re-synced" in l and "acme-ui-review" in l for l in f.log), f.log)
        self.assertEqual(self.fx().role_skills("reviewer-code"), ["acme-code-review", "acme-ui-review"])
        with redirect_stdout(io.StringIO()) as buf:
            fx.skills_cmd(self.fx(), "catalog")
        self.assertIn("Review code against the standards", buf.getvalue())

    def test_discover_mode_is_announced_in_prompts(self):
        self.enable({})
        with redirect_stdout(io.StringIO()):
            fx.skills_cmd(self.fx(), "on")
        k = self.start()
        out = "\n".join(self.step(k))
        self.assertIn("Skills: none. Discover skills: yes (acme).", out)

    def test_enforcement_refuses_output_without_required_skills(self):
        self.enable({"builder": ["acme-dev-story"]})
        with redirect_stdout(io.StringIO()):
            fx.skills_cmd(self.fx(), "on")
        k = self.start()
        self.step(k)
        self.intake(k, lane="hotfix")
        out = "\n".join(self.step(k))
        self.assertIn("Skills: acme-dev-story.", out)
        self.build(k, skills="none")
        out = "\n".join(self.step(k))
        self.assertIn("required skills on its SKILLS line: acme-dev-story", out)
        self.build(k, skills="acme-dev-story", commit=False)
        self.assertEqual(self.step(k)[-1], "NEXT gate")

    def test_library_paths_are_protected_when_on(self):
        self.enable({"builder": ["acme-dev-story"]})
        with redirect_stdout(io.StringIO()):
            fx.skills_cmd(self.fx(), "on")
        run("git", "add", "-A", cwd=self.root)
        run("git", "commit", "--quiet", "-m", "skills", cwd=self.root)
        run("git", "push", "--quiet", cwd=self.root)
        k = self.start()
        self.step(k)
        self.intake(k, lane="hotfix")
        self.step(k)
        wt = Path(self.job(k)["worktree"])
        (wt / ".claude/skills/acme-dev-story/SKILL.md").write_text("tampered")
        self.build(k, skills="acme-dev-story")
        self.step(k)
        self.assertIn(".claude/skills/acme-dev-story/SKILL.md", self.gate(k))


class TestGuard(FactoryCase):
    def guard(self, role, tool, **inp):
        stdin = io.StringIO(json.dumps({"tool_name": tool, "tool_input": inp}))
        err = io.StringIO()
        with mock.patch.object(sys, "stdin", stdin), redirect_stderr(err):
            rc = fx.guard(self.fx(), role)
        return rc, err.getvalue()

    def test_builder_rules(self):
        wt = self.root / ".worktrees" / "ABC-1"
        self.assertEqual(self.guard("builder", "Bash", command="pytest -q && git commit -am x")[0], 0)
        self.assertEqual(self.guard("builder", "Bash", command="git merge origin/main")[0], 0)
        for cmd in ("git push origin HEAD", "git -C x push", "git rebase origin/main", "git reset --hard HEAD~1",
                    "git checkout main", "glab mr merge 3", "git commit --amend && git push --force"):
            self.assertEqual(self.guard("builder", "Bash", command=cmd)[0], 2, cmd)
        self.assertEqual(self.guard("builder", "Edit", file_path=str(wt / "src/app.py"))[0], 0)
        self.assertEqual(self.guard("builder", "Write", file_path=str(self.jd("ABC-1") / "build.md"))[0], 0)
        rc, msg = self.guard("builder", "Edit", file_path=str(wt / "factory/checks.sh"))
        self.assertEqual(rc, 2)
        self.assertIn("protected", msg)
        self.assertEqual(self.guard("builder", "Write", file_path=str(self.root / "app.py"))[0], 2)

    def test_reviewer_rules(self):
        self.assertEqual(self.guard("reviewer-code", "Bash", command="git -C /x diff --stat origin/main...HEAD")[0], 0)
        self.assertEqual(self.guard("reviewer-code", "Bash", command="git log --oneline")[0], 0)
        self.assertEqual(self.guard("reviewer-code", "Bash", command="git commit -am fix")[0], 2)
        self.assertEqual(self.guard("reviewer-code", "Bash", command="git checkout -b x")[0], 2)
        p = self.jd("ABC-1") / "round-1" / "review-code.md"
        self.assertEqual(self.guard("reviewer-code", "Write", file_path=str(p))[0], 0)
        self.assertEqual(self.guard("intake", "Write", file_path=str(self.root / "app.py"))[0], 2)


class TestHelpers(unittest.TestCase):
    def test_glob(self):
        m = fx.matching
        self.assertEqual(m(["migrations/1.sql", "db/migrations/2.sql", "src/x.py"], ["**/migrations/**"]),
                         ["migrations/1.sql", "db/migrations/2.sql"])
        self.assertEqual(m(["factory/bin/fx", "factoryx"], ["factory/**"]), ["factory/bin/fx"])
        self.assertEqual(m(["a/Dockerfile.prod", "Dockerfile"], ["**/Dockerfile*"]), ["a/Dockerfile.prod", "Dockerfile"])
        self.assertEqual(m([".claude/agents/fx-builder.md", ".claude/agents/other.md"], [".claude/agents/fx-*.md"]),
                         [".claude/agents/fx-builder.md"])

    def test_remote_parsing(self):
        self.assertEqual(fx.parse_remote("git@gitlab.acme.io:team/sub/app.git"), ("gitlab.acme.io", "team/sub/app"))
        self.assertEqual(fx.parse_remote("ssh://git@gitlab.acme.io:2222/team/app.git"), ("gitlab.acme.io", "team/app"))
        self.assertEqual(fx.parse_remote("https://oauth2:tok@gitlab.com/a/b"), ("gitlab.com", "a/b"))

    def test_jira_markup(self):
        self.assertEqual(fx.md_to_jira("## Hi\n- `x` **b** [l](https://e.x)"), "h2. Hi\n* {{x}} *b* [l|https://e.x]")

    def test_frontmatter_rewrite(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.md"
            p.write_text("---\nname: a\nskills:\n  - old\nmodel: opus\n---\nbody\n")
            fx.set_frontmatter_list(p, "skills", ["x", "y"])
            self.assertEqual(p.read_text(), '---\nname: a\nmodel: opus\nskills: ["x", "y"]\n---\nbody\n')
            fx.set_frontmatter_list(p, "skills", [])
            self.assertEqual(p.read_text(), "---\nname: a\nmodel: opus\n---\nbody\n")


class Recorder(BaseHTTPRequestHandler):
    routes, calls = {}, []

    def _do(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n)) if n else None
        Recorder.calls.append((self.command, self.path, body, dict(self.headers)))
        key = (self.command, self.path.split("?")[0])
        resp = Recorder.routes.get(key, {})
        if callable(resp):
            resp = resp(body, self.path)
        data = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = do_PUT = _do

    def log_message(self, *a):
        pass


class TestAdapters(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Recorder)
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        Recorder.calls.clear()
        Recorder.routes.clear()

    def test_jira_cloud_search_paginates_and_comments(self):
        pages = iter([{"issues": [{"key": "A-1", "fields": {"summary": "one"}}], "nextPageToken": "t2"},
                      {"issues": [{"key": "A-2", "fields": {"summary": "two"}}], "isLast": True}])
        Recorder.routes[("POST", "/rest/api/2/search/jql")] = lambda b, p: next(pages)
        Recorder.routes[("POST", "/rest/api/2/issue/A-1/comment")] = {"id": "10042"}
        Recorder.routes[("GET", "/rest/api/2/issue/A-1/transitions")] = {
            "transitions": [{"id": "31", "name": "Start", "to": {"name": "In Progress"}}]}
        cfg = fx.deep_merge(fx.DEFAULTS, {"jira": {"url": self.url, "jql": "labels = factory",
                                                   "transitions": {"started": "In Progress"}}})
        env = {"JIRA_EMAIL": "me@x", "JIRA_API_TOKEN": "tok"}
        with mock.patch.dict(os.environ, env):
            j = fx.JiraTracker(cfg)
            self.assertEqual([i["key"] for i in j.queue()], ["A-1", "A-2"])
            self.assertEqual(j.comment("A-1", "## Hi\n- `x`"), 10042)
            self.assertTrue(j.transition("A-1", "started"))
            j.labels("A-1", add=["f-x"], remove=["f-y"])
        searches = [c for c in Recorder.calls if c[1] == "/rest/api/2/search/jql"]
        self.assertEqual(searches[1][2]["nextPageToken"], "t2")
        self.assertTrue(searches[0][3]["Authorization"].startswith("Basic "))
        comment = next(c for c in Recorder.calls if c[1].endswith("/comment"))
        self.assertEqual(comment[2], {"body": "h2. Hi\n* {{x}}"})
        self.assertIn(("POST", "/rest/api/2/issue/A-1/transitions", {"transition": {"id": "31"}}),
                      [c[:3] for c in Recorder.calls])
        self.assertIn({"update": {"labels": [{"add": "f-x"}, {"remove": "f-y"}]}}, [c[2] for c in Recorder.calls])

    def test_jira_datacenter_uses_bearer_and_offset_search(self):
        Recorder.routes[("POST", "/rest/api/2/search")] = {"issues": [{"key": "B-1", "fields": {"summary": "x"}}],
                                                           "total": 1}
        cfg = fx.deep_merge(fx.DEFAULTS, {"jira": {"url": self.url, "deployment": "server", "jql": "x"}})
        with mock.patch.dict(os.environ, {"JIRA_API_TOKEN": "pat"}):
            self.assertEqual(fx.JiraTracker(cfg).queue()[0]["key"], "B-1")
        self.assertEqual(Recorder.calls[0][3]["Authorization"], "Bearer pat")

    def test_gitlab_mr_lifecycle(self):
        base = "/api/v4/projects/team%2Fapp"
        Recorder.routes[("POST", base + "/merge_requests")] = {"iid": 7, "web_url": "u", "state": "opened",
                                                                "draft": True}
        Recorder.routes[("GET", base + "/merge_requests/7")] = {"iid": 7, "web_url": "u", "state": "merged"}
        with tempfile.TemporaryDirectory() as d:
            run("git", "init", "--quiet", d, cwd=d)
            run("git", "remote", "add", "origin", "git@gitlab.acme.io:team/app.git", cwd=d)
            cfg = fx.deep_merge(fx.DEFAULTS, {"gitlab": {"url": self.url}})
            with mock.patch.dict(os.environ, {"GITLAB_TOKEN": "glpat"}):
                g = fx.GitLabForge(cfg, Path(d))
                mr = g.create("ABC-1-feat/x", "main", "ABC-1: X", "body", ["factory"], draft=True)
                g.update(7, title="ABC-1: X", body="b2", draft=False, add_labels=["factory-in-review"])
                self.assertEqual(g.get(7)["state"], "merged")
        self.assertEqual(mr["iid"], 7)
        create = Recorder.calls[0]
        self.assertEqual(create[2]["title"], "Draft: ABC-1: X")
        self.assertEqual(create[3]["Private-Token"], "glpat")
        self.assertEqual(Recorder.calls[1][2], {"title": "ABC-1: X", "description": "b2",
                                                "add_labels": "factory-in-review"})

    def test_github_adapters_via_fake_gh(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "gh.log"
            ghs = Path(d) / "gh"
            ghs.write_text(f"""#!{sys.executable}
import json, sys
args = sys.argv[1:]
body = sys.stdin.read() if "--input" in args else ""
open({str(log)!r}, "a").write(json.dumps([args, body]) + "\\n")
path = args[3] if args[:1] == ["api"] else ""
if path.startswith("repos/me/app/issues?"):
    print(json.dumps([{{"number": 4, "title": "Fix it"}}, {{"number": 5, "title": "PR", "pull_request": {{}}}}]))
elif path == "repos/me/app/pulls":
    print(json.dumps({{"number": 9, "html_url": "https://github.com/me/app/pull/9", "state": "open", "draft": True}}))
elif path == "repos/me/app/pulls/9":
    print(json.dumps({{"number": 9, "state": "closed", "merged_at": "2026-11-20T00:00:00Z"}}))
else:
    print("{{}}")
""")
            ghs.chmod(0o755)
            run("git", "init", "--quiet", d, cwd=d)
            run("git", "remote", "add", "origin", "git@github.com:me/app.git", cwd=d)
            cfg = fx.deep_merge(fx.DEFAULTS, fx.PROFILES["personal"])
            with mock.patch.dict(os.environ, {"PATH": f"{d}:{os.environ['PATH']}"}):
                t = fx.GitHubTracker(cfg, Path(d))
                self.assertEqual(t.queue(), [{"key": "GH-4", "title": "Fix it"}])
                self.assertEqual(t.closing_line("GH-4"), "Closes #4")
                f = fx.GitHubForge(cfg, Path(d))
                pr = f.create("feat/gh-4-x", "main", "Fix it", "Closes #4", ["factory"], draft=True)
                f.update(9, draft=False)
                self.assertEqual(f.get(9)["state"], "merged")
            calls = [json.loads(l) for l in log.read_text().splitlines()]
        self.assertEqual(pr["iid"], 9)
        create = next(c for c in calls if c[0][3] == "repos/me/app/pulls")
        self.assertEqual(json.loads(create[1])["draft"], True)
        self.assertIn(["pr", "ready", "9", "--repo", "me/app"], [c[0] for c in calls])


class TestInitProfiles(unittest.TestCase):
    def test_personal_profile_naming(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            run("git", "init", "--quiet", d, cwd=d)
            with redirect_stdout(io.StringIO()):
                fx.init_cmd(root, "personal", False)
            cfg = json.loads((root / "factory/config.json").read_text())
            self.assertEqual((cfg["tracker"], cfg["forge"]), (["local", "github"], "github"))
            self.assertIn("/factory/jobs/", (root / ".gitignore").read_text())
            with mock.patch.dict(os.environ, {"FX_ROOT": d}):
                f = fx.Fx(root)
            job = {"key": "GH-12", "type": "fix", "slug": "null-check", "title": "Handle null"}
            self.assertEqual(f.fmt(f.cfg["branch_template"], job), "fix/gh-12-null-check")
            self.assertEqual(f.fmt(f.cfg["commit_template"], job), "fix: <short summary> (#12)")
            self.assertFalse(f.skills_on())
            with self.assertRaises(fx.FxError):
                fx.init_cmd(root, "work", False)


class TestBriefs(FactoryCase):
    SPEC = ("SPEC: READY\nSKILLS: none\nSOURCE: vision brief subtract\n\n## Summary\n- add sub\n\n"
            "## Acceptance criteria\n1. sub(3, 1) == 2\n")

    def brief(self, text=None):
        p = self.root / "factory/briefs/subtract/spec.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text or self.SPEC)
        return p

    def file(self, **kw):
        with redirect_stdout(io.StringIO()) as buf:
            key = self.fx().file(kw.pop("title", "Add subtract"), kw.pop("text", ""), **kw)
        return key, buf.getvalue()

    def test_filed_spec_skips_the_spec_writer(self):
        key, out = self.file(spec=str(self.brief()))
        self.assertIn(f"filed {key}", out)
        body = self.tracker.issues[key]["body"]
        self.assertIn("sub(3, 1) == 2", body)
        self.assertNotIn("SPEC: READY", body)
        self.assertIn("factory", self.tracker.labels_[key])
        self.assertEqual((self.root / f"factory/specs/{key}.md").read_text(), self.SPEC)
        with redirect_stdout(io.StringIO()):
            self.fx().create(key)
        self.assertEqual(self.job(key)["spec_source"], "brief")
        self.assertEqual((self.jd(key) / "spec.md").read_text(), self.SPEC)
        self.step(key)
        self.intake(key, lane="feature")
        out = "\n".join(self.step(key))
        self.assertIn("AGENT factory:builder", out)
        self.assertNotIn("factory:spec-writer", out)
        self.assertIn("work from spec.md", out)

    def test_drafts_are_refused(self):
        p = self.brief("SPEC: DRAFT\nSKILLS: none\n\n## Open questions\n- which module?\n")
        with self.assertRaises(fx.FxError):
            self.file(spec=str(p))
        self.assertEqual(self.tracker.created, [])

    def test_hold_then_release(self):
        key, out = self.file(spec=str(self.brief()), hold=True)
        self.assertIn(f"fx release {key}", out)
        self.assertNotIn("factory", self.tracker.labels_[key])
        self.assertFalse(any(key in l for l in self.fx().queue()))
        with redirect_stdout(io.StringIO()):
            self.fx().release([key])
        self.assertTrue(any(l.startswith(f"start {key}") for l in self.fx().queue()))

    def test_epic_with_ordered_stories(self):
        epic, _ = self.file(title="Audit export", text="Overview", issue_type="Epic", hold=True)
        a, _ = self.file(title="API", spec=str(self.brief()), parent=epic)
        b, out = self.file(title="UI", spec=str(self.brief()), parent=epic, after=a)
        self.assertIn(f"after {a}", out)
        self.assertEqual([c[1] for c in self.tracker.created], [None, epic, epic])
        lines = self.fx().queue()
        self.assertIn(f"blocked {b} (waits on {a})", lines)
        self.assertFalse(any(epic in l for l in lines))

    def test_brief_spec_is_not_held_to_spec_writer_pins(self):
        cfg = json.loads((self.root / "factory/config.json").read_text())
        cfg["skills"]["enabled"] = True
        cfg["skills"]["library"] = {"name": "acme", "verify": None}
        cfg["skills"]["roles"] = {"spec-writer": ["acme-story"]}
        (self.root / "factory/config.json").write_text(json.dumps(cfg))
        d = self.root / ".claude/skills/acme-story"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("---\nname: acme-story\ndescription: x\n---\n")
        key, _ = self.file(spec=str(self.brief()))
        with redirect_stdout(io.StringIO()):
            self.fx().create(key)
        self.step(key)
        self.intake(key, lane="feature")
        self.assertIn("AGENT factory:builder", "\n".join(self.step(key)))


class TestWorkspace(unittest.TestCase):
    """A Valhalla-style workspace: a plain folder holding several repos, the factory at its root."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = self.tmp / "ssp"
        self.ws.mkdir()
        for name in ("backend", "frontend"):
            origin = self.tmp / f"{name}.git"
            run("git", "init", "--quiet", "--bare", "-b", "main", str(origin), cwd=self.tmp)
            seed = self.tmp / f"seed-{name}"
            run("git", "init", "--quiet", "-b", "main", str(seed), cwd=self.tmp)
            for k, v in (("user.email", "t@t"), ("user.name", "t")):
                run("git", "config", k, v, cwd=seed)
            (seed / "app.py").write_text(f"# {name}\n")
            run("git", "add", "-A", cwd=seed)
            run("git", "commit", "--quiet", "-m", "init", cwd=seed)
            run("git", "push", "--quiet", str(origin), "main", cwd=seed)
            run("git", "clone", "--quiet", str(origin), str(self.ws / name), cwd=self.tmp)
            for k, v in (("user.email", "t@t"), ("user.name", "t")):
                run("git", "config", k, v, cwd=self.ws / name)
        (self.ws / "_val").mkdir()
        (self.ws / ".valhalla.lock").write_text("lock")
        os.environ["FX_ROOT"] = str(self.ws)
        with redirect_stdout(io.StringIO()) as buf:
            fx.init_cmd(self.ws, "work", False)
        self.init_out = buf.getvalue()
        cfg = json.loads((self.ws / "factory/config.json").read_text())
        cfg["repos"]["backend"]["match"]["components"] = ["Backend"]
        (self.ws / "factory/config.json").write_text(json.dumps(cfg))
        for name in ("backend", "frontend"):
            (self.ws / "factory/checks" / f"{name}.sh").write_text(CHECKS.replace("all good", f"{name} good"))
        self.tracker, self.forges = FakeTracker(), {}

        def forge(cfg, root, *a, **k):
            return self.forges.setdefault(Path(root).name, FakeForge())

        self.p1 = mock.patch.object(fx, "make_tracker", lambda *a, **k: self.tracker)
        self.p2 = mock.patch.object(fx, "make_forge", forge)
        self.p1.start()
        self.p2.start()

    def tearDown(self):
        self.p1.stop()
        self.p2.stop()
        os.environ.pop("FX_ROOT", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fx(self):
        return fx.Fx(self.ws)

    def jd(self, key):
        return self.ws / "factory/jobs" / key

    def job(self, key):
        return json.loads((self.jd(key) / "job.json").read_text())

    def step(self, key):
        f = self.fx()
        return f.log + f.step(key)

    def test_init_discovers_repos_and_valhalla(self):
        cfg = json.loads((self.ws / "factory/config.json").read_text())
        self.assertEqual(sorted(cfg["repos"]), ["backend", "frontend"])
        self.assertEqual(cfg["repos"]["frontend"]["base_branch"], "main")
        self.assertEqual(cfg["skills"]["library"]["name"], "Valhalla")
        self.assertIn("_val/**", cfg["skills"]["library"]["protected_paths"])
        self.assertIn("workspace mode: 2 repos", self.init_out)
        self.assertIn("Valhalla workspace detected", self.init_out)
        self.assertFalse((self.ws / ".gitignore").exists())

    def test_component_routes_to_repo(self):
        self.tracker.add("SSP-1", "Fix login", components=["Backend"])
        with redirect_stdout(io.StringIO()):
            self.fx().create("SSP-1")
        self.assertEqual(self.job("SSP-1")["repo"], "backend")
        self.assertIn("Pre-selected from the issue's components/labels: backend",
                      (self.jd("SSP-1") / "context.md").read_text())

    def test_intake_picks_repo_and_job_runs_in_that_repo(self):
        k = "SSP-2"
        self.tracker.add(k, "Dark mode toggle")
        with redirect_stdout(io.StringIO()):
            self.fx().create(k)
        self.assertIsNone(self.job(k)["repo"])
        self.assertIn("Repos: see context.md.", "\n".join(self.step(k)))
        header = "DECISION: ACCEPT\nLANE: hotfix\nRISK: low\nSURFACES: none\nTYPE: fix\nSLUG: dark mode\nTITLE: Dark\n"
        (self.jd(k) / "intake.md").write_text(header + "SKILLS: none\n\n## Summary\n- x\n")
        self.assertIn("REPO must name one of: backend, frontend", "\n".join(self.step(k)))
        (self.jd(k) / "intake.md").write_text(header + "REPO: frontend\nSKILLS: none\n\n## Summary\n- x\n")
        out = "\n".join(self.step(k))
        job = self.job(k)
        self.assertEqual(job["repo"], "frontend")
        self.assertIn(f"Main checkout: {self.ws / 'frontend'}.", out)
        self.assertIn("Repo: frontend (frontend).", out)
        wt = Path(job["worktree"])
        self.assertEqual(wt.parent, self.ws / ".worktrees")
        self.assertIn("# frontend", (wt / "app.py").read_text())
        (wt / "app.py").write_text("# frontend\nx = 1\n")
        run("git", "commit", "--quiet", "-am", "SSP-2: dark", cwd=wt)
        (self.jd(k) / "build.md").write_text("STATUS: READY\nROUND: 1\nSKILLS: none\n\n## What\nx\n")
        self.assertEqual(self.step(k)[-1], "NEXT gate")
        self.assertIn("SSP-2-fix/dark-mode", run("git", "ls-remote", "origin", cwd=self.ws / "frontend"))
        self.assertIn(1, self.forges["frontend"].mrs)
        self.assertNotIn("backend", self.forges)
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.fx().gate(k)
        self.assertIn("GATE: PASS", buf.getvalue())
        self.assertIn("factory/checks/frontend.sh", (self.jd(k) / "round-1/checks.md").read_text())
        self.assertIn("frontend good", (self.jd(k) / "round-1/checks.log").read_text())

    def test_epic_splits_into_per_repo_stories(self):
        k = "SSP-3"
        self.tracker.add(k, "Audit export")
        with redirect_stdout(io.StringIO()):
            self.fx().create(k)
        self.step(k)
        (self.jd(k) / "intake.md").write_text("DECISION: ACCEPT\nLANE: epic\nRISK: medium\nSKILLS: none\n\n## Summary\n- x\n")
        self.assertIn("AGENT factory:planner", "\n".join(self.step(k)))
        (self.jd(k) / "plan.md").write_text("""PLAN: READY
SKILLS: none

```json
{"stories": [
 {"title": "API", "description": "endpoint", "repo": "backend"},
 {"title": "UI", "description": "button", "repo": "frontend", "depends_on": [0]}
]}
```
""")
        self.step(k)
        with redirect_stdout(io.StringIO()):
            self.fx().approve_plan(k)
        api, ui = [c[0] for c in self.tracker.created]
        self.assertIn("fx-repo-backend", self.tracker.labels_[api])
        self.assertIn("fx-repo-frontend", self.tracker.labels_[ui])
        lines = self.fx().queue()
        self.assertIn(f"blocked {ui} (waits on {api})", lines)
        with redirect_stdout(io.StringIO()):
            self.fx().create(api)
        self.assertEqual(self.job(api)["repo"], "backend")

    def test_filing_with_repo_routes_the_job(self):
        with redirect_stdout(io.StringIO()):
            key = self.fx().file("Dark mode", "Add a toggle", repo="frontend")
            self.fx().create(key)
        self.assertIn("fx-repo-frontend", self.tracker.labels_[key])
        self.assertEqual(self.job(key)["repo"], "frontend")
        with self.assertRaises(fx.FxError):
            self.fx().file("x", "y", repo="nope")

    def test_find_root_from_the_cwd_like_an_installed_plugin(self):
        env = {k: v for k, v in os.environ.items() if k not in ("FX_ROOT", "CLAUDE_PROJECT_DIR")}
        out = subprocess.run([str(FX), "status"], env=env, text=True, capture_output=True, cwd=self.ws / "backend")
        self.assertEqual(out.stdout.strip(), "no jobs", out.stderr)
        out = subprocess.run([str(FX), "where"], env=env, text=True, capture_output=True, cwd=self.ws / "backend")
        self.assertEqual(out.stdout.strip(), str(self.ws.resolve()))
        out = subprocess.run([str(FX), "status"], env=env, text=True, capture_output=True, cwd=self.tmp)
        self.assertEqual(out.returncode, 1)
        self.assertIn("/factory:setup", out.stderr)
        out = subprocess.run([str(FX), "--home", str(self.ws), "status"], env=env, text=True, capture_output=True,
                             cwd=self.tmp)
        self.assertEqual(out.stdout.strip(), "no jobs", out.stderr)


class TestGuardMcpAndGlab(FactoryCase):
    def guard(self, role, tool, **inp):
        stdin = io.StringIO(json.dumps({"tool_name": tool, "tool_input": inp}))
        with mock.patch.object(sys, "stdin", stdin), redirect_stderr(io.StringIO()):
            return fx.guard(self.fx(), role)

    def test_mcp_tools_are_read_only_for_agents(self):
        for tool in ("mcp__atlassian__getJiraIssue", "mcp__atlassian__searchJiraIssuesUsingJql",
                     "mcp__atlassian__getTransitionsForJiraIssue", "mcp__gitlab__get_merge_request",
                     "mcp__gitlab__list_pipelines"):
            self.assertEqual(self.guard("builder", tool), 0, tool)
        for tool in ("mcp__gitlab__save_merge_request", "mcp__atlassian__addCommentToJiraIssue",
                     "mcp__atlassian__transitionJiraIssue", "mcp__atlassian__editJiraIssue",
                     "mcp__gitlab__create_branch", "mcp__gitlab__merge_merge_request"):
            self.assertEqual(self.guard("builder", tool), 2, tool)
            self.assertEqual(self.guard("reviewer-code", tool), 2, tool)

    def test_gitlab_through_glab_without_a_token(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "glab.log"
            g = Path(d) / "glab"
            g.write_text(f"""#!{sys.executable}
import json, sys
args = sys.argv[1:]
body = sys.stdin.read() if "--input" in args else ""
open({str(log)!r}, "a").write(json.dumps([args, body]) + "\\n")
print(json.dumps({{"iid": 3, "web_url": "https://gitlab.acme.io/team/app/-/merge_requests/3", "state": "opened"}}))
""")
            g.chmod(0o755)
            run("git", "remote", "set-url", "origin", "git@gitlab.acme.io:team/app.git", cwd=self.root)
            env = {k: v for k, v in os.environ.items() if k not in ("GITLAB_TOKEN", "GITLAB_PRIVATE_TOKEN")}
            env["PATH"] = f"{d}:{env['PATH']}"
            with mock.patch.dict(os.environ, env, clear=True):
                forge = fx.GitLabForge(fx.deep_merge(fx.DEFAULTS, {}), self.root)
                self.assertEqual(forge.transport, "glab")
                mr = forge.create("ABC-1-feat/x", "main", "ABC-1: X", "body", ["factory"], draft=True)
                self.assertEqual(forge.get(3)["state"], "open")
            args, body = json.loads(log.read_text().splitlines()[0])
        self.assertEqual(mr["iid"], 3)
        self.assertEqual(args[:4], ["api", "-X", "POST", "projects/team%2Fapp/merge_requests"])
        self.assertIn("--hostname", args)
        self.assertEqual(args[args.index("--hostname") + 1], "gitlab.acme.io")
        self.assertEqual(json.loads(body)["title"], "Draft: ABC-1: X")



if __name__ == "__main__":
    unittest.main()
