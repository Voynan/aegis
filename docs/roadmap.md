# Roadmap to 1.0

The build order is not arbitrary. It is chosen so that the module carrying all the
cryptographic risk is written **after** the pure modules it depends on are already
exhaustively tested, and so that the format is frozen before anything depends on it.

Each milestone has a definition of done. A milestone is not finished until its DoD is
demonstrated, not asserted.

---

## Before anything: settle two questions

Both are recorded in [architecture.md § 16](architecture.md#16-open-questions).

- **Q1 — the chunk AAD / rotation contradiction.** Resolved in
  [ADR-0014](decisions.md#adr-0014-chunk-aad-covers-the-immutable-header-core-only); needs
  a yes. Blocks M2.
- **Q2 — how a KEK is encoded in an environment variable.** Proposed in
  [ADR-0015](decisions.md#adr-0015-keks-in-environment-variables-are-base64). Blocks M3.

Also worth deciding early, because they are free now and expensive after M4: **Q5** (domain
separation in the AAD hashes) and **Q6** (the name, which appears in the HKDF `info`
strings).

---

## M0 — Repository scaffolding

Packaging, tooling and CI, with no library code.

- `pyproject.toml`: `aegis` package, `cryptography` floor, extras `[django]`, `[cli]`,
  `[dev]`. Hatchling or PDM backend; no `setup.py`.
- `.gitignore` **replaced** — the committed one is a Ruby template and ignores none of
  `__pycache__/`, `.venv/`, `*.egg-info/`, `.pytest_cache/`, `.hypothesis/`, `.coverage`.
- `ruff` (lint + format), `mypy --strict`, `pytest`, `pytest-cov`, `hypothesis` pinned in
  `[dev]`.
- CI matrix per [tests.md § 9](tests.md#9-ci): Python 3.10–3.13 × Linux/macOS/Windows.
- `py.typed`, `LICENSE` (present), `README.md` skeleton whose first section after the title
  is the threat-model paragraph.
- `SECURITY.md` at the repository root pointing at [security.md](security.md), so GitHub's
  private advisory flow is enabled from day one.

**DoD:** a green CI run on an empty package on every matrix cell; `pip install -e ".[dev]"`
works on all three platforms.

## M1 — The pure core: `errors`, `format`, `context`

No cryptography, no I/O. These are the modules a fuzzer can chew on for free.

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

- STREAM segmentation, nonce construction, final-chunk marker, AAD composition.
- Pure with respect to randomness: DEK, `nonce_prefix` and AAD arrive as parameters
  ([architecture.md § 4](architecture.md#4-the-purity-boundary-randomness-lives-at-the-edges)).
- Forward-only I/O through iterators; never seeks, never buffers more than one segment.

**DoD:** fits on one screen; 100 % branch coverage; the property round-trip passes with all
the boundary sizes; the adversarial suite passes; a second person has read it line by line
against [file-format.md](file-format.md).

## M3 — `keys.py` and `vault.py`

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

- Generate `tests/vectors/v1.json` with `tests/vectors/generate.py`, run by hand.
- **Hand-check the output against [file-format.md](file-format.md), offset by offset, with
  a second pair of eyes.** This is the last moment a byte can move.
- Wire the KAT test in both directions for every case, including the negative vectors.

**DoD:** the vector file is committed with its "FROZEN" note; CI runs it on every matrix
cell; there is no code path anywhere in the repository that rewrites it.

## M5 — `rotate.py`

- Unwrap with the matching KEK, re-wrap under the primary, write 80 bytes at offset 7.
- A single `pwrite`, so an interruption leaves a file that still opens with the old KEK.
- No-op when the file is already under the primary KEK.

**DoD:** the body-byte-identity test passes; interruption leaves a readable file; an unknown
`kek_id` raises `UnknownKek` and leaves the file untouched.

## M6 — CLI

`keygen`, `seal`, `unseal`, `inspect`, `rotate`, with the exit-code contract from
[architecture.md § 12](architecture.md#12-the-cli).

**DoD:** subprocess integration tests covering every exit code; `inspect` never decrypts
(asserted by giving it a file whose KEK is not configured); stdin/stdout piping works; the
dogfood test proves the CLI imports only the public API.

## M7 — Django adapter

`SealedFileField`, the storage wrapper, and system checks that reject `CallerHeld` and
catch the common context mistakes.

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
  [security.md § 4.1](security.md#41-the-accepted-risk).
- Mutation testing run over `stream.py`, `format.py`, `context.py`; every surviving mutant
  either killed or explained.

**DoD:** review feedback is triaged and either fixed or answered in writing; no open
finding that touches the format.

## M9 — 1.0

- PyPI trusted publishing (OIDC), signed tags, provenance attestations.
- A CHANGELOG that starts here.
- The README says plainly that the library has **not** been independently audited.

**DoD:** `pip install aegis` works on a clean machine on all supported Pythons; the frozen
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
