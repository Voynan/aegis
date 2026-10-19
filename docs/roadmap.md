# Roadmap to 1.0

The build order is not arbitrary. It is chosen so that the modules carrying all the
cryptographic risk are written **after** the pure modules they depend on are already
exhaustively tested, and so that the format is frozen before anything depends on it.

Each milestone has a definition of done. A milestone is not finished until its DoD is
demonstrated, not asserted.

Each milestone also starts with an approved spec and one or more approved plans, written with
the superpowers skills ([.claude/rules/milestone-specs-and-plans.md](../.claude/rules/milestone-specs-and-plans.md)),
and its code is written test-first ([.claude/rules/tdd-and-testing.md](../.claude/rules/tdd-and-testing.md)).
The working checklist is [dev/v1-todo.md](dev/v1-todo.md).

---

## Before anything: open questions

All are recorded in [architecture.md § 16](architecture.md#16-open-questions). As of 2026-10-18
every question is decided (ADR-0014 to ADR-0037) or moved to the V2 plan for the Django adapter
([ADR-0034](decisions.md#adr-0034-the-django-adapter-moves-to-v2)).

Two decisions are actions for a person, not code, and both are due before M2:

- **Q18 — reserve the PyPI name.** Configure the pending trusted publisher and publish the
  `0.0.0` placeholder through `release.yml`. A pending publisher alone does not reserve the name.
- **Q19 — request public review of [file-format.md](file-format.md) now**, before any code
  depends on it, in a venue where cryptographers read.

Settled before M4 because they change bytes on disk, and free only until then:

- **Q1, Q3, Q5, Q6** — the chunk AAD covers the immutable core; `context` is required and `{}`
  legal; domain-separated hashes; the name in the format strings stays `aegis`.
- **Q25, Q27–Q32, Q45** — the review of 2026-10-18: library-drawn DEKs, a per-file salt and key
  commitment, a typed custody record, truncation classification and the canonical final chunk,
  exact context types (ADR-0026 to ADR-0030, ADR-0033).

---

## M0 — Repository scaffolding

Packaging, tooling and CI, with no library code.

- `pyproject.toml`: distribution `aegis-voynan`, import package `aegis`, `cryptography` floor,
  the `[cli]` extra, a `dev` dependency group, `requires-python = ">=3.11"`
  ([ADR-0023](decisions.md#adr-0023-python-floor-follows-cpythons-support-window)). Hatchling
  backend ([ADR-0022](decisions.md#adr-0022-hatchling-as-the-build-backend)); no `setup.py`
  ([stack.md § 5](stack.md#5-packaging)).
- `uv.lock` committed; CI on `uv sync --locked`
  ([ADR-0024](decisions.md#adr-0024-uv-for-development-and-ci)).
- Reserve `aegis-voynan` on PyPI: pending trusted publisher, then the `0.0.0` placeholder through
  `release.yml` (Q18, [ADR-0037](decisions.md#adr-0037-smaller-resolutions)).
- `.gitignore` **replaced** with the list in [structure.md § 5](structure.md#5-never-committed),
  `.hypothesis/` included (Q17). The committed file is a Ruby template and ignores none of
  `__pycache__/`, `.venv/`, `*.egg-info/`, `.pytest_cache/`, `.coverage`. Keep the existing
  `docs/dev/diary/` and `docs/dev/notes.md` entries; the plans in `docs/dev/` stay committed.
- The directories of [structure.md § 2](structure.md#2-the-tree) marked M0.
- `ruff` (lint + format), `mypy --strict`, `pytest`, `pytest-cov`, `hypothesis`, `pip-audit`,
  `zizmor` in the `dev` group, versions locked in `uv.lock`; their configuration in
  `pyproject.toml` as in [stack.md § 6.3](stack.md#63-tool-configuration), and
  `tools/coverage_gates.py`.
- CI matrix per [tests.md § 9](tests.md#9-ci): Python 3.11–3.14 × Linux/macOS/Windows.
- `py.typed`, `LICENSE` (present), `README.md` skeleton whose first section after the title
  is the threat-model paragraph.
- `SECURITY.md` at the repository root pointing at [security.md](security.md), so GitHub's
  private advisory flow is enabled from day one.

**DoD:** a green CI run on an empty package on every matrix cell, including the
`lowest-direct` floor job; `uv sync --all-extras` works on all three platforms; the placeholder
release exists on PyPI.

## M1 — The pure core: `errors`, `format`, `context`

No cryptography, no I/O. These are the modules a fuzzer can chew on for free.

- `errors.py`: the full hierarchy of [architecture.md § 9](architecture.md#9-error-model),
  `KeyMismatch` included, with structured attributes and no message-only errors.
- `format.py`: the 73-byte core and the custody record ↔ dataclasses; strict validation in
  the order of [file-format.md § 6.2](file-format.md#62-unsealing) (Q20); offsets,
  `MAX_CUSTODY_LEN` and every label as constants
  ([ADR-0028](decisions.md#adr-0028-a-typed-bounded-custody-record-replaces-the-fixed-80-byte-block)).
- `context.py`: canonical serialization and hashing, exact types
  ([ADR-0033](decisions.md#adr-0033-context-values-must-have-an-exactly-accepted-type)), every
  rejection implemented.

**DoD:** 100 % branch coverage on `format.py`; the offset table asserted against literals;
Hypothesis round-trip on headers in every custody mode; a table-driven test for every context
type and every rejection; `from_bytes` provably raises nothing outside `FormatError` for
arbitrary input up to 73 + 4 096 bytes.

## M2 — `envelope.py` and `stream.py`

The risky modules. Written last among the primitives, first among the crypto.

- `envelope.py`: the per-file key schedule — body key, nonce prefix, commitment — `kek_id`, and
  the local DEK wrap and unwrap
  ([ADR-0027](decisions.md#adr-0027-a-per-file-salt-drives-the-key-schedule-and-the-header-commits-to-the-key)).
- `stream.py`: STREAM segmentation, nonce construction, the final-chunk flag, per-chunk
  primitives with an explicit index and `last` flag (for random access), truncation
  classification ([ADR-0030](decisions.md#adr-0030-how-a-reader-classifies-truncation-and-when-a-final-chunk-may-be-empty)),
  `MAX_CHUNKS` (Q22), and the I/O contract
  ([ADR-0031](decisions.md#adr-0031-the-stream-io-contract-full-segments-full-writes-blocking-streams)).
- Both pure with respect to randomness: the DEK, salt, KEK and AAD arrive as parameters
  ([architecture.md § 4](architecture.md#4-the-purity-boundary-randomness-lives-at-the-edges)).
- Forward-only I/O through iterators; never seeks, never buffers more than one segment.
- **Request public review of `stream.py` and `envelope.py`** when the DoD below is met (Q19).

**DoD:** each module fits on one screen; 100 % branch coverage on both; the property round-trip
passes at every boundary size and under the short-read source; the adversarial suite passes for
this layer; a second person has read both line by line against [file-format.md](file-format.md).

## M3 — `keys.py`, `vault.py`, `readers.py`, `info.py`

The public API is fixed here.

- `keys.py`: `EnvKey`, `FileKey`, `BytesKey` with strict decoding, the entropy floor and
  duplicate detection ([ADR-0029](decisions.md#adr-0029-local-key-sources-envkey-filekey-and-byteskey-with-an-entropy-floor));
  `CallerHeld`; the `KeySource` protocol
  ([ADR-0026](decisions.md#adr-0026-the-library-draws-every-data-key-key-sources-only-wrap-and-unwrap)).
- `vault.py`:
  - `seal`, `unseal`, `seal_bytes`, `unseal_bytes`, `unseal_to_path`, `sealed`, `unsealed`;
  - randomness drawn here and nowhere else, behind the pure seam the vectors use;
  - the context and the call's custody arguments checked before any read (Q23, Q26);
  - `seal_bytes` refused on `CallerHeld()` (Q46);
  - `unseal_to_path` durable on POSIX (Q21).
- `readers.py`: `SealedReader` and `UnsealedReader`, seekable when the source is
  ([ADR-0032](decisions.md#adr-0032-pull-style-readers-vaultsealed-and-vaultunsealed-seekable-when-the-source-is)).
- `info.py`: `inspect()` and `FileInfo`
  ([ADR-0036](decisions.md#adr-0036-inspect-and-the-cli-contract)).
- `Receipt` with `key_id` (Q7); redacted `__repr__` everywhere key material can reach.
- `aegis/__init__.py` exports exactly [architecture.md § 2.2](architecture.md#22-the-public-api).

**DoD:**
- the end-to-end round-trip works in all three custody modes, external custody through a fake
  KMS that imports only the public API;
- the readers pass their equivalence and random-access properties;
- `unseal_to_path` leaves nothing behind on failure and `fsync`s before renaming, tested on
  Windows too;
- the secret-hygiene test passes;
- the constant-memory invariant holds at 512 MB for every streaming path.

## M4 — Freeze the format 🔒

The point of no return ([ADR-0013](decisions.md#adr-0013-freeze-the-format-at-milestone-m4)).

**Gate:** review feedback on [file-format.md](file-format.md) triaged (Q19); no open issue
touching bytes on disk.

- Generate `tests/vectors/v1.json` with `tests/vectors/generate.py`, run by hand: every case of
  [tests.md § 3](tests.md#3-layer-1--frozen-vectors-kat) in all three custody modes, and every
  negative vector.
- **Hand-check the output against [file-format.md](file-format.md), offset by offset, with
  a second pair of eyes.** This is the last moment a byte can move.
- Wire the KAT test in both directions for every case, including the negative vectors.

**DoD:** the vector file is committed with its "FROZEN" note; CI runs it on every matrix
cell; there is no code path anywhere in the repository that rewrites it.

## M5 — `rotate.py`

[ADR-0035](decisions.md#adr-0035-rotation-write-path-torn-write-journal-public-calls-recursive-runs)
decides everything this milestone needs.

- `vault.rotate(path)`: recover the DEK and verify the commitment before writing; one write of
  the custody record at offset 73 (`os.pwrite` where available, `seek` + `write` elsewhere),
  then `fsync` (Q8).
- The journal: written and synced before the record, deleted after; leftover journals recovered
  before any new work (Q9, option 3).
- `vault.rewrap(src, dst)` for object stores: the body copied byte for byte, never decrypted.
- `RotationResult`; no-op when the file is already under the primary key.

**DoD:**
- the body-byte-identity test passes on all three platforms;
- a killed process leaves a readable file;
- a simulated torn write is recovered;
- an unknown `key_id` or a `KeyMismatch` leaves the file untouched;
- P7 holds.

## M6 — CLI

`keygen`, `seal`, `unseal`, `inspect`, `rotate`, with the contract of
[architecture.md § 12](architecture.md#12-the-cli) and
[ADR-0036](decisions.md#adr-0036-inspect-and-the-cli-contract): key options, every context
type, size-derived numbers labelled as such, recursive rotation as specified in Q15.

**DoD:** subprocess integration tests covering every exit code; `inspect` never decrypts
(asserted by giving it a file whose key is not configured); stdin/stdout piping works; the
dogfood test proves the CLI imports only the public API.

## M7 — moved to V2

The Django adapter is not part of 1.0
([ADR-0034](decisions.md#adr-0034-the-django-adapter-moves-to-v2)); it is planned in
[dev/v2-django.md](dev/v2-django.md). The number stays so that references to M8 and M9 remain valid.

## M8 — Documentation and public review

- README with the threat-model paragraph prominent, not in a footnote.
- These documents updated to describe what was actually built.
- **Final public review pass on `stream.py`, `envelope.py` and
  [file-format.md](file-format.md)**, in a venue where cryptographers read (`cryptography`
  mailing lists, `r/crypto`, the `age`/Tink communities). This is a **release blocker**, per
  [security.md § 4.1](security.md#41-the-accepted-risk); the earlier requests of Q19 come first.
- Mutation testing run over `stream.py`, `envelope.py`, `format.py`, `context.py`; every surviving
  mutant either killed or explained.
- The benchmark suite meets every objective in [performance.md](performance.md) on both
  reference runners.

**DoD:** review feedback is triaged and either fixed or answered in writing; no open
finding that touches the format.

## M9 — 1.0

- PyPI trusted publishing (OIDC), signed tags, provenance attestations.
- A CHANGELOG that starts here.
- The README says plainly that the library has **not** been independently audited.

**DoD:** `pip install aegis-voynan` works on a clean machine on every supported Python
(3.11–3.14); the frozen vectors pass against the published wheel.

---

## Post-1.0 backlog

Not commitments — the list of things people will ask for, with our current answer.

| Request | Position |
|---|---|
| **Django adapter** | V2: [dev/v2-django.md](dev/v2-django.md). Additive, so it can ship as a 1.x minor release. |
| **KMS providers** (AWS KMS, Vault, Google Cloud KMS) | As separate packages, built on `KeySource`. External custody means no format change. Possibly `aegis-kms-aws` maintained here, never in the core. |
| **Password-derived keys** (Argon2id) | Today: derive the key yourself and use it as a `BytesKey` KEK ([usage.md § 5.4](usage.md#54-password-derived-keys)). A built-in KDF with stored parameters would be a new suite byte. |
| **Async wrappers** | Only with a demonstrated workload that `asyncio.to_thread` cannot serve ([ADR-0007](decisions.md#adr-0007-no-async-api-in-10)). The ASGI bridge for Django ships with the V2 adapter. |
| **A second suite** (XChaCha20-Poly1305) | For environments without AES-NI. Cheap: a suite byte, a branch in `stream.py`, a new vector file. |
| **Full re-keying** (`aegis rekey`) | Already one line in Python: `new_vault.seal(old_vault.unsealed(src, …), dst, …)`. A CLI command is plausible. |
| **Detached custody** (the record in a database row) | A V2 question ([dev/v2-django.md](dev/v2-django.md), V2-Q1); expressible without a format change. |
| **A `seal` that also returns a plaintext hash** | Refused: business logic of the consumer ([product.md § 4](product.md#4-what-aegis-deliberately-does-not-do)). Callers use `hashlib`. |
| **Compression** | Refused ([ADR-0006](decisions.md#adr-0006-no-compression)). |
| **A browser/WASM implementation** | Only with a committed maintainer. Byte-for-byte sync with the frozen vectors is the hard part, and the vectors make it possible. |
| **SQLAlchemy / FastAPI adapters** | Likely, once the Django adapter has proven the pattern. Same dogfood rule. Until then, [usage.md § 10](usage.md#10-django-and-other-web-frameworks). |
