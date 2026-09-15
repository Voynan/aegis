# Roadmap to 1.0

The build order is not arbitrary. It is chosen so that the module carrying all the
cryptographic risk is written **after** the pure modules it depends on are already
exhaustively tested, and so that the format is frozen before anything depends on it.

Each milestone has a definition of done. A milestone is not finished until its DoD is
demonstrated, not asserted.

---

## Before anything: open questions

All are recorded, with deadlines, in [architecture.md § 16](architecture.md#16-open-questions).

- **Q1 — the chunk AAD / rotation contradiction.** Resolved:
  [ADR-0014](decisions.md#adr-0014-chunk-aad-covers-the-immutable-header-core-only) accepted.
- **Q2 — how a KEK is encoded in an environment variable.** Resolved: strict base64,
  [ADR-0015](decisions.md#adr-0015-keks-in-environment-variables-are-base64) accepted.
- **Q8 — rotation on Windows** and **Q9 — torn writes during rotation.** Open. Both block M5.
  Q9 must be decided before M4 if the format-level option (a redundant custody block) is
  considered.
- **Q10–Q26 — gaps found while turning this roadmap into a task list.** Open. Each milestone
  below lists the ones it depends on.

Also settled before M4, because they were free then and expensive after:

- **Q3** — `context` is required, `{}` is legal
  ([ADR-0020](decisions.md#adr-0020-context-is-required-but-may-be-empty)).
- **Q5** — domain-separated AAD hashes
  ([ADR-0019](decisions.md#adr-0019-domain-separated-aad-hashes)).
- **Q6** — distribution `aegis-voynan`, import `aegis`
  ([ADR-0018](decisions.md#adr-0018-distribute-as-aegis-voynan-import-as-aegis)).

---

## M0 — Repository scaffolding

Packaging, tooling and CI, with no library code.

**Open questions:** [Q17 and Q18](architecture.md#16-open-questions) — both change tasks below.

- `pyproject.toml`: distribution `aegis-voynan`, import package `aegis`, `cryptography`
  floor, extras `[django]` and `[cli]`, a `dev` dependency group. Hatchling backend; no
  `setup.py` ([stack.md § 5](stack.md#5-packaging)).
- `uv.lock` committed; CI on `uv sync --locked`
  ([ADR-0024](decisions.md#adr-0024-uv-for-development-and-ci)).
- Reserve `aegis-voynan` on PyPI. A pending trusted publisher alone does **not** reserve the
  name; only a published release does ([Q18](architecture.md#16-open-questions)).
- `.gitignore` **replaced** — the committed one is a Ruby template and ignores none of
  `__pycache__/`, `.venv/`, `*.egg-info/`, `.pytest_cache/`, `.hypothesis/`, `.coverage`.
  Whether `.hypothesis/` is ignored is [Q17](architecture.md#16-open-questions). Keep the
  existing `docs/dev/` entry.
- `ruff` (lint + format), `mypy --strict`, `pytest`, `pytest-cov`, `hypothesis` in the `dev`
  group, versions locked in `uv.lock`.
- CI matrix per [tests.md § 9](tests.md#9-ci): Python 3.10–3.13 × Linux/macOS/Windows.
- `py.typed`, `LICENSE` (present), `README.md` skeleton whose first section after the title
  is the threat-model paragraph.
- `SECURITY.md` at the repository root pointing at [security.md](security.md), so GitHub's
  private advisory flow is enabled from day one.

**DoD:** a green CI run on an empty package on every matrix cell, including the
`lowest-direct` floor job; `uv sync --all-extras` works on all three platforms.

## M1 — The pure core: `errors`, `format`, `context`

No cryptography, no I/O. These are the modules a fuzzer can chew on for free.

**Open questions:** [Q20](architecture.md#16-open-questions).

- `errors.py`: the full hierarchy, with structured attributes and no message-only errors.
- `format.py`: `Header` dataclass ↔ 94 bytes, with strict validation
  ([ADR-0017](decisions.md#adr-0017-strict-header-validation-reserved-bits-and-custody-zeros)).
- `context.py`: canonical serialization and hashing, with every rejection implemented.

**DoD:** 100 % branch coverage on `format.py`; the offset table asserted against literals;
Hypothesis round-trip on headers; a table-driven test for every context type and every
rejection; `from_bytes` provably raises nothing outside `FormatError` for arbitrary 94-byte
input.

## M2 — `stream.py`

The risky module. Written last among the primitives, first among the crypto.

**Open questions:** [Q19 and Q22](architecture.md#16-open-questions).

- STREAM segmentation, nonce construction, final-chunk marker, AAD composition.
- Pure with respect to randomness: DEK, `nonce_prefix` and AAD arrive as parameters
  ([architecture.md § 4](architecture.md#4-the-purity-boundary-randomness-lives-at-the-edges)).
- Forward-only I/O through iterators; never seeks, never buffers more than one segment.

**DoD:** fits on one screen; 100 % branch coverage; the property round-trip passes with all
the boundary sizes; the adversarial suite passes; a second person has read it line by line
against [file-format.md](file-format.md).

## M3 — `keys.py` and `vault.py`

**Open questions:** [Q10, Q12, Q21, Q23 and Q26](architecture.md#16-open-questions).

- `KeySource` protocol, `CustodyBlock`, `EnvKey` (with `primary` / `previous`),
  `CallerHeld`.
- Constructor-time validation with `ConfigurationError`.
- `Vault` with `seal`, `unseal`, `seal_bytes`, `unseal_bytes`, `unseal_to_path`.
- `Receipt`, and redacted `__repr__` everywhere key material can reach.

**DoD:** the end-to-end round-trip works in both custody modes; `unseal_to_path` leaves
nothing behind on failure and `fsync`s before renaming (tested on Windows too); the
secret-hygiene test passes; the constant-memory invariant holds at 512 MB for both `seal`
and `unseal`.

## M4 — Freeze the format 🔒

The point of no return ([ADR-0013](decisions.md#adr-0013-freeze-the-format-at-milestone-m4)).

**Open questions:** [Q9 (if its format option is considered), Q19, Q20 and
Q25](architecture.md#16-open-questions) — all closed before the vectors are generated.

- Generate `tests/vectors/v1.json` with `tests/vectors/generate.py`, run by hand.
- **Hand-check the output against [file-format.md](file-format.md), offset by offset, with
  a second pair of eyes.** This is the last moment a byte can move.
- Wire the KAT test in both directions for every case, including the negative vectors.

**DoD:** the vector file is committed with its "FROZEN" note; CI runs it on every matrix
cell; there is no code path anywhere in the repository that rewrites it.

## M5 — `rotate.py`

**Blocked by** [Q8 and Q9](architecture.md#16-open-questions): the write primitive on Windows,
and what happens when power is lost mid-write. Also open: [Q11 and
Q15](architecture.md#16-open-questions), the public rotation call and recursive rotation over
mixed directories.

- Unwrap with the matching KEK, re-wrap under the primary, write 80 bytes at offset 7.
- One write of the 80 bytes (`os.pwrite` where available, `seek` + `write` elsewhere), then
  `fsync`. Crash safety beyond process death depends on Q9.
- No-op when the file is already under the primary KEK.

**DoD:** the body-byte-identity test passes on all three platforms; a killed process leaves a
readable file; the torn-write guarantee chosen in Q9 is tested (for example by simulating a
half-written custody block); an unknown `kek_id` raises `UnknownKek` and leaves the file
untouched.

## M6 — CLI

`keygen`, `seal`, `unseal`, `inspect`, `rotate`, with the exit-code contract from
[architecture.md § 12](architecture.md#12-the-cli).

**Open questions:** [Q10, Q13, Q14, Q15 and Q24](architecture.md#16-open-questions).

**DoD:** subprocess integration tests covering every exit code; `inspect` never decrypts
(asserted by giving it a file whose KEK is not configured); stdin/stdout piping works; the
dogfood test proves the CLI imports only the public API.

## M7 — Django adapter

`SealedFileField`, the storage wrapper, and system checks that reject `CallerHeld` and
catch the common context mistakes.

**Open questions:** [Q4 and Q16](architecture.md#16-open-questions).

**DoD:** integration tests on Django LTS and latest; upload streams without buffering the
file in memory; `manage.py check` fails on a caller-held configuration; the dogfood test
passes for `aegis.contrib.django`.

## M8 — Documentation and public review

- README with the threat-model paragraph prominent, not in a footnote.
- These documents updated to describe what was actually built — every "proposed" ADR either
  accepted or superseded.
- **Public review request on `stream.py` and [file-format.md](file-format.md)**, in a
  venue where cryptographers read (`cryptography` mailing lists, `r/crypto`, the
  `age`/Tink communities). This is a **release blocker**, per
  [security.md § 4.1](security.md#41-the-accepted-risk). Requesting it only here, after the M4
  freeze, is [Q19](architecture.md#16-open-questions).
- Mutation testing run over `stream.py`, `format.py`, `context.py`; every surviving mutant
  either killed or explained.
- The benchmark suite meets every objective in [performance.md](performance.md) on both
  reference runners.

**DoD:** review feedback is triaged and either fixed or answered in writing; no open
finding that touches the format.

## M9 — 1.0

**Open questions:** [Q7](architecture.md#16-open-questions).

- PyPI trusted publishing (OIDC), signed tags, provenance attestations.
- A CHANGELOG that starts here.
- The README says plainly that the library has **not** been independently audited.

**DoD:** `pip install aegis-voynan` works on a clean machine on all supported Pythons; the frozen
vectors pass against the published wheel.

---

## Post-1.0 backlog

Not commitments — the list of things people will ask for, with our current answer.

| Request | Position |
|---|---|
| **KMS providers** (AWS KMS, Vault, GCP KMS) | As separate packages, built on `KeySource`. Possibly `aegis-kms-aws` maintained here, never in the core. |
| **Password-derived keys** (Argon2id) | Plausible. Needs its own parameter-tuning discussion and a KDF-parameters field, so it is at least a new suite byte. |
| **Async wrappers** | Only with a demonstrated workload that `asyncio.to_thread` cannot serve ([ADR-0007](decisions.md#adr-0007-no-async-api-in-10)). |
| **A second suite** (XChaCha20-Poly1305) | For environments without AES-NI. Cheap: a suite byte, a branch in `stream.py`, a new vector file. |
| **Full re-keying** (`aegis rekey`) | Unseal + re-seal with a new DEK. Distinct from rotation; useful after a DEK compromise. |
| **A `seal` that also returns a plaintext hash** | Refused: business logic of the consumer ([product.md § 4](product.md#4-what-aegis-deliberately-does-not-do)). Callers use `hashlib`. |
| **Compression** | Refused ([ADR-0006](decisions.md#adr-0006-no-compression)). |
| **A browser/WASM implementation** | Only with a committed maintainer. Byte-for-byte sync with the frozen vectors is the hard part, and the vectors make it possible. |
| **SQLAlchemy / FastAPI adapters** | Likely, once the Django adapter has proven the pattern. Same dogfood rule. |
