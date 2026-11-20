---
name: docs
description: Publish the documentation the software factory drafted (tech specs, overviews, guides, runbooks) after their merge requests merge, and write an epic's planned documents once its stories have merged. Use when the user types /factory:docs or asks to publish or write up factory documentation.
argument-hint: "[KEY]"
---

# Factory documentation

The factory plans documentation with the work (`/factory:vision` and the spec
writer), builders write the in-repo docs inside each merge request, and a docs
writer drafts the external ones after review. You take those drafts the last
step: check them against what actually merged, then publish them with the
user's approval. You also write the documents planned for a whole epic once
its stories have merged.

Arguments: $ARGUMENTS

`fx` is on your PATH. Run it from the factory's home.

## You run fx; the user decides

The factory guides the user's workflow. They type slash commands and answer
questions; they never need `fx`.

- Run every `fx` command yourself. Never ask the user to type one, and don't
  show fx commands as instructions to them.
- fx output names follow-up commands (`fx release KEY`, `fx outbox`,
  `fx plan SLUG --file`, `fx feedback KEY`). Those are for you: turn each into
  a short question (AskUserQuestion when you can name the options) and run it
  on their yes.
- Finish every turn that leaves work open with **Next**: the one or two things
  that move the work forward, in order, as a decision to make, a merge request
  to review (with its link) or a slash command (`/factory:vision`,
  `/factory:run`, `/factory:docs`).

## 1. See what's waiting

Run `fx docs` (limit to a KEY if one was given). It lists:

- `draft KEY <path> · <title> · ready to publish`: a job's draft whose merge
  request has merged.
- `draft … · after merge (job is …)`: not yet. Say so and skip it unless the
  user insists (publishing describes code that isn't on the base branch).
- `epic KEY · N planned doc(s): … · ready to draft` (or `x/y stories merged`):
  documents for a whole feature.

Show the list in one short table and ask which to do now (AskUserQuestion,
multi-select). Publishing is the user's call, document by document.

## 2. Refresh a draft against what merged

For each chosen draft:

1. Read it. Its header names `TITLE`, `TARGET`, `AUDIENCE` and `SOURCE`.
2. Fetch the base branch in the job's repo and find the merged commit. Set the
   source revision in the body to `<repo>@<merged commit>` (short SHA), and
   repoint code links to it.
3. Check the draft's claims against the merged code with an Explore subagent
   when they are more than a glance. Fix what changed in later rounds; keep
   anything unverified as an open question.

Never paste the full draft into the chat unless the user asks; the publishing
skill shows its own preview.

## 3. Publish

**TARGET `confluence` (work).** Use the skill named in `outputs.docs_skill` of
`factory/config.json` (the user's `atlassian-work`): invoke it with the
Skill tool and give it the refreshed draft, the space and parent from
`docs.confluence` (or the ones the draft names), and the title. That skill
owns the rest: duplicate search, the content-format guide, the full preview,
the user's approval, the write and the read-back. Don't bypass its approval.
Without a docs skill, use the Atlassian MCP directly with the same discipline:
check for a page with that title, show the complete page, publish only after
an explicit yes, read it back.

**TARGET `repo`, or a personal project with no Confluence.** External docs
then live in the repository. Offer to file them as a small docs change the
factory builds and reviews like any other:
`fx file --title "Docs: <title>" --to local < <draft path>` (or `--to github`;
add `--repo` in a workspace). The intake will route it as a docs change.

**Other targets** (a wiki, a shared drive): give the user the refreshed file
and say where it was meant to go.

After each published document, record it so it stops showing up:
`fx docs done KEY <file name> --url <page URL>`. With Jira approvals on, this
also queues a short Implementation update on the ticket. Before you finish,
run `fx outbox`, show the pending writes in one compact table and ask for
approval, as `/factory:run` does at the end of a run (`fx outbox approve`,
then spawn any `factory:tracker-write` pair it prints in the foreground).

## 4. Epic documents

When an epic shows `ready to draft` (every story merged), write its planned
`(external)` documents yourself, here, with the user:

1. Read the epic's plan (`factory/jobs/<EPIC>/plan.md` `## Documentation`,
   or `factory/specs/<EPIC>.epic.json`) and the stories' specs and merge
   requests (`fx status <story>` gives each job's folder and MR).
2. Ground the documents in the merged code at the base branch's head; use an
   Explore subagent for the reading and keep only conclusions.
3. Draft each document for its named reader, in the docs skill's templates
   (application overview, tech spec, runbook or guide), with the source
   revision and open questions. Prefer one accessible overview over a page per
   story.
4. Publish as in step 3, record each with `fx docs done <EPIC> <name> --url
   <URL>`, and when all are done, `fx docs done <EPIC> epic`.

In-repo epic documents (an ADR or `docs/` page about the whole feature) go
through the factory: `fx file --title "Docs: <title>" …` with the content as
the description.

## Rules

- Publish nothing without the user's explicit approval of that exact page.
- Never publish secrets, credentials, customer data or unverified claims.
- Never edit a job's files under `factory/jobs/` other than reading drafts;
  write refreshed drafts to a scratch copy if you need one.
