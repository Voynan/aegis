# Every milestone starts with a spec and a plan

Applies to every milestone of [docs/dev/v1-todo.md](../../docs/dev/v1-todo.md) and, after 1.0, of
[docs/dev/v2-django.md](../../docs/dev/v2-django.md) — scaffolding, release and documentation
milestones included. The size of a milestone changes the length of its spec and plans, never
whether they exist.

## Dependency

The workflow runs on the **superpowers** plugin (`superpowers@claude-plugins-official`), enabled in
[.claude/settings.json](../settings.json). If its skills are missing from the session, install it
with `/plugin install superpowers@claude-plugins-official`, and do not start the milestone until it
is available.

## Steps

1. **Spec — `superpowers:brainstorming`.**
   - Start from the milestone's tasks in the checklist and its definition of done in
     [docs/roadmap.md](../../docs/roadmap.md). Ask only what `docs/` does not already answer.
   - Write the spec as a delta over `docs/`, to
     `docs/dev/superpowers/specs/YYYY-MM-DD-mN-<topic>-design.md`.
   - A new or changed decision becomes an ADR in [docs/decisions.md](../../docs/decisions.md) and an
     edit to every document it affects. The normative documents win over the spec.
   - **Gate:** the author approves the written spec.
2. **Plans — `superpowers:writing-plans`.**
   - Write one plan per slice that can be built, tested and reviewed on its own, to
     `docs/dev/superpowers/plans/YYYY-MM-DD-mN-<k>-<topic>.md`.
   - A small milestone gets one plan. It gets several when it spans modules reviewed separately or
     carries more than about ten tasks. Work on a crypto module (`stream.py`, `envelope.py`,
     `format.py`) always gets a plan of its own, because its pull request answers the review
     questions of [docs/contributing.md § 7](../../docs/contributing.md#7-reviewing) on its own.
   - Each task names the test to write first, the command that must fail and why, the minimal
     implementation, and the command that must then pass.
   - **Gate:** the author approves each plan.
3. **Execution — `superpowers:executing-plans`, inline.** Apply
   [tdd-and-testing.md](tdd-and-testing.md) to every task. Use
   `superpowers:subagent-driven-development` only when the author asks for subagents.
4. **Verification — `superpowers:verification-before-completion`.** Demonstrate the milestone's
   definition of done with command output; never just assert it.
5. **Close.**
   - Tick the milestone's tasks and status in the checklist.
   - Update the documents to describe what was built, including `docs/diagrams.md` when a flow
     changed.
   - Offer the day's diary entry (the `diary` skill).

## Conventions

- No automatic commits, branches or worktrees. Skip those steps of the superpowers skills; propose
  atomic commits with the project's `git-commit` skill and wait for the author to authorize them.
- Specs and plans live in `docs/dev/superpowers/`, which is git-ignored
  ([ADR-0039](../../docs/decisions.md#adr-0039-milestone-specs-and-plans-are-local-working-files)).
  They are not normative. Every decision a spec makes that outlives the milestone lands in an ADR
  or a document; closing a milestone checks that it did.
- Subagents only when the author asks for them.
