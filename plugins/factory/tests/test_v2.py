"""v2 features: approval outbox, Jira over the Atlassian MCP bridge, local spec queue, multi-tracker routing,
plugin hook guard, documentation stage, adopt. Run from plugins/factory: python3 -m unittest discover -s tests"""
import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from test_fx import FX, FactoryCase, FakeForge, FakeTracker, fx, run


class ApprovingTracker(FakeTracker):
    """A REST-style Jira whose writes the factory must queue for approval."""

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.moves = []

    def transition_to(self, key, name):
        self.moves.append((key, name))
        return True


def main(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = fx.main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class TestImplementationUpdateFormat(FactoryCase):
    def test_jira_comments_use_the_atlassian_work_format(self):
        k = self.start()
        self.step(k)
        self.intake(k)
        self.step(k)
        body = self.tracker.comments_[k][-1]["body"]
        self.assertTrue(body.startswith("## Implementation update — "), body)
        self.assertIn("**Progress**\nAccepted by the software factory", body)
        self.assertIn("**Next**\nBuilding on branch ABC-1-feat/add-subtract.", body)

    def test_question_goes_under_blockers_and_is_not_mistaken_for_a_reply(self):
        k = self.start()
        self.step(k)
        self.intake(k, decision="NEEDS-INFO", extra="## Question\n1. Which module?\n")
        self.step(k)
        body = self.tracker.comments_[k][-1]["body"]
        self.assertIn("**Blockers**\n1. Which module?", body)
        self.assertFalse(self.fx().replied(self.job(k)))
        self.tracker.comment(k, "The math module", author="rep")
        self.assertTrue(self.fx().replied(self.job(k)))


class TestApprovalOutbox(FactoryCase):
    def setUp(self):
        super().setUp()
        self.p1.stop()
        self.raw = ApprovingTracker(json.loads((self.root / "factory/config.json").read_text()))
        self.raw.cfg = fx.deep_merge(fx.DEFAULTS, self.raw.cfg)
        self.tracker = self.raw
        self.p1 = mock.patch.object(fx, "make_tracker", lambda cfg, root, home=None: fx.Outboxed(
            self.raw, fx.Outbox(self.root), auto=False))
        self.p1.start()

    def test_writes_wait_for_a_batch_approval(self):
        k = self.start()
        self.step(k)
        self.intake(k)
        self.step(k)
        self.assertEqual(self.raw.comments_[k], [], "nothing is posted before approval")
        self.assertEqual(self.raw.moves, [])
        rc, out, _ = main("outbox")
        self.assertEqual(out.count("pending"), 3, out)
        self.assertIn("status -> In Progress", out)
        self.assertIn("outbox 3 pending approval", "\n".join(self.fx().queue()))
        rc, out, _ = main("outbox", "approve", "all")
        self.assertEqual(rc, 0)
        self.assertIn("posted 3 op(s)", out)
        self.assertEqual(self.raw.moves, [(k, "In Progress")])
        self.assertTrue(self.raw.comments_[k][-1]["body"].startswith("## Implementation update"))
        self.assertIn("outbox empty", main("outbox")[1])

    def test_reject_drops_an_op(self):
        k = self.start()
        self.step(k)
        self.intake(k)
        self.step(k)
        ops = fx.Outbox(self.root).all()
        rc, out, _ = main("outbox", "reject", ops[0]["id"])
        self.assertIn("rejected 1", out)
        main("outbox", "approve", "all")
        self.assertEqual(self.raw.comments_[k], [])

    def test_question_waits_for_approval_before_the_reply_clock_starts(self):
        k = self.start()
        self.step(k)
        self.intake(k, decision="NEEDS-INFO", extra="## Question\n1. Which module?\n")
        out = self.step(k)
        self.assertIn("waiting for your approval", out[-1])
        self.raw.comment(k, "early chatter", author="rep")
        self.assertFalse(self.fx().replied(self.job(k)))
        main("outbox", "approve", "all")
        job = self.job(k)
        self.assertGreater(job["asked_comment_id"], 0)
        self.assertEqual(self.step(k)[-1], "NEXT wait needs-info (question posted on the issue)")
        self.raw.comment(k, "The math module", author="rep")
        self.assertTrue(self.fx().replied(self.job(k)))

    def test_epic_stories_are_created_after_approval(self):
        k = self.start()
        self.step(k)
        self.intake(k, lane="epic")
        self.step(k)
        stories = [{"title": "API", "description": "a", "acceptance": ["x"], "lane": "feature"},
                   {"title": "UI", "description": "b", "acceptance": ["y"], "lane": "feature", "depends_on": [0]}]
        self.write(k, "plan.md", "PLAN: READY\nSKILLS: none\n\n```json\n" + json.dumps({"stories": stories})
                   + "\n```\n")
        self.step(k)
        with redirect_stdout(io.StringIO()) as buf:
            self.fx().approve_plan(k)
        self.assertIn("2 stories queued for your approval", buf.getvalue())
        self.assertEqual(self.job(k)["stage"], "plan-review")
        with self.assertRaises(fx.FxError):
            self.fx().approve_plan(k)
        main("outbox", "approve", "all")
        job = self.job(k)
        self.assertEqual(job["stage"], "planned")
        self.assertEqual([c["title"] for c in job["children"]], ["API", "UI"])
        self.assertEqual(job["children"][1]["depends_on"], [job["children"][0]["key"]])

    def test_filed_spec_registers_under_the_key_jira_returns(self):
        spec = self.root / "brief.md"
        spec.write_text("SPEC: READY\n\n## Summary\n- dark mode\n")
        with redirect_stdout(io.StringIO()) as buf:
            self.fx().file("Dark mode", "", str(spec), after="ABC-1")
        self.assertIn("queued for your approval", buf.getvalue())
        self.assertEqual(self.raw.created, [])
        main("outbox", "approve", "all")
        key = self.raw.created[0][0]
        self.assertTrue((self.root / "factory/specs" / f"{key}.md").exists())
        deps = json.loads((self.root / "factory/specs/deps.json").read_text())
        self.assertEqual(deps[key], ["ABC-1"])

    def test_operator_answer_is_posted_without_another_approval(self):
        k = self.start()
        self.step(k)
        self.intake(k, decision="NEEDS-INFO", extra="## Question\n1. Which module?\n")
        self.step(k)
        main("outbox", "approve", "all")
        with mock.patch.object(sys, "stdin", io.StringIO("Use the math module")):
            rc, out, err = main("answer", k)
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.raw.comments_[k][-1]["body"], "Use the math module")
        self.assertTrue(self.fx().replied(self.job(k)))


class TestMcpBridge(FactoryCase):
    def setUp(self):
        super().setUp()
        self.p1.stop()
        cfg = json.loads((self.root / "factory/config.json").read_text())
        cfg["tracker"] = "jira-mcp"
        cfg["jira"]["url"] = "https://acme.atlassian.net"
        (self.root / "factory/config.json").write_text(json.dumps(cfg))
        self.bridge = self.root / "factory/bridge"
        self.p1 = mock.patch.object(fx, "make_tracker", fx.make_tracker)
        self.p1.start()

    def answer(self, rid, data):
        (self.bridge / "responses").mkdir(parents=True, exist_ok=True)
        (self.bridge / "responses" / f"{rid}.json").write_text(json.dumps(data))

    def requests(self):
        return json.loads((self.bridge / "requests.json").read_text())

    def test_reads_go_through_the_reader_agent_and_writes_through_the_writer(self):
        rc, out, err = main("queue")
        self.assertEqual(rc, 0, err)
        self.assertIn("NEXT sync", out)
        self.assertIn("AGENT factory:tracker-read | model=haiku", out)
        self.assertIn("Jira site: https://acme.atlassian.net", out)
        self.assertEqual(self.requests()["search"]["jql"], "project = ABC AND labels = factory AND statusCategory != Done")

        self.answer("search", {"issues": [{"key": "ABC-7", "title": "Add subtract"}]})
        rc, out, _ = main("queue")
        self.assertIn("start ABC-7 Add subtract", out)
        self.assertEqual(set(self.requests()), {"issue-ABC-7", "comments-ABC-7", "myself"},
                         "intake's reads are queued with the queue answer, one reader trip for all")
        rc, out, err = main("create", "ABC-7")
        self.assertTrue(out.strip().startswith("NEXT sync"), out + err)

        self.answer("issue-ABC-7", {"key": "ABC-7", "title": "Add subtract", "body": "Please add subtract",
                                    "type": "Story", "status": "To Do", "labels": ["factory"],
                                    "reporter_id": "acc-1", "reporter": "Pat"})
        self.answer("comments-ABC-7", {"comments": [
            {"id": "10", "author_id": "acc-1", "created": "2026-11-01T10:00:00.000+0000", "body": "Also negatives"},
            {"id": "11", "author_id": "acc-9", "created": "2026-11-01T11:00:00.000+0000", "body": "drive-by"}]})
        self.answer("myself", {"id": "acc-me"})
        rc, out, err = main("create", "ABC-7")
        self.assertIn("ABC-7 created", out, err)
        rc, out, _ = main("step", "ABC-7")
        self.assertIn("AGENT factory:intake", out)
        issue = (self.jd("ABC-7") / "issue.md").read_text()
        self.assertIn("Please add subtract", issue)
        self.assertIn("Also negatives", issue)
        self.assertNotIn("drive-by", issue)

        self.intake("ABC-7")
        main("step", "ABC-7")
        self.assertEqual(sum(1 for o in fx.Outbox(self.root).all() if o["status"] == "pending"), 3)
        self.assertFalse((self.bridge / "approved").exists())
        rc, out, _ = main("outbox", "approve", "all")
        self.assertIn("NEXT spawn", out)
        self.assertIn("AGENT factory:tracker-write | model=haiku", out)
        approved = sorted((self.bridge / "approved").glob("*.json"))
        self.assertEqual(len(approved), 3)
        comment = next(json.loads(p.read_text()) for p in approved if '"comment"' in p.read_text())

        def guard(tool, **inp):
            stdin = io.StringIO(json.dumps({"tool_name": tool, "tool_input": inp, "agent_type": "factory:tracker-write"}))
            with mock.patch.object(sys, "stdin", stdin), redirect_stderr(io.StringIO()):
                return fx.hook_guard()
        self.assertEqual(guard("mcp__atlassian__addCommentToJiraIssue", issueIdOrKey="ABC-7",
                               commentBody=comment["args"]["body"]), 0)
        self.assertEqual(guard("mcp__atlassian__addCommentToJiraIssue", issueIdOrKey="ABC-7",
                               commentBody="something else"), 2)
        self.assertEqual(guard("mcp__atlassian__addCommentToJiraIssue", issueIdOrKey="ABC-8",
                               commentBody=comment["args"]["body"]), 2)
        self.assertEqual(guard("mcp__atlassian__transitionJiraIssue", issueIdOrKey="ABC-7", transition={"id": "21"}), 0)
        self.assertEqual(guard("mcp__atlassian__createJiraIssue", projectKey="ABC", summary="Sneaky"), 2)
        self.assertEqual(guard("Write", file_path=str(self.bridge / "done" / "x.json")), 0)
        self.assertEqual(guard("Write", file_path=str(self.root / "app.py")), 2)
        self.assertEqual(guard("Bash", command="curl https://example.com"), 2)

        (self.bridge / "done").mkdir()
        for p in approved:
            rec = json.loads(p.read_text())
            res = {"ok": True, "result": {"comment_id": "12", "created": "2026-11-02T09:00:00.000+0000"}} \
                if rec["op"] == "comment" else {"ok": True}
            (self.bridge / "done" / p.name).write_text(json.dumps(res))
        self.assertIn("outbox empty", main("outbox")[1])
        self.assertEqual(list((self.bridge / "approved").glob("*.json")), [])
        self.assertFalse((self.bridge / "responses" / "comments-ABC-7.json").exists(), "stale cache dropped")

    def test_doctor_reports_the_mcp_tracker_without_a_token(self):
        rc, out, _ = main("doctor")
        self.assertIn("OK   tracker jira (Atlassian MCP)", out)
        self.assertIn("outbox: 0 pending approval", out)

    def test_direct_writes_are_refused(self):
        t = fx.JiraMcpTracker(fx.deep_merge(fx.DEFAULTS, json.loads((self.root / "factory/config.json").read_text())),
                              self.root)
        with self.assertRaises(fx.FxError):
            t.comment("ABC-1", "hi")

    def test_failed_write_can_be_retried(self):
        k = "ABC-7"
        ob = fx.Outbox(self.root)
        oid = ob.add(k, "comment", {"body": "x"}, auto=True)
        main("outbox", "flush")
        (self.bridge / "done").mkdir(parents=True)
        (self.bridge / "done" / f"{oid}.json").write_text(json.dumps({"ok": False, "error": "403 from Jira"}))
        out = main("outbox")[1]
        self.assertIn("failed", out)
        rc, out, _ = main("outbox", "retry", oid)
        self.assertIn("AGENT factory:tracker-write", out)


class TestLocalQueue(FactoryCase):
    def setUp(self):
        super().setUp()
        self.p1.stop()
        cfg = json.loads((self.root / "factory/config.json").read_text())
        cfg["tracker"] = "local"
        (self.root / "factory/config.json").write_text(json.dumps(cfg))
        self.p1 = mock.patch.object(fx, "make_tracker", fx.make_tracker)
        self.p1.start()

    def test_spec_file_to_merged(self):
        spec = self.root / "brief.md"
        spec.write_text("SPEC: READY\n\n## Summary\n- subtract\n\n## Acceptance criteria\n- sub(3,1) == 2\n")
        with redirect_stdout(io.StringIO()) as buf:
            key = self.fx().file("Add subtract", "", str(spec))
        self.assertEqual(key, "SPEC-1")
        self.assertIn("filed SPEC-1 factory/queue/SPEC-1.md", buf.getvalue())
        self.assertTrue((self.root / "factory/specs/SPEC-1.md").exists())
        self.assertIn("start SPEC-1 Add subtract", self.fx().queue())
        with redirect_stdout(io.StringIO()):
            self.fx().create(key)
        out = "\n".join(self.step(key))
        self.assertIn("AGENT factory:intake", out)
        self.assertIn("sub(3,1) == 2", (self.jd(key) / "issue.md").read_text())

        self.intake(key, decision="NEEDS-INFO", extra="## Question\n1. Floats too?\n")
        self.assertEqual(self.step(key)[-1], "NEXT wait needs-info (question posted on the issue)")
        log = (self.root / "factory/queue/SPEC-1.log.jsonl").read_text()
        self.assertIn("Floats too?", log)
        self.assertFalse(self.fx().replied(self.job(key)))
        with redirect_stdout(io.StringIO()):
            self.fx().answer(key, "Integers only")
        self.assertTrue(self.fx().replied(self.job(key)))

        self.fx().tk(key).transition(key, "merged")
        self.assertTrue((self.root / "factory/queue/done/SPEC-1.md").exists())
        self.assertEqual(self.fx().tk(key).issue(key)["status"], "done")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(self.fx().file("Next", "more work", hold=True), "SPEC-2")
        self.assertFalse(self.fx().tk("SPEC-2").in_queue("SPEC-2"))
        with redirect_stdout(io.StringIO()):
            self.fx().release(["SPEC-2"])
        self.assertTrue(self.fx().tk("SPEC-2").in_queue("SPEC-2"))


class TestMultiTracker(unittest.TestCase):
    def test_routes_by_key_prefix(self):
        import tempfile
        home = Path(tempfile.mkdtemp())
        cfg = fx.deep_merge(fx.DEFAULTS, {})
        local = fx.LocalTracker(cfg, home)
        gh = FakeTracker()
        gh.kind, gh.prefix = "github", "GH"
        gh.add("GH-3", "From GitHub")
        m = fx.MultiTracker([local, gh])
        key = local.create("From a spec", "body", ["factory"])
        self.assertEqual({i["key"] for i in m.queue()}, {"SPEC-1", "GH-3"})
        self.assertIs(m.for_key("GH-3"), gh)
        self.assertIs(m.for_key(key), local)
        self.assertEqual(m.issue("GH-3")["title"], "From GitHub")
        self.assertIs(m.by_kind("github"), gh)
        with self.assertRaises(fx.FxError):
            m.by_kind("jira")


class TestHookGuard(FactoryCase):
    def hook(self, agent_type, tool, **inp):
        data = {"tool_name": tool, "tool_input": inp, "cwd": str(self.root)}
        if agent_type is not None:
            data["agent_type"] = agent_type
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(data))), redirect_stderr(io.StringIO()):
            return fx.hook_guard()

    def test_only_factory_agents_are_guarded(self):
        outside = str(self.root / "app.py")
        self.assertEqual(self.hook(None, "Write", file_path=outside), 0, "main session")
        self.assertEqual(self.hook("Explore", "Write", file_path=outside), 0, "other agents")
        self.assertEqual(self.hook("factory:builder", "Write", file_path=outside), 2)
        self.assertEqual(self.hook("fx-builder", "Write", file_path=outside), 2, "legacy per-project agents")
        self.assertEqual(self.hook("factory:reviewer-docs", "mcp__atlassian__updateConfluencePage"), 2)
        self.assertEqual(self.hook("factory:docs-writer", "mcp__atlassian__getConfluencePage"), 0)
        resp = self.root / "factory/bridge/responses/search.json"
        self.assertEqual(self.hook("factory:tracker-read", "Write", file_path=str(resp)), 0)
        self.assertEqual(self.hook("factory:tracker-read", "Write", file_path=str(self.root / "factory/jobs/x.md")), 2)
        self.assertEqual(self.hook("factory:tracker-read", "Bash", command="ls"), 2)
        self.assertEqual(self.hook("factory:tracker-read", "mcp__atlassian__addCommentToJiraIssue"), 2)

    def test_shim_hands_factory_agents_to_the_full_guard(self):
        shim = FX.parent / "fx-guard"
        data = {"tool_name": "Bash", "tool_input": {"command": "git push origin HEAD"},
                "agent_type": "factory:builder", "cwd": str(self.root)}
        out = subprocess.run([str(shim)], input=json.dumps(data), text=True, capture_output=True,
                             env=dict(__import__("os").environ, FX_ROOT=str(self.root)))
        self.assertEqual(out.returncode, 2, out.stderr)
        self.assertIn("agents never push", out.stderr)

    def test_role_names(self):
        self.assertEqual(fx.role_of("factory:spec-writer"), "spec-writer")
        self.assertEqual(fx.role_of("fx-tracker-write"), "tracker-write")
        self.assertIsNone(fx.role_of("factory:nope"))
        self.assertIsNone(fx.role_of("general-purpose"))


class TestDocsStage(FactoryCase):
    SPEC = ("SPEC: READY\nSKILLS: none\n\n## Summary\n- x\n\n## Documentation\n"
            "- README: usage of sub() (in-repo)\n- Calculator overview for support, Confluence (external)\n")

    def to_review_pass(self, k):
        self.step(k)
        self.intake(k, lane="feature", risk="low")
        self.step(k)
        self.write(k, "spec.md", self.SPEC)
        self.step(k)
        self.build(k)
        self.step(k)
        self.gate(k)
        self.step(k)
        for r in self.job(k)["reviewers"]:
            self.review(k, r)

    def test_planned_external_docs_are_drafted_before_ready(self):
        k = self.start()
        self.to_review_pass(k)
        self.assertEqual(self.job(k)["reviewers"]["docs"], "haiku")
        out = "\n".join(self.step(k))
        self.assertEqual(self.job(k)["stage"], "docs")
        self.assertIn("AGENT factory:docs-writer | model=sonnet", out)
        self.assertIn("Docs format: the atlassian-work skill.", out)
        self.assertIn("Calculator overview for support", out)
        self.assertNotIn("README: usage", out.split("PROMPT")[-1].split("Draft these")[-1])

        self.write(k, "docs/overview.md", "TITLE: Calculator overview\n\n# Calculator overview\n")
        self.write(k, "docs.md", "DOCS: DONE\n\n- docs/overview.md\n")
        out = "\n".join(self.step(k))
        self.assertIn("refused overview.md", out)
        self.write(k, "docs/overview.md", "DOC: READY\nTITLE: Calculator overview\nTARGET: confluence\n\n# x\n")
        out = self.step(k)
        self.assertTrue(out[-1].startswith("NEXT wait ready"), out)
        self.assertTrue(any("Documentation drafts (1)" in n for _, n in self.forge.notes))
        self.assertIn("Doc draft: Calculator overview", self.tracker.comments_[k][-1]["body"])

        rc, out, _ = main("docs")
        self.assertIn("after merge (job is ready)", out)
        self.forge.mrs[1]["state"] = "merged"
        self.fx().queue()
        rc, out, _ = main("docs")
        self.assertIn("ready to publish", out)
        rc, out, _ = main("docs", "done", k, "overview.md", "--url", "https://wiki/x")
        self.assertIn("recorded", out)
        self.assertIn("no documentation waiting", main("docs")[1])

    def test_no_external_docs_means_no_docs_stage(self):
        k = self.start()
        self.SPEC = "SPEC: READY\nSKILLS: none\n\n## Summary\n- x\n\n## Documentation\n- README (in-repo)\n"
        self.to_review_pass(k)
        out = self.step(k)
        self.assertTrue(out[-1].startswith("NEXT wait ready"), out)

    def test_epic_docs_plan_waits_for_all_stories(self):
        plan = self.root / "docs-plan.md"
        plan.write_text("- Billing tech spec, Confluence (external)\n- ADR for the ledger (in-repo)\n")
        rc, out, err = main("adopt", "ABC-50", "--docs-plan", str(plan), "--children", "ABC-51,ABC-52")
        self.assertEqual(rc, 0, err)
        self.assertIn("epic docs plan saved", out)
        rc, out, _ = main("docs")
        self.assertIn("epic ABC-50 · 1 planned doc(s): Billing tech spec", out)
        self.assertIn("0/2 stories merged", out)
        self.assertEqual(main("docs", "done", "ABC-50", "billing-tech-spec.md", "--url", "https://wiki/b")[0], 0)
        self.assertIn("epic ABC-50", main("docs")[1])
        main("docs", "done", "ABC-50", "epic")
        self.assertIn("no documentation waiting", main("docs")[1])
        self.assertEqual(main("docs", "done", "ZZZ-1", "x.md")[0], 1)


class TestAdopt(FactoryCase):
    def test_adopt_registers_a_spec_for_a_ticket_made_elsewhere(self):
        spec = self.root / "brief.md"
        spec.write_text("SPEC: READY\n\n## Summary\n- y\n")
        self.tracker.add("ABC-9", "Made by my ticket skill", labels=())
        rc, out, err = main("adopt", "ABC-9", "--spec", str(spec), "--after", "ABC-1", "--queue")
        self.assertEqual(rc, 0, err)
        self.assertTrue((self.root / "factory/specs/ABC-9.md").exists())
        self.assertEqual(json.loads((self.root / "factory/specs/deps.json").read_text())["ABC-9"], ["ABC-1"])
        self.assertIn("factory", self.tracker.labels_["ABC-9"])
        bad = self.root / "draft.md"
        bad.write_text("SPEC: DRAFT\n")
        self.assertEqual(main("adopt", "ABC-9", "--spec", str(bad))[0], 1)


class TestPluginLayout(unittest.TestCase):
    ROOT = FX.parents[1]

    def test_every_role_has_an_agent_and_names_match(self):
        for role in fx.ROLES:
            p = self.ROOT / "agents" / f"{role}.md"
            self.assertTrue(p.exists(), role)
            head = p.read_text().split("---")[1]
            self.assertIn(f"\nname: {role}\n", head)
            self.assertNotIn("hooks:", head, "plugin agents cannot carry hooks")
            self.assertNotIn("permissionMode", head)

    def test_skills_and_hooks(self):
        for name in ("run", "vision", "setup", "docs"):
            self.assertTrue((self.ROOT / "skills" / name / "SKILL.md").exists(), name)
        hooks = json.loads((self.ROOT / "hooks" / "hooks.json").read_text())
        cmd = hooks["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        self.assertIn("${CLAUDE_PLUGIN_ROOT}", cmd)
        self.assertIn("bin/fx-guard", cmd)
        shim = self.ROOT / "bin" / "fx-guard"
        quiet = subprocess.run([str(shim)], input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push"}}),
                               text=True, capture_output=True)
        self.assertEqual(quiet.returncode, 0, "the main session is never guarded")
        other = subprocess.run([str(shim)], input=json.dumps({"tool_name": "Bash", "agent_type": "Explore",
                                                              "tool_input": {"command": "git push"}}),
                               text=True, capture_output=True)
        self.assertEqual(other.returncode, 0)
        self.assertEqual(fx.AGENT_PREFIX, "factory:")


if __name__ == "__main__":
    unittest.main()
