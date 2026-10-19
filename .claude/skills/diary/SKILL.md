---
name: diary
description: Write or update the developer's diary entry for a day in docs/dev/diary/DD-MM-YYYY.md — what was done and the next planned step, headed by a Markdown comment with the developer, the finish time and the Claude session ids. Use when the developer asks to write, update or close the diary, the day's log or a session summary ("escreva o diary", "diário de hoje", "fecha o dia", "write today's diary"). Entries are personal and never committed.
argument-hint: "[DD-MM-YYYY]"
---

# Developer diary

A short private log that lets the developer pick up exactly where they stopped. One file per day,
written in the developer's own language, never published.

## Where it lives

- `docs/dev/diary/DD-MM-YYYY.md`, for today unless the developer names another day — for example
  `docs/dev/diary/18-10-2026.md`.
- `docs/dev/diary/` is git-ignored. Check it before writing with
  `git check-ignore -q docs/dev/diary/<file>`. If the file would not be ignored, stop and tell the
  developer.
- Never stage, commit, force-add or push an entry, and never quote one in a pull request, an
  issue or a published document. The diary is a convention for the developer, nothing more.

## Gather the header

| Field | Source |
|---|---|
| `developer` | `git config user.name` and `git config user.email` |
| `finished` | `date '+%Y-%m-%d %H:%M %z'`, taken when the entry is written — the end of the work it reports |
| `claude-sessions` | `$CLAUDE_CODE_SESSION_ID`. If it is empty, use the newest `*.jsonl` file name in `~/.claude/projects/<working directory with every "/" replaced by "-">/` |

## Write the entry

```markdown
<!--
developer: <name> <email>
finished: <YYYY-MM-DD HH:MM ±hhmm>
claude-sessions:
  - <session id>
-->

# DD-MM-YYYY

## <What was done, in the developer's language>

- one line per result: what changed and where (ADR, file, commit hash)

## <Next planned step, in the developer's language>

- the next concrete action, and what it waits on, if anything
```

- **Language.** Write in the developer's native language — the one they write to you in. The
  headings follow it: `O que foi feito` and `Próximo passo` in Portuguese, `What was done` and
  `Next step` in English.
- **Concise and direct.** Report results, not narration: three to eight bullets of work, one to
  three of next steps. Name files, ADRs and commit hashes so the developer can jump straight to
  them.
- **Always both sections.** An entry without a next step is not finished.
- **No secrets.** Never paste keys, tokens or plaintext the project encrypts, even in a private
  file.

## A day that already has an entry

Update the file instead of replacing it:
- keep every session id already listed and add the current one;
- set `finished` to now;
- add new bullets under the work section without repeating earlier ones;
- rewrite the next-step section so it reflects the latest plan.
