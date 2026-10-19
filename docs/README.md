# Aegis documentation

Design and architecture documents, written before implementation starts.
Everything here is normative unless a section says otherwise.

## Reading order

| # | Document | Answers |
|---|---|---|
| 1 | [product.md](product.md) | What Aegis is, who it is for, what it promises and refuses |
| 2 | [diagrams.md](diagrams.md) | How it works, in pictures — the mechanism before the details; not normative |
| 3 | [architecture.md](architecture.md) | How the code is organised and why it is organised that way |
| 4 | [structure.md](structure.md) | Where every file and directory lives, and where a new one goes |
| 5 | [stack.md](stack.md) | Dependencies, tools and version policy, and why each was chosen |
| 6 | [file-format.md](file-format.md) | The byte-level format — the one artifact that cannot change |
| 7 | [security.md](security.md) | Threat model, guarantees, non-guarantees, disclosure |
| 8 | [usage.md](usage.md) | How a developer actually uses the library |
| 9 | [tests.md](tests.md) | The testing strategy — which is the argument for trusting the code |
| 10 | [performance.md](performance.md) | Performance objectives, how they are measured, what blocks a release |
| 11 | [decisions.md](decisions.md) | The decision log (ADRs), including rejected alternatives |
| 12 | [roadmap.md](roadmap.md) | Implementation milestones and what blocks 1.0 |
| 13 | [contributing.md](contributing.md) | How to work on this repository |

[initial-spec.md](initial-spec.md) is the original approved design spec (2026-09-07). It is
kept as a historical record and is **not** updated. Where these documents differ from it, they
say so explicitly and the reason is recorded in [decisions.md](decisions.md).

## Plans

Working plans live in [dev/](dev/). They are committed but **not normative**: when a plan and a
document above disagree, the document wins and the plan gets fixed.

| Plan | Answers |
|---|---|
| [dev/v2-django.md](dev/v2-django.md) | The plan for the Django adapter, after 1.0 |

`dev/notes.md` and `dev/diary/` are personal notes and stay out of git.

## Status

Pre-implementation. No code exists yet.

The design review of 2026-10-18 revised the format before the freeze
([ADR-0026](decisions.md#adr-0026-the-library-draws-every-data-key-key-sources-only-wrap-and-unwrap)
to [ADR-0033](decisions.md#adr-0033-context-values-must-have-an-exactly-accepted-type)):
- library-drawn data keys;
- a per-file salt with key commitment;
- a typed custody record that holds KMS wraps;
- provable truncation errors.

It also added pull-style and seekable readers, and moved the Django adapter to V2. The file
format is frozen once [ADR-0013](decisions.md#adr-0013-freeze-the-format-at-milestone-m4) closes
at milestone M4 (see [roadmap.md](roadmap.md)).

## Open questions

Every question in [architecture.md § 16](architecture.md#16-open-questions) — Q1 to Q46 — is
decided or moved to the V2 plan. Q27–Q46 were raised by the review of 2026-10-18.

| Group | Questions | Where decided |
|---|---|---|
| Format (settled before the M4 freeze) | Q1, Q3, Q5, Q6, Q25, Q27, Q29–Q32, Q45 | ADR-0014, 0018, 0019, 0020, 0026–0030, 0033 |
| Public API and behaviour | Q7, Q10, Q12, Q20–Q23, Q26, Q36, Q38, Q40, Q46 | ADR-0026, 0031, 0032, 0036, 0037 |
| Keys and custody | Q2, Q28, Q33, Q37 | ADR-0015, 0029 |
| Rotation | Q8, Q9, Q11, Q15, Q43 | ADR-0035 |
| CLI | Q13, Q14, Q24 | ADR-0036 |
| Project and process | Q17, Q18, Q19, Q44 | ADR-0037, 0023 |
| Claims corrected | Q34, Q35 | security.md §§ 1, 3, 5.2 |
| Moved to V2 | Q4, Q16, Q39, Q41, Q42 | ADR-0034, [dev/v2-django.md](dev/v2-django.md) |

Two decisions are actions for a person, and both are due now:

| Action | Due | Why |
|---|---|---|
| Publish the `0.0.0` placeholder that reserves `aegis-voynan` (Q18) | M0 | a pending publisher alone does not reserve the name |
| Request public review of [file-format.md](file-format.md) (Q19) | before M2 | after the M4 freeze, a format finding costs a new format version |

Questions for the Django adapter (V2-Q1 to V2-Q7) live in [dev/v2-django.md](dev/v2-django.md).
