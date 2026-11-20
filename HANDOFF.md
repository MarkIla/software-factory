# Handoff

From the claude.ai session of 19–20 November 2026, where the factory was
designed and built. Update this file as items close, and delete it once it's
empty.

## Where things stand

- **Version 2.1.0** is in this repo (`MarkIla/software-factory`): the plugin,
  the central plan step, the Jira bridge and outbox, the docs pipeline, and
  the docs in `docs/`.
- **Installed on the owner's Mac** from this folder
  (`~/.local/share/claude-plugins/factory-marketplace`), added as a local
  marketplace, so edits here apply in the next session.
- **Design doc with the diagrams:** "Software Factory: Architecture and How It
  Works", https://claude.ai/artifact/XsBoufz92otjPrjVZgYxEi. The PNGs in
  `docs/images/` are screenshots of its diagrams.
- **Work workspace** where it will be used: `~/Documents/ssp` (several repos,
  Valhalla installed, Atlassian and GitLab MCPs from Valhalla's `.mcp.json`).

## Verified so far

- 79 unit tests pass on macOS (Python 3.13); `claude plugin validate` passes for the plugin and the
  marketplace.
- `claude plugin install` from a local marketplace works; `fx` and `fx-guard`
  run on the Mac.

## Not yet verified live

Nothing has run with real agents, a real Jira or a real GitLab yet. Check
these first, in this order:

1. **The guard hook sees `agent_type`.** The guard relies on PreToolUse hook
   input carrying `agent_type` (`factory:builder` and so on) for plugin
   subagents. Test: in a factory run, a builder write outside its worktree
   must be blocked. If `agent_type` is missing, every factory agent runs
   unguarded.
2. **Background agents and permission prompts.** Plugin agents can't set
   `permissionMode`; `/factory:setup` proposes allow rules instead. Watch for
   prompts that stall unattended agents and widen the suggested rules.
3. **Atlassian MCP tool names and arguments.** `writer_allows` in `fx`
   assumes `addCommentToJiraIssue` (`commentBody`), `editJiraIssue`,
   `transitionJiraIssue`, `createJiraIssue` (`summary`, `projectKey`) and
   `issueIdOrKey`. If the owner's Atlassian MCP names differ, tracker-write is
   blocked; adjust `writer_allows` and its test.
4. **The tracker-read answer format** against real Jira data (comment ids,
   timestamps, account ids), and the reply detection that depends on it.
5. **GitLab through `glab` and GitHub through `gh`** end to end: push, draft
   MR, notes, ready, merge detection.
6. **The docs writer and `/factory:docs`** with the real `atlassian-work`
   skill.

## Open questions for the owner

- The Jira status names: "In Progress" for started and "In Review" for ready
  are assumed in the `work` profile (`jira.transitions`).
- The Jira project key, JQL and Confluence space for `~/Documents/ssp`
  (`/factory:setup` asks).
- Whether to set `outputs.ticket_skill` to a ticket-creation skill.
- A licence for the repo (only needed if it goes public).

## Suggested next steps

1. **Dry run on a small personal repo** with the `personal` profile:
   `/factory:setup`, then `/factory:vision` with a tiny feature, approve the
   plan, `fx plan SLUG --file --to local`, `/factory:run`. Watch the guard,
   permission prompts and the agents' output files.
2. **Then one small work ticket** in `~/Documents/ssp`: `/factory:setup work`,
   `fx doctor`, a single low-risk ticket, and approve the Jira writes at the
   end of the run.
3. **Fix what the live runs show**, add tests, bump the version, push, update
   `docs/`.
