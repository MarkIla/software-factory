# Commands

You only need the four slash commands. They run `fx`, the script underneath,
for you: you answer questions and make decisions, and each command ends by
telling you what comes next. The `fx` tables below are a reference for when you
want to look underneath or debug. Inside Claude Code
it is on your PATH; elsewhere call it by path (the plugin's `bin/fx`), with
`--home <project>` when you're not inside the project.

- [Slash commands](#slash-commands)
- [fx: everyday](#fx-everyday)
- [fx: work intake and filing](#fx-work-intake-and-filing)
- [fx: Jira approvals](#fx-jira-approvals)
- [fx: documentation](#fx-documentation)
- [fx: jobs, step by step](#fx-jobs-step-by-step)
- [fx: setup and maintenance](#fx-setup-and-maintenance)

## Slash commands

| Command | What it does |
| --- | --- |
| `/factory:setup [work\|personal]` | Sets up the factory in this repo or workspace: config, checks, permissions, health check. Also repairs an existing setup |
| `/factory:vision [name\|list]` | Starts or resumes a brief: turns an idea into reviewed specs, has the planner plan the build for your approval, then files it |
| `/factory:vision KEY` | Starts a brief from an existing ticket (`SSP-123`, `GH-12`, `SPEC-3`) and files the reviewed specs onto it |
| `/factory:run` | Works the queue until nothing more can run, then asks you to approve its Jira writes |
| `/factory:run KEY` | Runs one ticket (`ABC-123`, `GH-12`, `SPEC-3`) |
| `/factory:run status [KEY]` | Shows every job, or one job in detail |
| `/factory:run outbox` | Reviews and approves pending Jira writes |
| `/factory:run <anything>` | Talk to the factory: feedback on a merge request, answers to questions, plan approval, dropping a job |
| `/factory:docs [KEY]` | Publishes documentation drafts for merged work, and writes an epic's planned documents once its stories have merged |

## fx: everyday

| Command | What it does |
| --- | --- |
| `fx status [KEY]` | Lists jobs with stage, lane, risk, round and MR, or shows one job: its summary, why it stopped, recent history and the first line of each file it holds |
| `fx summary [KEY …]` | One line per job, for reports |
| `fx queue` | Syncs with the tracker and prints what to do: `start`, `step`, `hold`, `blocked`, `wait`, `done` |
| `fx doctor [--checks]` | Checks config, credentials, the plugin install and the trackers; `--checks` also runs the checks on the base branch |

## fx: work intake and filing

| Command | What it does |
| --- | --- |
| `fx plan` | Lists every brief with its plan state |
| `fx plan SLUG` | Spawns the planner on the brief, or prints its plan: waves, collision warnings, documentation count |
| `fx plan SLUG --approve` | Approves the plan as written |
| `fx plan SLUG --redo` | Rejects the plan; your notes on stdin go to the planner |
| `fx plan SLUG --file [--to local\|github\|jira] [--hold]` | Files the approved plan: the epic (held), then every story with its spec and dependencies. Run it again after approving queued Jira creates. A brief tied to a ticket files onto it: one story attaches its spec to the ticket, several are filed under the ticket as their epic |
| `fx plan SLUG --link N=KEY --link epic=KEY` | Attaches tickets you created elsewhere (for example with your ticket skill) to plan stories, numbered from 1 |
| `fx ticket KEY [--brief NAME]` | Copies an existing ticket into a brief (`ticket.md`, quoted as data) and ties the brief to it, so `fx plan NAME --file` files onto that ticket. `/factory:vision KEY` runs it for you |
| `fx file --title T [--spec FILE] [--to …] [--hold] [--repo R] [--parent KEY] [--issue-type TYPE] [--after KEY,KEY]` | Files one piece of work. With `--spec`, the reviewed spec rides along and the factory builds from it; without it, the description comes from stdin |
| `fx adopt KEY [--spec FILE] [--queue] [--after KEY,KEY] [--docs-plan FILE --children KEY,KEY]` | Attaches an approved spec, dependencies or an epic's documentation plan to a ticket made elsewhere |
| `fx release KEY …` | Adds the queue label to held tickets so the next run picks them up |

## fx: Jira approvals

| Command | What it does |
| --- | --- |
| `fx outbox` | Lists pending, approved, sent and failed Jira writes |
| `fx outbox show ID\|all` | Shows the full text of one write, or all |
| `fx outbox approve ID … \| all` | Approves writes. With the Atlassian MCP it prints the writer agent to spawn; with REST it posts them |
| `fx outbox reject ID …` | Drops writes |
| `fx outbox retry ID` | Retries a failed write |
| `fx outbox flush` | Sends already-approved writes again, for example after an interrupted run |

## fx: documentation

| Command | What it does |
| --- | --- |
| `fx docs` | Lists documentation drafts (ready to publish, or waiting for their merge) and epic documentation plans (waiting for stories, or ready to write) |
| `fx docs done KEY FILE [--url URL]` | Records a published document so it stops showing up |
| `fx docs done EPIC epic` | Closes an epic's documentation plan |

## fx: jobs, step by step

The orchestrator runs these for you. You need them only to look closer or
unstick something.

| Command | What it does |
| --- | --- |
| `fx create KEY` | Starts a job for a queued ticket |
| `fx step KEY` | Advances a job and prints the next instruction (`NEXT spawn`, `gate`, `sync`, `wait` or `done`) |
| `fx gate KEY` | Runs the checks for the job's current round |
| `fx selfcheck KEY` | Runs the checks in the job's worktree; builders use it before finishing |
| `fx feedback KEY` | Your notes (stdin) on a ready, needs-human or plan-review job; starts a new round |
| `fx answer KEY` | Your answer (stdin) to a question intake asked |
| `fx approve-plan KEY` | Approves an epic's plan made during a run and creates its stories |
| `fx reject KEY` | Drops a job; the reason comes from stdin |

## fx: setup and maintenance

| Command | What it does |
| --- | --- |
| `fx init work\|personal [--force]` | Writes `factory/config.json` and the checks scripts from a profile, in the current repo or workspace |
| `fx where` | Prints the factory home `fx` would use from here |
| `fx version` | Prints the version and where the plugin lives |
| `fx skills on\|off` | Turns the optional company skills integration on or off for this workspace |
| `fx skills sync [--install] [--update]` | Re-resolves skill pins and shows which skills each role uses, optionally installing or updating the library first |
| `fx skills check` | Like `sync`, plus the library's own validate and outdated commands |
| `fx skills catalog` | Lists the installed skills with their descriptions |
| `fx guard --hook` | The guard the plugin's hook runs for factory agents; not for direct use |

Global option: `--home PATH` points `fx` at a factory home (the folder that
holds `factory/config.json`) instead of finding it from the current folder.
`FX_HOME` does the same from the environment.
