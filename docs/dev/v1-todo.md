# Aegis 1.0 — TODO

Working checklist for shipping 1.0, compiled from [`docs/`](../README.md) on 2026-09-14 and
last reconciled with them on 2026-10-18: after the design review (ADR-0026 to ADR-0037), the
new [diagrams.md](../diagrams.md), the move of the plans into `docs/dev/`, and the workflow rules
in [`.claude/rules/`](../../.claude/rules/).

**Not normative.** When this file and a document disagree, the document wins and this file gets
fixed. It is committed, like [v2-django.md](v2-django.md) beside it; `docs/dev/notes.md`,
`docs/dev/diary/` and `docs/dev/superpowers/` (the milestone specs and plans, ADR-0039) are
git-ignored.

**Legend** — 🔒 must hold before the M4 format freeze · 👤 an action for a person, not code

---

## 1. Next actions

- [x] Commit the pending documentation work — `f3e682a`, 2026-09-14.
- [x] Commit the documentation work of 2026-09-21 and 22 — `be7ba4d`, `fdb2b9b`, `c582ee9`.
- [x] Commit the work of 2026-10-18, one concern per commit: the project's Claude setup
  (`git-commit` skill, rules, `diary` skill, superpowers), the design review (ADR-0026–0037), the
  diagrams, this checklist, and the spec-and-plan workflow in the documents.
- [ ] 👤 **Q19 — request public review of `file-format.md` now** (cryptography mailing lists,
      `r/crypto`, the `age`/Tink communities), before any code depends on it.
- [ ] 👤 **Q18 — reserve `aegis-voynan`:** pending trusted publisher, then a `0.0.0` placeholder
      through `release.yml`.
- [ ] Start M0 with its spec and plan — `superpowers:brainstorming`, then
      `superpowers:writing-plans` — and nothing else first. Nothing else blocks it.

## 2. Status

| Milestone | State | Blocked by |
|---|---|---|
| M0 — Scaffolding | not started | — |
| M1 — `errors`, `format`, `context` | not started | M0 |
| M2 — `envelope`, `stream` | not started | M1; the Q19 review request should be out |
| M3 — `keys`, `vault`, `readers`, `info` | not started | M2 |
| M4 — Freeze 🔒 | not started | M3; format review feedback triaged |
| M5 — `rotate` | not started | M4 |
| M6 — CLI | not started | M3, M5 |
| M7 — Django adapter | **moved to V2** (ADR-0034, [v2-django.md](v2-django.md)) | — |
| M8 — Docs and public review | not started | M0–M6 |
| M9 — 1.0 | not started | M8 |

## 3. Decisions

Every question Q1–Q46 is decided or moved to V2 ([architecture.md § 16](../architecture.md#16-open-questions)).
The ones that shape the code, in one place:

- **Format (🔒):** 73-byte core + custody record (ADR-0028); per-file salt, derived body key and
  nonce prefix, key commitment (ADR-0027); library-drawn DEKs (ADR-0026); truncation
  classification and canonical final chunk (ADR-0030); exact context types (ADR-0033).
- **API:** `EnvKey` / `FileKey` / `BytesKey` with an entropy floor (ADR-0029); `KeySource`
  protocol over bytes (ADR-0026); `sealed` / `unsealed` readers, seekable when the source is
  (ADR-0032); `inspect` (ADR-0036); `rotate` / `rewrap` (ADR-0035); `KeyMismatch`; `seal_bytes`
  refused on `CallerHeld()` (Q46).
- **I/O:** full segments, full writes, non-blocking and text streams refused (ADR-0031).
- **Rotation:** `pwrite` or `seek` + `write`, then `fsync`; torn writes journaled (ADR-0035).
- **CLI:** `--key-env` / `--key-file` / `--previous-*`, `--key-out` / `--key-in`, every context
  type, labelled size-derived numbers, recursive semantics (ADR-0036, ADR-0035).
- **Workflow:** every milestone starts with an approved spec and plan(s) written with superpowers,
  and all code is written test-first
  ([milestone-specs-and-plans.md](../../.claude/rules/milestone-specs-and-plans.md),
  [tdd-and-testing.md](../../.claude/rules/tdd-and-testing.md)).
- **Review:** one maintainer, so no required approvals. Crypto PRs answer the six questions of
  contributing.md § 7 in writing, and the M2 and M4 reads are done by someone else (ADR-0038).
- **Project:** Python 3.11–3.14 (ADR-0023), `click` (ADR-0021), Hatchling (ADR-0022),
  `.hypothesis/` ignored with failures pinned as `@example` (Q17). Milestone specs and
  plans live in `docs/dev/superpowers/`, git-ignored (ADR-0039); `diagrams.md` is kept in step with the documents (contributing.md § 6).

## 4. Milestones

Every milestone opens with the same first task, and its code is written test-first.

### M0 — Repository scaffolding

- [ ] Spec and plan(s) in `docs/dev/superpowers/` (git-ignored, ADR-0039), written with superpowers and
  approved before any other task.

**Repository**

- [ ] Replace `.gitignore` (still the Ruby template) with the list in
  [structure.md § 5](../structure.md#5-never-committed), `.hypothesis/` included. **Keep
  `docs/dev/notes.md` and `docs/dev/diary/`** — and only those: the plans in `docs/dev/` stay
  committed.
- [ ] Create the paths [structure.md § 2](../structure.md#2-the-tree) marks M0.
- [ ] `README.md` skeleton: title, the threat-model paragraph first, pre-1.0 status,
  `pip install aegis-voynan`.
- [ ] `SECURITY.md` at the root, pointing at [security.md § 8](../security.md#8-reporting-a-vulnerability).
- [ ] Turn on **private vulnerability reporting** in the repository settings.
- [ ] Ruleset on `main`: required status checks, linear history, no force pushes.
- [ ] `CODEOWNERS` for `src/aegis/stream.py`, `envelope.py`, `format.py`, `keys.py`,
  `readers.py`, `rotate.py`, `docs/file-format.md` and `tests/vectors/`. No required approvals
  while there is one maintainer (ADR-0038).
- [ ] Protect `v*` tags and register the maintainers' signing keys.
- [ ] Dependabot for `uv` and `github-actions`.

**Packaging**

- [ ] `pyproject.toml` from [stack.md § 5](../stack.md#5-packaging): `requires-python = ">=3.11"`,
  the `[cli]` extra only, the `dev` group.
- [ ] `src/aegis/__init__.py` with a lazy `__version__`, and `src/aegis/py.typed`.
- [ ] Tool configuration from [stack.md § 6.3](../stack.md#63-tool-configuration): `TID251` bans
  `os.urandom`, `os.environ`, `os.getenv` and `click`, with per-file ignores for `keys.py`,
  `vault.py` and `cli/` only. A per-file ignore lifts the whole rule, so the AST purity test
  (tests.md § 6) is what narrows `os.urandom` to `vault.py` and the environment to `keys.py`.
- [ ] `tools/coverage_gates.py`: 100 for `stream.py`, `envelope.py`, `format.py`; 95 for
  `context.py`, `keys.py`, `readers.py`, `rotate.py`; 90 for the rest.
- [ ] `.pre-commit-config.yaml` with `repo: local` hooks (`uv run ruff check`,
  `uv run ruff format`, `uv lock --check`).
- [ ] `uv lock`, and commit `uv.lock`.

**PyPI** 👤

- [ ] Pending trusted publisher for `aegis-voynan`: repository `Voynan/aegis`, workflow
  `release.yml`, environment `pypi`.
- [ ] Publish the `0.0.0` placeholder through it (Q18).

**CI** — [stack.md § 7](../stack.md#7-cicd)

- [ ] `ci.yml`: `setup-uv` pinned by SHA → `uv sync --locked` → ruff → mypy → zizmor → pytest
  on Python 3.11–3.14 × Linux/macOS/Windows → the `lowest-direct` floor job → coverage gates →
  a guard on changes to `tests/vectors/`.
- [ ] `nightly.yml`: the Hypothesis `nightly` profile; `pip-audit` over the locked tree;
  `mutmut` once M2 lands.
- [ ] `bench.yml`: weekly, on tags, manual; empty suite for now.
- [ ] `release.yml`: signed `v*` tag → `pip-audit` → `uv build` → frozen vectors against the
  built wheel → `pypa/gh-action-pypi-publish` over OIDC, with attestations.

**DoD**

- [ ] A green CI run on an empty package on every matrix cell, including `lowest-direct`.
- [ ] `uv sync --all-extras` works on Linux, macOS and Windows.
- [ ] The placeholder release exists on PyPI.

### M1 — The pure core: `errors`, `format`, `context`

- [ ] Spec and plan(s) in `docs/dev/superpowers/` (git-ignored, ADR-0039), written with superpowers and
  approved before any other task.
- [ ] `errors.py`: the hierarchy of [architecture.md § 9](../architecture.md#9-error-model),
  `KeyMismatch` and `TruncatedFile` under `UnsealFailed`; structured attributes
  (`UnknownKek.file_key_id`, `.file_custody`, `.available_key_ids`, `KeyMismatch.reason`, …).
- [ ] `format.py`: the 73-byte core and the custody record ↔ dataclasses; validation in the order
  of [file-format.md § 6.2](../file-format.md#62-unsealing) — magic prefix, version, suite, then
  custody byte, `custody_len`, `payload_len`, padding, zero `key_id`; constants for offsets,
  `MAX_CUSTODY_LEN = 4096` and every label (`aegis-hdr-v1\x00`, `aegis-ctx-v1\x00`,
  `aegis-custody-v1\x00`, `aegis-kek-id\x00`, and the four HKDF infos).
- [ ] `context.py`: exact types (ADR-0033), `bool` before `int`, every rejection; labelled hash.
- [ ] Tests: offsets against literals; Hypothesis header round-trip in all three custody modes;
  `from_bytes` raises nothing outside `FormatError` up to 73 + 4 096 bytes; the context table
  including `IntEnum`, `StrEnum`, `bytearray`.
- [ ] DoD: 100 % branch coverage on `format.py`; every rejection has a table-driven test.

### M2 — `envelope.py` and `stream.py`

- [ ] Spec and plan(s) in `docs/dev/superpowers/` (git-ignored, ADR-0039), written with superpowers and
  approved before any other task.
- [ ] `envelope.py`: `schedule(dek, salt)` → body key, nonce prefix, commitment; `kek_id`;
  `wrap_local` / `unwrap_local` (zero nonce, AAD = custody AAD ‖ `kek_id`).
- [ ] `stream.py`: per-chunk primitives with explicit index and `last`; encrypt/decrypt
  iterators; read-ahead; the truncation table of ADR-0030; the empty-final-chunk rule;
  `MAX_CHUNKS` as a parameter; `read_exactly` / `write_all` with the I/O contract of ADR-0031;
  forward-only, never seeking, never buffering more than one segment.
- [ ] Tests: round-trip at `BOUNDARIES`; the short-read source and partial-write sink; the
  adversarial property for this layer; P6, P10.
- [ ] `mutmut` over `stream.py` and `envelope.py` wired into `nightly.yml`.
- [ ] 👤 Request review of `stream.py` and `envelope.py` (Q19).
- [ ] DoD: each fits on one screen; 100 % branch coverage; a second person read both against
  `file-format.md`.

### M3 — `keys.py`, `vault.py`, `readers.py`, `info.py`

- [ ] Spec and plan(s) in `docs/dev/superpowers/` (git-ignored, ADR-0039), written with superpowers and
  approved before any other task.
- [ ] `keys.py`: `EnvKey`, `FileKey` (one trailing `\n` / `\r\n` tolerated), `BytesKey`; strict
  base64; 32 bytes; entropy floor (all printable ASCII, or < 16 distinct values → reject);
  duplicates; `CallerHeld`; the `KeySource` protocol — `key_id`, `capacity`, `wrap`, `unwrap`,
  with `unwrap` raising `UnknownKek` for an unknown key and `KeyMismatch` for a payload that does
  not authenticate.
- [ ] `vault.py`: `seal`, `unseal`, `seal_bytes`, `unseal_bytes`, `unseal_to_path`, `sealed`,
  `unsealed`; `os.urandom` here only, behind the pure seam the vectors call; context and custody
  arguments checked before any read (Q23, Q26); `seal_bytes` refused on `CallerHeld()` (Q46);
  `unseal_to_path` with mode `0600` and a directory `fsync` on POSIX (Q21).
- [ ] `readers.py`: `SealedReader` (receipt after EOF), `UnsealedReader` (seekable path: final
  chunk authenticated at open, `size`, `seek` / `tell`); `chunks()` closes; no `name`; closing
  closes the source.
- [ ] `info.py`: `inspect()` → `FileInfo`, sizes labelled as derived, `size_consistent`.
- [ ] `Receipt.key_id` (Q7); redacted `__repr__` everywhere.
- [ ] `aegis/__init__.py` exports exactly [architecture.md § 2.2](../architecture.md#22-the-public-api).
- [ ] Tests: all three custody modes end to end (external through a fake KMS that imports only
  the public API); readers' equivalence and random-access properties; P3, P4, P12, P14; the
  secret-hygiene test; one `Vault` shared by threads; `unseal_to_path` leaves nothing behind on
  failure and `fsync`s before renaming, Windows included.

### M4 — Freeze the format 🔒

- [ ] Spec and plan(s) in `docs/dev/superpowers/` (git-ignored, ADR-0039), written with superpowers and
  approved before any other task.
- [ ] Gate: `file-format.md` review feedback triaged; no open issue touching bytes.
- [ ] `tests/vectors/generate.py`, run by hand: every positive case in all three custody modes
  (with derived values), every negative vector of [tests.md § 3](../tests.md#3-layer-1--frozen-vectors-kat),
  the deliberately non-canonical case.
- [ ] Hand-check offset by offset with a second person; record both names in the PR.
- [ ] KAT both directions; activate the `tests/vectors/` change guard.
- [ ] DoD: the vector file is committed with its "FROZEN" note; CI runs it on every matrix cell;
  no code path anywhere in the repository rewrites it.

### M5 — `rotate.py`

- [ ] Spec and plan(s) in `docs/dev/superpowers/` (git-ignored, ADR-0039), written with superpowers and
  approved before any other task.
- [ ] `vault.rotate(path)`: leftover-journal recovery first; DEK recovered and commitment checked
  before writing; journal written and synced (with its directory on POSIX); one write of the
  record at offset 73 (`os.pwrite`, or `seek` + `write`); `fsync`; journal deleted.
- [ ] `vault.rewrap(src, dst)`: body copied byte for byte, never decrypted.
- [ ] `RotationResult(outcome, recovered)`.
- [ ] Tests: body identity on three platforms; idempotence; no-op on the current key; untouched
  on `UnknownKek` / `KeyMismatch`; a killed process; a simulated torn write; a corrupt journal;
  P7, P8.

### M6 — CLI

- [ ] Spec and plan(s) in `docs/dev/superpowers/` (git-ignored, ADR-0039), written with superpowers and
  approved before any other task.
- [ ] `keygen` (TTY unless `--force`), `seal`, `unseal`, `inspect`, `rotate` per
  [architecture.md § 12](../architecture.md#12-the-cli).
- [ ] Keys: `--key-env` (default `AEGIS_MASTER_KEY`), `--key-file`, repeatable `--previous-env` /
  `--previous-file`; caller-held `--caller-held --key-out PATH` (exclusive, `0600`) and
  `--key-in PATH`.
- [ ] Context: `--context`, `--context-int`, `--context-hex`, `--context-bool`, `--context-null`.
- [ ] `rotate --recursive [--fail-fast]`: skip caller-held, non-Aegis and external-custody files
  with a report line; continue past errors; summary; first failure's exit code.
- [ ] Tests: one subprocess test per exit code; `inspect` with an unconfigured key; binary
  piping, Windows included; the dogfood AST test over `aegis/cli`.

### M7 — moved to V2

See [v2-django.md](v2-django.md).

### M8 — Documentation and public review

- [ ] Spec and plan(s) in `docs/dev/superpowers/` (git-ignored, ADR-0039), written with superpowers and
  approved before any other task.
- [ ] Root README: threat-model paragraph first, install, the sixty-second example, pitfalls,
  and "reviewed, not audited" in those words.
- [ ] Every document describes what was actually built — `diagrams.md` included.
- [ ] 👤 Final review pass on `stream.py`, `envelope.py` and `file-format.md`; every finding fixed
  or answered in writing; none open that touches the format.
- [ ] `mutmut` over `stream.py`, `envelope.py`, `format.py`, `context.py`: every surviving mutant
  killed or explained.
- [ ] Benchmarks P1, P2, P5, P8, P11, P13 met on `ubuntu-latest` and `macos-latest`; P5
  re-measured on the new key schedule; the GIL release re-verified at the `cryptography` floor.

### M9 — 1.0

- [ ] Spec and plan(s) in `docs/dev/superpowers/` (git-ignored, ADR-0039), written with superpowers and
  approved before any other task.
- [ ] Every gate green on every matrix cell, slow invariants included.
- [ ] The frozen vectors pass against the built wheel and the published one.
- [ ] `CHANGELOG.md` starting at 1.0.0; README says the library is not independently audited.
- [ ] A signed tag triggers `release.yml`; `pip install aegis-voynan` works on a clean machine on
  Python 3.11–3.14.

## 5. Invariants to keep true all the way to 1.0

| Rule | Enforced by |
|---|---|
| No blanket `except Exception` | `ruff` `BLE001` |
| No non-cryptographic randomness | `ruff` `S311` |
| Randomness only in `vault.py`; the environment only in `keys.py` | `ruff` `TID251`; AST purity test |
| No key source ever generates a DEK | the protocol shape (`wrap` / `unwrap`); review |
| The commitment is checked before any chunk | KAT negative vectors; adversarial suite |
| `import aegis` never loads `click` | `ruff` `TID251`; the `sys.modules` test (P12) |
| Downward-only imports, no cycles | AST test |
| Adapters import only the public API | dogfood AST test |
| No secret in any string | secret-hygiene test |
| Constant memory, every streaming path | `tracemalloc` tests (P3, P4) |
| Vectors are read-only | CI change guard; generator never run in CI |
| Per-file coverage | `tools/coverage_gates.py` |
| `stream.py` and `envelope.py` fit on one screen | review; `ruff` `C90` |
| Crypto-path PRs answer the six review questions; M2 and M4 reads by someone other than the author | review; the PR description ([ADR-0038](../decisions.md#adr-0038-one-maintainer-crypto-review-is-written-not-enforced-at-merge)) |
| Third-party actions pinned by SHA | `zizmor` |
| No known-vulnerable dependency in the lock | `pip-audit` nightly and before every release |
| The diagrams never contradict the documents | review — [contributing.md § 6](../contributing.md#6-documentation-is-part-of-the-change) |
| Code is written test-first | [tdd-and-testing.md](../../.claude/rules/tdd-and-testing.md); the failing and passing outputs in every PR |
| Every milestone starts with an approved spec and plan | [milestone-specs-and-plans.md](../../.claude/rules/milestone-specs-and-plans.md); the first task of each milestone |

## 6. Not in 1.0

Everything in [roadmap.md § Post-1.0 backlog](../roadmap.md#post-10-backlog),
[product.md § 4](../product.md#4-what-aegis-deliberately-does-not-do), and the Django adapter
([v2-django.md](v2-django.md)).
