# factory: a local software factory for Claude Code

Turn tickets and reviewed specs into checked, reviewed, documented draft merge
requests. You start it (`/factory:run`), agents do the work in isolated git
worktrees, a deterministic state machine (`fx`) decides every next step, and
nothing merges unless a person merges it.

It works for company projects (Jira through the Atlassian MCP, GitLab, an
optional company skills library) and for personal ones (local spec files and
GitHub issues, GitHub pull requests), with the same commands.

## Commands

| Command | What it does |
|---|---|
| `/factory:setup` | Set up the factory in this repo or multi-repo workspace: config, checks, permissions, health check. Run once per project. |
| `/factory:vision` | Think out loud about something to build. Ends with reviewed specs, a central plan from the planner that you approve, and tickets or spec files queued in the plan's order. |
| `/factory:run` | Work the queue: start jobs, spawn agents, run checks, open draft MRs. Ends by asking you to approve its Jira writes in one batch. |
| `/factory:run KEY` | Run one ticket (`ABC-123`, `GH-12`, `SPEC-3`). |
| `/factory:run <anything>` | Status, feedback on an MR, answers to a reporter question, plan approval, dropping a job. |
| `/factory:docs` | Publish the documentation drafts of merged work, and write an epic's planned documents once its stories have merged. |

`fx` (the plugin's `bin/`) is on the PATH inside Claude Code; `fx --help`
lists everything. Outside Claude Code, call it by path or alias it.

## The whole flow

```
you -> /factory:vision -> specs -> central plan (planner) -> your approval -> tickets, in waves
    -> /factory:run -> per ticket: intake -> [spec] -> build -> gate -> review -> [docs] -> ready MR
    -> you merge -> /factory:docs publishes the documentation
```

**The central plan.** After `/factory:vision` writes the specs, the planner
(Opus, its own context) plans the whole build once: waves of stories that can
run in parallel, the shared contracts every story builds against (decided once,
first wave), the files each story touches (so collisions show before anyone
builds), and the documentation for the feature as a whole. You approve it with
`fx plan SLUG --approve` (or send it back with `--redo`), and
`fx plan SLUG --file` files the epic and stories in order with their specs and
dependencies. Tickets that arrive another way and turn out too big get the
same planner inside the run, as an epic.

### How a job flows

```
queue -> intake -> [plan -> your approval -> stories]          (epics filed by others)
               -> spec -> build -> gate -> review -> [docs] -> ready MR -> you merge
                    ^________ fixes, until the round limit ______|
```

- **Intake** (Sonnet) accepts, asks the reporter a question, or rejects, and
  picks the lane (hotfix, feature, epic), risk and surfaces.
- **Spec** (Opus) unless a reviewed spec from `/factory:vision` already exists.
- **Build** (Sonnet) in a worktree on a ticket-named branch; fx pushes and opens
  a draft MR.
- **Gate** runs the project's own checks script, the factory's copy.
- **Review** by a code reviewer plus security, data and UI reviewers where the
  change touches them, and a **docs reviewer** on features. Models scale with
  risk.
- **Docs** stage drafts the external documents the spec planned.
- **Ready**: the MR leaves draft with a summary note; the ticket gets an update.

## Trackers

| Profile | Queue | Keys | Writes |
|---|---|---|---|
| `work` | Jira through the Atlassian MCP (`tracker: "jira-mcp"`) | `ABC-123` | Wait in the outbox for your approval |
| `personal` | Local spec files in `factory/queue/` and GitHub issues (`["local", "github"]`) | `SPEC-3`, `GH-12` | Immediate |

**Jira without a token.** fx never calls Jira. When it needs a read, it prints
`NEXT sync` and the orchestrator runs the `tracker-read` agent (Haiku), which
answers fx's requests through the Atlassian MCP into `factory/bridge/`. Writes
(status updates, labels, transitions, new stories, questions to reporters)
go to `factory/outbox/`; at the end of each run you approve them in one batch,
and the `tracker-write` agent posts exactly the approved text. The guard lets
it touch only the approved issues. A REST mode (`tracker: "jira"` with
`JIRA_EMAIL`/`JIRA_API_TOKEN`) remains for machines without the MCP.

Jira comments use the Implementation update format (Progress, Next, Blockers,
Evidence) from your `atlassian-work` conventions.

```
fx outbox                      list pending, approved and failed writes
fx outbox show ID|all          full text
fx outbox approve ID…|all      approve (posts, or prints the writer agent to spawn)
fx outbox reject ID…           drop
fx outbox retry ID             retry a failed write
```

## Documentation

Documentation is planned with the work and checked like code:

1. **Planning.** `/factory:vision` and the spec writer give every spec a
   `## Documentation` section; an epic's plan has one for the whole feature.
   Each entry is `(in-repo)` or `(external)` and names its reader: an ADR for
   a design decision, a README change, a tech spec or high-level overview for
   people who want to understand the feature, a guide, a runbook.
2. **In-repo docs** are part of the builder's definition of done (changelog,
   ADRs in `docs.adr_dir`, listed pages). The **docs reviewer** blocks docs
   that are missing or describe behaviour the code doesn't have.
3. **External docs** are drafted by the docs writer after review, in your
   `atlassian-work` page templates, into `factory/jobs/<KEY>/docs/`.
4. **Publishing** is yours: `/factory:docs` refreshes each draft against the
   merged commit and publishes it through `atlassian-work`'s preview and
   approval. Epic-level documents are written once all stories have merged.

## Your house style

`outputs` in `factory/config.json` points at skills you already use:

- `mr_skill: "gitlab-mr"`: MR titles (`ABC-123: summary`), branches
  (`ABC-123-feat/slug`), commits and the What / How / Testing / Risk and
  rollback / Checklist description. A repo MR template still wins.
- `docs_skill: "atlassian-work"`: Confluence page templates and the publish
  flow in `/factory:docs`.
- `ticket_skill`: optional; `/factory:vision` creates Jira tickets with it and
  then attaches the reviewed specs with `fx adopt`.
- `jira_update_format: "implementation-update"`.

## Company skills (optional)

In a Valhalla workspace, `fx skills on` lets agents use the installed skills
(discover mode by default, or pinned per role with glob patterns). The factory
re-resolves pins when `.valhalla.lock` changes, protects the library's files
from builders, and keeps working with the integration off.

## Safety

- Only tickets your JQL, queue label or local queue selects become jobs.
  Ticket text reaches agents only as quoted data.
- A plugin hook guards every factory agent: no pushes, rebases, branch
  switches or worktree changes; writes only in the agent's job folder (and the
  builder's worktree); protected paths stay untouched; no MCP writes except
  the Jira writer's approved ops. Your own sessions and other agents are not
  affected.
- fx pushes, opens draft MRs and marks them ready. It never merges.
- Each job has a round limit; then it stops and asks for a person.

## Configuration

`factory/config.json` in each project; `fx init work|personal` writes it and
`fx doctor` checks it. The keys you'll touch most:

| Key | Meaning |
|---|---|
| `tracker` | `jira-mcp`, `jira`, `github`, `local`, or a list |
| `jira.url`, `jira.jql`, `jira.transitions`, `jira.approve_writes` | Jira site, trust boundary, workflow names, approvals |
| `forge`, `gitlab.host` | `gitlab` or `github` |
| `outputs.*` | your house-style skills (above) |
| `docs.changelog`, `docs.adr_dir`, `docs.paths`, `docs.confluence` | documentation conventions and default Confluence location |
| `docs.review` | docs reviewer model per risk |
| `models.*`, `lanes.*`, `code_review`, `surface_reviewers` | who runs on which model |
| `concurrency`, `ports`, `gate_timeout_sec`, `sensitive_paths` | limits |
| `repos` | workspace mode: one entry per repo, with routing hints |

Defaults for everything else are in `bin/fx` (`DEFAULTS`).

## Upgrading from the zip install

Run `/factory:setup` in the project. It keeps `factory/config.json`, the
checks, jobs, briefs and specs, offers to switch `tracker` to `jira-mcp`, and
offers to delete the copied `factory/bin/fx`, `.claude/agents/fx-*.md`,
`.claude/skills/factory/` and `.claude/skills/vision/`.

## Development

```
cd plugins/factory
python3 -m unittest discover -s tests
claude plugin validate .
```
