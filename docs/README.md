# Aegis documentation

Design and architecture documents, written before implementation starts.
Everything here is normative unless a section says otherwise.

## Reading order

| # | Document | Answers |
|---|---|---|
| 1 | [product.md](product.md) | What Aegis is, who it is for, what it promises and refuses |
| 2 | [architecture.md](architecture.md) | How the code is organised and why it is organised that way |
| 3 | [file-format.md](file-format.md) | The byte-level format — the one artifact that cannot change |
| 4 | [security.md](security.md) | Threat model, guarantees, non-guarantees, disclosure |
| 5 | [usage.md](usage.md) | How a developer actually uses the library |
| 6 | [tests.md](tests.md) | The testing strategy — which is the argument for trusting the code |
| 7 | [decisions.md](decisions.md) | The decision log (ADRs), including rejected alternatives |
| 8 | [roadmap.md](roadmap.md) | Implementation milestones and what blocks 1.0 |
| 9 | [contributing.md](contributing.md) | How to work on this repository |

[initial-spec.md](initial-spec.md) is the original approved design spec (2026-09-07). It is
kept as a historical record and is **not** updated. Where these documents differ from it, they
say so explicitly and the reason is recorded in [decisions.md](decisions.md).

## Status

Pre-implementation. No code exists yet. The file format is frozen once
[ADR-0013](decisions.md#adr-0013-freeze-the-format-at-milestone-m4) closes at milestone M4
(see [roadmap.md](roadmap.md)).

## Open questions

Items that need a human decision before or during implementation are collected in
[architecture.md § Open questions](architecture.md#16-open-questions). Three of them change
the format or the public API and should be settled first:

1. The chunk-AAD / rotation contradiction — **resolved here**, needs confirmation
   ([ADR-0014](decisions.md#adr-0014-chunk-aad-covers-the-immutable-header-core-only)).
2. The encoding of a KEK inside an environment variable — unspecified in `initial-spec.md`
   ([ADR-0015](decisions.md#adr-0015-keks-in-environment-variables-are-base64)).
3. Whether `context` may be empty ([Q3](architecture.md#16-open-questions)).
