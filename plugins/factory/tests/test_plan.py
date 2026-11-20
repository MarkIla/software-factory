"""The central plan step: a /factory:vision brief planned once, approved, then filed in dependency order.
Run from plugins/factory: python3 -m unittest discover -s tests"""
import io
import json
import sys
from contextlib import redirect_stdout
from unittest import mock

from test_fx import FactoryCase, fx
from test_v2 import ApprovingTracker, main

PLAN = """PLAN: READY
SKILLS: none

## Summary
- Audit log export in three stories

## Architecture
- audit_events table is the single source; the API exposes /audit/export

## Risks
- Large exports

## Documentation
- ADR for the audit_events schema (in-repo)
- Audit export overview for support, Confluence (external)

## Stories
1. Table  2. API  3. UI

```json
{"stories": [
  {"title": "Add audit_events table", "description": "Schema and model", "spec": "stories/01-table.md",
   "touches": ["src/models"], "depends_on": []},
  {"title": "Export endpoint", "description": "CSV export API", "spec": "stories/02-api.md",
   "touches": ["src/api"], "depends_on": [0]},
  {"title": "Audit settings page", "description": "Admin UI toggle", "acceptance": ["toggle persists"],
   "touches": ["src/models/settings.py"], "depends_on": []}
]}
```
"""


class PlanCase(FactoryCase):
    def setUp(self):
        super().setUp()
        self.brief = self.root / "factory/briefs/audit-export"
        (self.brief / "stories").mkdir(parents=True)
        (self.brief / "brief.md").write_text("PHASE: review\nTITLE: Audit log export\nKEYS: none\n\ndigest\n")
        (self.brief / "overview.md").write_text("# Audit log export\n\nGoal: admins export the audit log.\n")
        (self.brief / "stories/01-table.md").write_text("SPEC: READY\n\n## Summary\n- table\n")
        (self.brief / "stories/02-api.md").write_text("SPEC: READY\n\n## Summary\n- api\n")

    def use_local(self):
        self.p1.stop()
        cfg = json.loads((self.root / "factory/config.json").read_text())
        cfg["tracker"] = "local"
        (self.root / "factory/config.json").write_text(json.dumps(cfg))
        self.p1 = mock.patch.object(fx, "make_tracker", fx.make_tracker)
        self.p1.start()


class TestPlanStep(PlanCase):
    def test_planner_is_spawned_on_the_brief_and_may_write_only_plan_md(self):
        rc, out, err = main("plan", "audit-export")
        self.assertEqual(rc, 0, err)
        self.assertIn("AGENT factory:planner | model=opus | name=planner-audit-export", out)
        self.assertIn(f"Brief folder: {self.brief}/.", out)
        self.assertIn("Mode: program plan for brief audit-export.", out)
        from test_v2 import TestHookGuard
        hook = TestHookGuard.hook
        self.assertEqual(hook(self, "factory:planner", "Write", file_path=str(self.brief / "plan.md")), 0)
        self.assertEqual(hook(self, "factory:planner", "Write", file_path=str(self.brief / "stories/01-table.md")), 2)
        self.assertEqual(hook(self, "factory:builder", "Write", file_path=str(self.brief / "plan.md")), 2)

    def test_draft_specs_block_planning(self):
        (self.brief / "stories/02-api.md").write_text("SPEC: DRAFT\n")
        rc, _, err = main("plan", "audit-export")
        self.assertEqual(rc, 1)
        self.assertIn("02-api.md", err)

    def test_summary_waves_and_conflict_warning(self):
        (self.brief / "plan.md").write_text(PLAN)
        rc, out, _ = main("plan", "audit-export")
        self.assertIn("plan audit-export: 3 stories in 2 wave(s) · waiting for your approval", out)
        self.assertIn("wave 1: 1 Add audit_events table · 3 Audit settings page", out)
        self.assertIn("wave 2: 2 Export endpoint", out)
        self.assertIn("warn stories 1 and 3 both touch src/models in wave 1", out)
        self.assertIn("docs: 2 planned (1 external)", out)
        self.assertIn("approve with fx plan audit-export --approve", out)
        self.assertEqual(main("plan", "audit-export", "--file")[0], 1, "filing needs approval")

    def test_redo_keeps_the_rejected_plan_and_respawns_with_feedback(self):
        (self.brief / "plan.md").write_text(PLAN)
        with mock.patch.object(sys, "stdin", io.StringIO("Split the API story")):
            rc, out, _ = main("plan", "audit-export", "--redo")
        self.assertIn("read plan-feedback-1.md", out)
        self.assertTrue((self.brief / "plan.md.rejected-1").exists())
        self.assertFalse((self.brief / "plan.md").exists())

    def test_spec_paths_must_stay_inside_the_brief(self):
        (self.brief / "plan.md").write_text(PLAN.replace("stories/01-table.md", "../../config.json"))
        rc, _, err = main("plan", "audit-export")
        self.assertEqual(rc, 1)
        self.assertIn("not a file in the brief", err)


class TestPlanFilingLocal(PlanCase):
    def test_files_epic_then_stories_with_specs_dependencies_and_docs_plan(self):
        self.use_local()
        (self.brief / "plan.md").write_text(PLAN)
        main("plan", "audit-export", "--approve")
        rc, out, err = main("plan", "audit-export", "--file", "--to", "local")
        self.assertEqual(rc, 0, err)
        self.assertIn("NEXT done plan audit-export filed", out)
        q = self.root / "factory/queue"
        self.assertIn("STATUS: held", (q / "SPEC-1.md").read_text(), "the epic is never built itself")
        self.assertIn("KIND: epic", (q / "SPEC-1.md").read_text())
        self.assertIn("PARENT: SPEC-1", (q / "SPEC-3.md").read_text())
        self.assertTrue((self.root / "factory/specs/SPEC-2.md").exists())
        self.assertTrue((self.root / "factory/specs/SPEC-3.md").exists())
        self.assertFalse((self.root / "factory/specs/SPEC-4.md").exists(), "no spec: the spec-writer writes it")
        self.assertIn("Architecture (from the plan)", (q / "SPEC-4.md").read_text())
        deps = json.loads((self.root / "factory/specs/deps.json").read_text())
        self.assertEqual(deps, {"SPEC-3": ["SPEC-2"]})
        epic = json.loads((self.root / "factory/specs/SPEC-1.epic.json").read_text())
        self.assertEqual(epic["children"], ["SPEC-2", "SPEC-3", "SPEC-4"])
        self.assertIn("Audit export overview for support", epic["docs_plan"])
        queue = self.fx().queue()
        self.assertIn("start SPEC-2 Add audit_events table", queue)
        self.assertTrue(any(line.startswith("blocked SPEC-3") for line in queue), queue)
        self.assertIn("filed", main("plan")[1])
        rc, out, _ = main("plan", "audit-export", "--file")
        self.assertEqual(sorted(p.name for p in q.glob("SPEC-*.md")), ["SPEC-1.md", "SPEC-2.md", "SPEC-3.md", "SPEC-4.md"],
                         "filing again creates nothing new")

    def test_tickets_made_elsewhere_are_linked(self):
        (self.brief / "plan.md").write_text(PLAN)
        rc, out, err = main("plan", "audit-export", "--link", "epic=ABC-10", "--link", "1=ABC-11",
                            "--link", "2=ABC-12", "--link", "3=ABC-13")
        self.assertEqual(rc, 0, err)
        self.assertIn("NEXT done", out)
        self.assertTrue((self.root / "factory/specs/ABC-12.md").exists())
        self.assertEqual(json.loads((self.root / "factory/specs/deps.json").read_text())["ABC-12"], ["ABC-11"])
        self.assertEqual(main("plan", "audit-export", "--link", "9=ABC-1")[0], 1)


class TestPlanFilingWithApprovals(PlanCase):
    def setUp(self):
        super().setUp()
        self.p1.stop()
        self.raw = ApprovingTracker(fx.deep_merge(fx.DEFAULTS, json.loads((self.root / "factory/config.json").read_text())))
        self.tracker = self.raw
        self.p1 = mock.patch.object(fx, "make_tracker", lambda cfg, root, home=None: fx.Outboxed(
            self.raw, fx.Outbox(self.root), auto=False))
        self.p1.start()

    def key_of(self, title):
        return next((o.get("result") or {}).get("created_key") for o in fx.Outbox(self.root).all()
                    if o["op"] == "create" and o["args"]["title"] == title)

    def test_epic_then_one_batch_of_stories_with_placeholders_until_keys_exist(self):
        (self.brief / "plan.md").write_text(PLAN)
        main("plan", "audit-export", "--approve")
        rc, out, _ = main("plan", "audit-export", "--file")
        self.assertIn("the epic waits for your approval", out)
        self.assertIn("fx outbox", out)
        self.assertEqual(len(fx.Outbox(self.root).all()), 1)
        main("outbox", "approve", "all")
        epic = self.raw.created[0][0]
        rc, out, _ = main("plan", "audit-export", "--file")
        ops = [o for o in fx.Outbox(self.root).all() if o["status"] == "pending"]
        self.assertEqual(len(ops), 3, "every story in one approval batch")
        self.assertTrue(all(o["args"]["parent"] == epic for o in ops))
        third = next(o for o in ops if o["args"]["title"] == "Export endpoint")
        main("outbox", "approve", third["id"])
        api = self.key_of("Export endpoint")
        deps = json.loads((self.root / "factory/specs/deps.json").read_text())
        self.assertEqual(deps[api], ["plan:audit-export#1"], "blocked until its dependency exists")
        main("outbox", "approve", "all")
        deps = json.loads((self.root / "factory/specs/deps.json").read_text())
        table = self.key_of("Add audit_events table")
        self.assertEqual(deps[api], [table])
        self.assertTrue((self.root / "factory/specs" / f"{api}.md").exists())
        self.assertIn("NEXT done", main("plan", "audit-export")[1])
