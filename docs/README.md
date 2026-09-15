# Aegis documentation

Design and architecture documents, written before implementation starts.
Everything here is normative unless a section says otherwise.

## Reading order

| # | Document | Answers |
|---|---|---|
| 1 | [product.md](product.md) | What Aegis is, who it is for, what it promises and refuses |
| 2 | [architecture.md](architecture.md) | How the code is organised and why it is organised that way |
| 3 | [stack.md](stack.md) | Dependencies, tools and version policy, and why each was chosen |
| 4 | [file-format.md](file-format.md) | The byte-level format — the one artifact that cannot change |
| 5 | [security.md](security.md) | Threat model, guarantees, non-guarantees, disclosure |
| 6 | [usage.md](usage.md) | How a developer actually uses the library |
| 7 | [tests.md](tests.md) | The testing strategy — which is the argument for trusting the code |
| 8 | [performance.md](performance.md) | Performance objectives, how they are measured, what blocks a release |
| 9 | [decisions.md](decisions.md) | The decision log (ADRs), including rejected alternatives |
| 10 | [roadmap.md](roadmap.md) | Implementation milestones and what blocks 1.0 |
| 11 | [contributing.md](contributing.md) | How to work on this repository |

[initial-spec.md](initial-spec.md) is the original approved design spec (2026-09-07). It is
kept as a historical record and is **not** updated. Where these documents differ from it, they
say so explicitly and the reason is recorded in [decisions.md](decisions.md).

## Status

Pre-implementation. No code exists yet. The file format is frozen once
[ADR-0013](decisions.md#adr-0013-freeze-the-format-at-milestone-m4) closes at milestone M4
(see [roadmap.md](roadmap.md)).

## Open questions

Items that need a human decision before or during implementation are collected in
[architecture.md § Open questions](architecture.md#16-open-questions). Resolved so far:

| Question | Resolution |
|---|---|
| Q1 — chunk AAD vs. rotation | AAD covers the immutable header core ([ADR-0014](decisions.md#adr-0014-chunk-aad-covers-the-immutable-header-core-only)) |
| Q2 — KEK encoding in env vars | Strict base64 ([ADR-0015](decisions.md#adr-0015-keks-in-environment-variables-are-base64)) |
| Q3 — empty `context` | Required argument; `{}` legal, `None` rejected ([ADR-0020](decisions.md#adr-0020-context-is-required-but-may-be-empty)) |
| Q5 — domain separation | Labelled AAD hashes ([ADR-0019](decisions.md#adr-0019-domain-separated-aad-hashes)) |
| Q6 — PyPI name | `aegis-voynan`, imported as `aegis` ([ADR-0018](decisions.md#adr-0018-distribute-as-aegis-voynan-import-as-aegis)) |

Still open, by the milestone each must be decided before:

| Before | Questions |
|---|---|
| M0 | Q17 (Hypothesis database), Q18 (PyPI name reservation) |
| M1 | Q20 (error for a short non-Aegis file) |
| M2 | Q19 (public review before the freeze), Q22 (the 2³² chunk limit) |
| M3 | Q10 (`inspect` API), Q12 (`CustodyBlock` export), Q21 (`unseal_to_path` durability), Q23 (context check order), Q26 (custody-mode mismatches) |
| M4 | Q9 if its format option is considered, Q25 (missing negative vector) |
| M5 | Q8 (rotation on Windows), Q9 (torn writes), Q11 (rotation API), Q15 (recursive rotation) |
| M6 | Q13 (CLI keys), Q14 (CLI context types), Q24 (`inspect` sizes) |
| M7 | Q4 (unsaved Django instances), Q16 (the field's `Vault`) |
| M9 | Q7 (`Receipt.kek_id`) |
