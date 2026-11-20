# Software factory plugin

This repo is a Claude Code plugin marketplace with one plugin, `factory`
(`plugins/factory/`). It turns ideas, Jira tickets, GitHub issues or local spec
files into checked, reviewed and documented draft merge requests. User-facing
docs are in `docs/`; read `docs/how-it-works.md` before changing behaviour.
Where the last session left off: `HANDOFF.md`.

## The owner's decisions (don't change without asking)

- Never auto-merge. A person merges every merge request.
- The plugin guides the owner's workflow. The owner types slash commands and
  makes decisions; skills run every `fx` command, turn fx's hints into
  questions, and end with what comes next. Never ask the owner to run `fx`.
- Models: builder Sonnet; planner and spec-writer Opus; Jira reader and writer
  Haiku; reviewers scale with risk.
- Work: Jira only through the Atlassian MCP (no API tokens on the machine),
  GitLab through `glab`, every Jira write batched for the owner's approval.
  Personal: local spec files and GitHub issues and PRs; never Jira.
- House style comes from the owner's global skills: `gitlab-mr` (MR title,
  branch, description format) and `atlassian-work` (the "Implementation
  update" Jira comment, Confluence page templates). Builders take only
  gitlab-mr's format, never its commit, push or approval steps.
- The company skills library (Valhalla) is an optional integration, off by
  default. The factory must work fully without it.
- Documentation is part of done: planned in every spec and plan, in-repo docs
  by the builder plus a docs reviewer, external drafts published with
  `/factory:docs`.
- Token efficiency matters: a thin orchestrator, agents that write one file
  and reply with one line.

## Architecture in brief

- `plugins/factory/bin/fx` is the state machine: Python 3.9+, standard
  library only. Every rule, stage change, tracker and forge write, the gate,
  the outbox and the guard live here. Skills and agents never change state by
  hand.
- `skills/`: `run` (the orchestrator loop), `vision`, `setup`, `docs`.
- `agents/`: twelve agents. Each writes one file whose first line is its
  verdict; `fx` parses it, retries or escalates.
- `hooks/hooks.json` runs `bin/fx-guard`, which passes everything through
  unless the hook input's `agent_type` is `factory:*`, then calls
  `fx guard --hook`.
- Jira bridge (`tracker: jira-mcp`): `fx` never calls Jira. Reads raise
  `NeedSync` → `NEXT sync` → the tracker-read agent answers
  `factory/bridge/requests.json` into `bridge/responses/`. Writes go to
  `factory/outbox/` → owner approves → copied to `bridge/approved/` → the
  tracker-write agent posts them → `bridge/done/` → `fx` reconciles.
- Central plan: `fx plan SLUG` spawns the planner on `factory/briefs/<slug>/`;
  `--approve`, `--redo`, `--file` (resumable; dependencies in
  `factory/specs/deps.json`, with `plan:<slug>#N` placeholders until a key
  exists), `--link`.
- Briefs from a ticket: `fx ticket KEY --brief SLUG` copies the ticket into
  `ticket.md` (quoted as data) and records it in the brief's `plan.json`.
  `fx plan SLUG --file` then files onto it: one story attaches the spec, several
  make it the epic. The queue holds any key with `specs/<KEY>.epic.json`.

## Commands

```
cd plugins/factory && python3 -m unittest discover -s tests    # 88 tests, ~70 s on macOS
claude plugin validate plugins/factory && claude plugin validate .
```

Release: bump `version` in `plugins/factory/.claude-plugin/plugin.json` and
`VERSION` in `bin/fx`. Never put a version in `marketplace.json`.

## Platform facts learned the hard way

- Plugin agents ignore `hooks`, `permissionMode` and `mcpServers` in their
  frontmatter, so the guard is a plugin hook keyed on `agent_type`.
- A plugin's `bin/` is on the Bash PATH in Claude Code. `fx` finds the project
  from `--home`, `FX_HOME`/`FX_ROOT`, then `CLAUDE_PROJECT_DIR` or the cwd
  (a linked worktree maps back to its main checkout).
- Plugin agents are shared by every project, so per-project skill pins travel
  in the prompt header (`Skills:` line), not in agent frontmatter.
- Installing from a local-folder marketplace copies the plugin folder as it
  is on disk, uncommitted edits included, into `~/.claude/plugins/cache/`.
  Sessions use that copy, not this folder. `claude plugin update` does nothing
  while the version is unchanged, so to apply edits run `claude plugin
  uninstall factory@software-factory` and `claude plugin install
  factory@software-factory`, then start a new session. `claude --plugin-dir
  plugins/factory` loads the folder in place for one terminal session.
  Installs from git also update only when `plugin.json`'s version changes.
  (Checked on Claude Code 2.1.152.)
- claude.ai organization plugin sync rejects a top-level `bin/` folder.
- Commands that take a file argument must not also read stdin: `fx file
  --spec` once hung on an open stdin pipe.

## Conventions

- Every `fx` behaviour change gets a test. Tests drive `fx` against
  `FakeTracker`/`FakeForge` in temporary git repos (`tests/test_fx.py`
  holds the fixtures).
- Keep `docs/` in step with behaviour, `commands.md` and `configuration.md`
  especially. Diagrams in `docs/images/` come from the Claude Doc linked in
  `HANDOFF.md`.
- Agent files: frontmatter `name` is the bare role (`builder`), run as
  `factory:builder`; no `hooks` or `permissionMode`.
- Writing (docs, prompts, ticket text): plain words, short sentences,
  specifics over adjectives.
