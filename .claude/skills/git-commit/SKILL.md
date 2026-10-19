---
name: git-commit
description: Create clean, well-structured git commits using the Conventional Commits standard. Use this skill whenever the user asks to commit changes — phrases like "commit this", "make a commit", "commit my changes", "git commit", "save this to git", "let's commit", "crie os commits". Trigger even when the user doesn't say the words "conventional commits", since this skill defines HOW to commit — atomic commits split by responsibility, English messages, the type(scope) subject format, and optional Claude co-authorship. Do NOT use it to commit on your own initiative when a task ends (propose the commits and wait), for pushing, opening PRs, or rewriting published history.
---

# Git Commit

Turn a pile of working-tree changes into a clean series of commits. Two things matter most: **the history is split into atomic commits** (one responsibility per commit) and **every message follows Conventional Commits**, written in English.

A messy `git add -A && git commit -m "stuff"` is fast but leaves a history nobody can review, revert, or bisect. The whole point of this skill is to do the opposite: take a little more care up front so the log stays useful forever.

## The workflow

Work through these steps in order. Show the user what you're doing as you go — committing is local and reversible, but it's still their repository.

### 1. Survey the changes

Before touching anything, build a mental model of what changed and why.

```bash
git status --short -uall    # what's modified/untracked/staged, every untracked file listed
git diff                    # unstaged changes, hunk by hunk
git diff --staged           # anything already staged
git log --oneline -10       # match the repo's existing type/scope conventions
```

`git diff` does not show untracked files: read every new file in full before it goes into a commit.

Reading recent log entries matters: a repo may already use scopes like `(api)`, `(ui)`, `(deps)`. Match the house style instead of inventing your own.

### 2. Group changes by responsibility

This is the heart of the skill. Look at everything that changed and sort it into **logically independent units**. Each unit becomes one commit. A good test: _could this commit be reverted on its own without breaking an unrelated feature, and does its subject line describe the whole thing without needing "and"?_ If a single commit would need "and" to describe it (e.g. "add login form and fix typo in footer and bump lodash"), that's three commits.

Common seams to split along:

- A bug fix vs. a new feature vs. a refactor that happened in the same session
- Production code vs. its tests (often fine together, but split if they're unrelated)
- Dependency bumps vs. the feature that needed them
- Formatting/whitespace-only changes vs. behavioral changes (always separate — a behavioral diff buried in a reformat is invisible in review)
- Changes to different modules or domains that don't depend on each other

If everything genuinely is one coherent change, one commit is correct. Don't split for the sake of splitting.

### 3. Stage each group precisely

Avoid `git add -A` / `git add .` when the goal is atomic commits — they sweep everything into one staging area. Instead stage the files (or hunks) for **one** group at a time:

```bash
git add path/to/file_a.ts path/to/file_b.ts     # stage by path
git rm --cached path/to/removed_file.ts          # stage a deletion or the old half of a move
```

When a single file holds changes belonging to different commits, stage only the part for the current commit. A human can use `git add -p`; an agent cannot, because it is interactive. Use one of these instead:

- **Patch:** `git diff -- path > part.patch` into a temporary directory, delete the hunks that belong to a later commit, then `git apply --cached part.patch`.
- **Intermediate copy:** keep a copy of the final file, write the version that holds only this commit's changes, `git add` it, commit, then restore the final file for the next commit.

Check `git diff --staged` before every commit, and after the last one confirm with `git diff` and `git status` that the working tree is exactly where it started.

### 4. Write the message and commit

Use the Conventional Commits format. The minimum, required form is a single subject line:

```
type(scope): short imperative summary
```

Then commit. Prefer a heredoc so multi-line bodies and trailers are clean:

```bash
git commit -F - <<'EOF'
feat(auth): add password reset flow

Users can now request a reset link from the login page.

Co-authored-by: Claude <noreply@anthropic.com>
EOF
```

(Blank lines separate the paragraphs: subject, then body, then the trailer block. Several `-m` flags do the same, one paragraph each.)

### 5. Verify

```bash
git log --oneline -5
git status            # confirm the working tree is in the state you expect
```

Confirm each commit landed and that nothing unintended was swept in.

## Message format reference

### Subject: `type(scope): short message`

- **type** — one of the types below, lowercase.
- **scope** — the area of the codebase affected, lowercase, in parentheses (e.g. `api`, `auth`, `parser`, `ui`, `deps`, `ci`). Include a scope whenever a meaningful one exists. Per the Conventional Commits spec the scope is optional, so if a change is genuinely repo-wide with no single scope, `type: subject` is acceptable — but default to providing one.
- **short message** — imperative mood ("add", not "added" or "adds"), lowercase start, **no trailing period**, and short: the whole subject line at most 72 characters, aiming for ~50. Imperative mood reads as a command: "if applied, this commit will _add password reset_."
- Everything is written in **English**.

### Types

| Type       | Use for                                                        |
| ---------- | -------------------------------------------------------------- |
| `feat`     | A new feature or capability                                    |
| `fix`      | A bug fix                                                      |
| `docs`     | Documentation only                                             |
| `style`    | Formatting, whitespace, semicolons — no behavior change        |
| `refactor` | Code change that neither fixes a bug nor adds a feature        |
| `perf`     | A performance improvement                                      |
| `test`     | Adding or correcting tests                                     |
| `build`    | Build system or external dependencies (npm, cargo, webpack)    |
| `ci`       | CI configuration and scripts                                   |
| `chore`    | Maintenance that doesn't touch src or tests (configs, tooling) |
| `revert`   | Reverting a previous commit                                    |

### Body (optional)

Add a body when the change needs a _why_ that the subject can't carry — non-obvious fixes, trade-offs, context for future readers. Separate it from the subject with a blank line and wrap lines at ~72 characters. Explain **why**, not **what** (the diff already shows what).

### Footers (optional)

- Breaking changes: a `BREAKING CHANGE: <description>` footer, or a `!` after the type/scope (`feat(api)!: drop v1 endpoints`).
- Issue references: `Closes #123`, `Refs #456`.

## Claude co-authorship

Adding Claude as a co-author is permitted and on by default. Append this trailer as the last paragraph of the message, after a blank line:

```
Co-authored-by: Claude <noreply@anthropic.com>
```

GitHub and GitLab recognize the `Co-authored-by:` trailer and attribute the commit to both authors. Omit it if the user asks you to, or if the repo has a convention against it.

## Examples

**One session, three responsibilities → three commits**

A session touched the auth module, reformatted an unrelated util file, and bumped a dependency. That's three commits, not one:

```
feat(auth): add password reset flow
style(utils): reformat date helpers with prettier
build(deps): bump zod to 3.23
```

**A fix that needs a body**

```
fix(api): prevent double-charge on retried payments

Stripe retries a request after a network timeout could create a
second charge. Add an idempotency key derived from the order id so
retries collapse to a single charge.

Closes #482
Co-authored-by: Claude <noreply@anthropic.com>
```

**Splitting one file across two commits**

A single `routes.ts` contains both a new endpoint and a typo fix in an existing route. Stage only the new-endpoint hunks first, with a patch or an intermediate copy (step 3):

```
feat(api): add GET /health endpoint
```

then stage and commit the remaining hunk:

```
fix(api): correct status code on 404 handler
```

## This repository

- [docs/contributing.md § 8](../../../docs/contributing.md#8-commits-and-prs) is the house rule: Conventional Commits, an imperative subject of at most 72 characters, a body that says **why**, the ADR or issue the change comes from, and `!` or a `BREAKING CHANGE:` footer for anything that breaks the public API.
- Scopes in use: none for repository-wide documentation (`docs:`), a document or area otherwise (`docs(stack):`, `docs(dev):` for the plans in `docs/dev/`), `claude` for `.claude/`.
- `docs/dev/diary/` and `docs/dev/notes.md` are personal and git-ignored. Never stage or force-add them.
- Commit only when the author asks. At the end of a task, propose the commits and wait (`.claude/rules/milestone-specs-and-plans.md`).

## Guardrails

- **Never commit secrets.** Before staging, glance at the diff for API keys, tokens, passwords, `.env` contents, private keys. If you spot one, stop and flag it.
- **Don't push or open PRs from this skill.** Committing is local. Pushing publishes to a shared remote, so leave `git push`, PRs, and tags to the user unless they explicitly ask.
- **Don't rewrite published history.** No `commit --amend`, rebase, or `--force` on commits that may already be pushed, unless the user explicitly requests it.
- **Pause on surprises.** If the working tree contains far more than you expected, or unrelated changes you didn't make, show the user before committing rather than guessing.
- **Respect failing hooks.** If a pre-commit hook rejects the commit, read its output and fix the underlying issue — don't bypass it with `--no-verify` unless the user asks.