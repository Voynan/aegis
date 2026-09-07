# Aegis — Design Spec v1

**Date:** 2026-09-07
**Status:** design approved, spec awaiting review
**Type:** open source library, independent project

---

## 1. Context and goal

Aegis is a Python library for encrypting files at rest. It is a **standalone project**,
with no dependency on, coupling to, or knowledge of CryptoVault.

CryptoVaultAPI is **client #1 and the pilot**: the first real consumer, the one that
proves the library in production. The relationship is one-way — Aegis never imports,
references, or accommodates CryptoVault's rules (blockchain, credits, Stripe, that
project's Django models).

The design came out of an audit of CryptoVaultAPI's hand-rolled encryption. Every defect
found there became a requirement here:

| Defect in the hand-rolled implementation | Aegis requirement |
|---|---|
| AES key persisted next to the ciphertext | Envelope encryption; the developer never handles key bytes |
| Whole file loaded into RAM (`.read()`) | Chunked streaming, constant memory |
| Invented format (`nonce + ciphertext`) | Versioned, self-describing format with frozen test vectors |
| Base64 in the database (+33% size) | Binary output; ~0.02% overhead |
| `associated_data=None` | Mandatory AAD binding the blob to its record |
| Key rotation impossible | Rotation by re-wrap, without touching file contents |
| Blanket `except Exception` | Precise, actionable error hierarchy |

**Stated goal:** fast, secure, and — top priority — **easy to use and to understand** for
a developer who is not a cryptographer.

## 2. Ideal customer

A Python backend developer (Django/FastAPI), solo or on a small team, building a product
that stores user files. Knows "AES is the right one", has copied `Fernet` from a blog post,
and is **not a cryptographer**. Does not know what happens when a nonce repeats, and has
never heard of envelope encryption.

The question that actually blocks them is not *which algorithm* — it is **where do I put
the key**. Aegis exists to answer that for them.

**Success criterion:** the developer adopts it in an afternoon, without reading up on
cryptography, and the result is correct by construction.

## 3. Scope

**In 1.0:**

- Core: file format, `seal`/`unseal`, streaming, key sources
- Django adapter (`[django]` extra)
- KEK rotation by re-wrap
- CLI (`[cli]` extra)

**Deliberately out:**

- **Compression** — opens the door to size-leak attacks (the CRIME class); the caller's
  responsibility if they accept the risk.
- **Plaintext hashing for blockchain anchoring** — business logic of the consumer, not of
  the library. Callers use `hashlib`.
- **Third-party KMS providers** (AWS KMS, Vault, HSM) — Aegis defines the extension point
  (two functions); concrete implementations stay out of the core.
- **Legacy format reader** — there is no production user data to preserve.
- **End-to-end encryption with a browser half** — would require a TypeScript/WASM
  implementation kept byte-for-byte in sync. Out of 1.0.
- **Async API** — encryption is CPU-bound; async buys nothing on its own and would double
  the public surface and the test matrix.

## 4. Locked design decisions

| Decision | Choice | Why |
|---|---|---|
| Key custody | **Both modes, through a single seam** | Serves the generic developer (server-held KEK) and the caller-held-key product without forking the library |
| Performance model | **Streaming-first, synchronous** | Removes the memory ceiling without inflating the public surface |
| Cryptographic core | **Our own, on top of `cryptography`, using the STREAM construction** | Invents no cryptography (STREAM is a published construction) while keeping control of the header and AAD, and keeping the code readable — which is the priority requirement |

**Rejected alternatives, and why:**

- **A thin shell over `age`/pyrage:** the best security story (zero original crypto) and
  interoperable with the `age` CLI, but its X25519 identity model distorts the ergonomics
  precisely at key custody — the heart of the library — and rules out a custom AAD. Adds a
  native wheel.
- **Tink `StreamingAEAD`:** audited, with keysets and rotation built in, but it imports
  Tink's conceptual weight (keysets, templates, primitives) against our simplicity
  requirement. The product would become "an easier way to use Tink", which is a different
  product.

**Accepted risk:** the chunk framing is our code. Even though the construction is
well-known, a subtle bug there is our bug. Mitigation: frozen test vectors, a
property-based adversarial suite, and a public review request before 1.0.

## 5. Public API

Mental model: **a vault configured once, used everywhere**. The developer makes one
decision — where the key comes from — and then stops thinking about cryptography.

```python
from aegis import Vault, EnvKey

vault = Vault(key=EnvKey("AEGIS_MASTER_KEY"))
```

Four operations, and nothing else:

```python
# streaming — the main path, constant memory
with open("contract.pdf", "rb") as src, open("contract.aegis", "wb") as dst:
    receipt = vault.seal(src, dst, context={"user_id": 42, "file_id": 7})

with open("contract.aegis", "rb") as src, open("out.pdf", "wb") as dst:
    vault.unseal(src, dst, context={"user_id": 42, "file_id": 7})

# sugar for callers who already hold the bytes
blob = vault.seal_bytes(data, context={...})
data = vault.unseal_bytes(blob, context={...})
```

Plus one safety helper, detailed in section 9:

```python
vault.unseal_to_path(src, "out.pdf", context={...})   # atomic
```

### 5.1 The custody seam

The `key` argument is the only thing that changes between the two modes:

```python
Vault(key=EnvKey("AEGIS_MASTER_KEY"))  # server holds it: DEK wrapped in the header
Vault(key=CallerHeld())                # user holds it: DEK returned, nothing persisted

receipt = vault.seal(src, dst)
receipt.key   # bytes only in CallerHeld mode; None in KEK mode
vault.unseal(src, dst, key=user_key)   # required only in CallerHeld mode
```

### 5.2 API conventions

- **`seal`/`unseal`, not `encrypt`/`decrypt`.** Distinct vocabulary signals a *sealed
  container*, not a raw AES primitive, and reduces the odds of the library being used as a
  general-purpose cipher.
- **`context` is mandatory** and becomes the AAD. It binds the blob to its record: a
  ciphertext belonging to user 42 will not open as user 99 — authentication fails. The
  caller must reproduce the same `context` to open the file; losing it means not opening
  it, and that is the intent.
- **`Receipt` as the return value**, not a tuple: carries `key` (where applicable),
  `size`, `algorithm`, `version`. Extensible without breaking the signature.

### 5.3 Canonical serialization of `context`

`context` is a dictionary with `str` keys and `str`, `bytes`, `int`, `bool`, or `None`
values. **Floats are rejected** with `UsageError` — their representation is not stable
enough to serve as cryptographic input.

Deterministic encoding, length-prefixed with a type tag, keys sorted by their UTF-8 bytes:

```
for each (key, value) in order:
    u32be(len(key)) ‖ key ‖ type_tag(1B) ‖ u32be(len(value)) ‖ value
```

Each type has a fixed encoding, so that `len(value)` is always well defined:

| Type | Tag | Value bytes |
|---|---|---|
| `str` | `0x01` | UTF-8 |
| `bytes` | `0x02` | the bytes themselves |
| `int` | `0x03` | 8 bytes, big-endian, signed |
| `bool` | `0x04` | 1 byte: `0x00` or `0x01` |
| `None` | `0x05` | empty (length 0) |

Length prefixing removes separator ambiguity (`{"a|b": "c"}` and `{"a": "b|c"}` do not
collide) and the type tag separates `1` from `"1"` from `True`.

## 6. File format v1

This is the artifact that **cannot change**. Code gets rewritten; a user's file has to
open years from now.

```
┌─ HEADER — 94 bytes, fixed size, authenticated ─────────────────┐
│  magic          4 B   "AEG\x00"                                │
│  version        1 B   0x01                                     │
│  suite          1 B   0x01 = AES-256-GCM / STREAM / 64 KiB     │
│  flags          1 B   bit0: 0 = wrapped DEK, 1 = caller-held   │
│  kek_id        16 B   KEK fingerprint      (zeros if caller)   │
│  salt          16 B   HKDF salt            (zeros if caller)   │
│  wrapped_dek   48 B   encrypted dek 32 + tag 16 (zeros if …)   │
│  nonce_prefix   7 B   random, STREAM base                      │
└────────────────────────────────────────────────────────────────┘
┌─ CHUNKS ───────────────────────────────────────────────────────┐
│  [65536 B of plaintext, encrypted + 16 B tag] × N              │
│  nonce = nonce_prefix(7) ‖ counter_be32(4) ‖ last_flag(1)      │
│  aad   = sha256(header) ‖ sha256(canonical_context)            │
└────────────────────────────────────────────────────────────────┘
```

**DEK wrapping.** The KEK never encrypts anything directly:

```
kek_id       = sha256(b"aegis-kek-id\x00" ‖ kek)[:16]
wrapping_key = HKDF-SHA256(ikm=kek, salt=salt, info=b"aegis-dek-wrap-v1", len=32)
wrapped_dek  = AESGCM(wrapping_key).encrypt(nonce=12 zero bytes, dek,
                                            aad=header[0:23])
```

The fixed nonce is safe because `wrapping_key` is unique per file (random salt). This
removes any birthday bound on how many files a single KEK has encrypted. The AAD binds the
wrap to the header's first 23 bytes (magic, version, suite, flags, kek_id).

### 6.1 Properties the layout buys

- **Truncation resistance.** The last chunk is marked in its own nonce. Cutting the file
  short does not produce a valid smaller file — it produces an error. Without that marker,
  chunked streaming AEAD is trivially truncatable.
- **Rotation without touching contents.** Fixed-size header: rotating means unwrapping the
  DEK with the old KEK, re-wrapping with the new one, and rewriting 94 bytes at the start
  of the file. A 10 TB bucket rotates in minutes.
- **~0.024% overhead.** 16 bytes per 64 KiB, plus the header. A 100 MB file becomes
  100.02 MB (against 133 MB as base64).
- **Authenticated header.** It enters the AAD of every chunk. Altering `kek_id` or
  `flags`, or pasting one file's header onto another's body, fails authentication — it
  never decrypts garbage.
- **Fixed-size bonus:** a `CallerHeld` file can be converted to KEK custody by rewriting
  only the header, without reprocessing the body.

**Limits:** a 32-bit counter × 64 KiB = **256 TiB** per file.

### 6.2 Accepted consequences

1. **`context` is not stored in the file** — only its hash enters the AAD. Deliberate: the
   blob leaks no `user_id` to whoever obtains the bucket. The price: when the context does
   not match, the library cannot report what it expected. Security beating ergonomics,
   knowingly.
2. **Streaming has a trust boundary.** Output is emitted chunk by chunk, each one
   authenticated, but the file is only proven whole once `unseal()` returns without
   raising. A consumer acting on partial output may act on truncated-but-authentic data.
   This is inherent to any streaming AEAD; it gets documented prominently, and
   `unseal_bytes` does not have the problem.
3. **`kek_id` is the only cleartext metadata.** It reveals that a KEK was used and which
   one, never the content. Trade-off accepted in exchange for cheap rotation.

## 7. Internal components

Rule: **cryptographic risk stays isolated in one small module, and everything that is not
crypto does not know what crypto is.**

| Module | Single responsibility | Depends on | Testable with |
|---|---|---|---|
| `format.py` | Header ↔ dataclass. No crypto, no I/O | nothing | raw bytes, fuzzing |
| `stream.py` | STREAM: chunking, nonces, chunk↔chunk. **All the risk lives here** | `cryptography` | `BytesIO`, vectors |
| `context.py` | Canonical serialization → hash | nothing | case table |
| `keys.py` | The `KeySource` contract + `EnvKey` + `CallerHeld` | `cryptography` | fake env |
| `errors.py` | Exception hierarchy (leaf) | nothing | — |
| `vault.py` | Orchestrates the above; reads like prose | all | integration |
| `rotate.py` | DEK re-wrap; touches the header only | `format`, `keys` | temp file |

Dependencies flow in one direction, with no cycles. `stream.py` must fit on one screen —
if it grows, it has become a junk drawer.

**Dogfood rule:** the Django adapter and the CLI may import only the **public API**. If
either one needs a private import, that is not an implementation detail — it is proof that
the public API is incomplete. Enforced by a test, not by convention.

## 8. Key custody and rotation

```python
class KeySource(Protocol):
    def provision(self) -> tuple[bytes, CustodyBlock]: ...
    def recover(self, block: CustodyBlock, caller_key: bytes | None) -> bytes: ...
```

`CustodyBlock` is simply the header's custody triple — `(kek_id, salt, wrapped_dek)` —
zeroed in `CallerHeld` mode.

Two functions. `EnvKey` wraps the DEK and returns a populated block; `CallerHeld` returns
an empty block and the DEK travels in the `receipt`. **This is the library's extension
story:** anyone who wants AWS KMS, Vault, or an HSM implements two functions.

`kek_id` is not configured by anyone — it is derived from the KEK itself, which eliminates
the entire "I configured the wrong id" class of error. Rotation becomes three steps:

```python
EnvKey(primary="AEGIS_KEY_V2", previous=["AEGIS_KEY_V1"])
# 1. add the new env var   2. run `aegis rotate`   3. remove the old one
```

`EnvKey` validates in its constructor that each KEK is exactly 32 bytes, failing with
`ConfigurationError` at startup — never in the middle of an upload.

## 9. Errors

Principle: **the library diagnoses everything it can before touching the AEAD and, past
that point, is honest about not knowing.**

AEAD cannot distinguish a wrong key from a wrong context from a corrupted file — all three
produce the same `InvalidTag`. Exposing separate `WrongKeyError` and `WrongContextError`
would be lying to the developer and sending them to debug the wrong thing.

```
AegisError
├── ConfigurationError    missing env var, KEK of invalid length
├── FormatError
│   ├── NotAnAegisFile    magic does not match
│   ├── UnsupportedVersion  future version/suite → "upgrade aegis"
│   └── MalformedHeader   truncated or inconsistent header
├── UnknownKek            kek_id matches no configured KEK
│                         "sealed with KEK a3f1…; you have b7c2…"
├── UnsealFailed          "wrong key, wrong context, or corrupted file"
│   └── TruncatedFile     final chunk missing — this one we do detect
└── UsageError            CallerHeld without a key, context with a float, etc.
```

`UnknownKek` carries the most practical value: it answers, before any decryption attempt,
that the problem is a missing KEK rather than a broken file. `TruncatedFile` is genuinely
distinguishable because the last-chunk marker is ours.

**Two footguns the library closes on its own:**

1. **`__repr__` redacts key material.** In `CallerHeld` mode the `receipt` carries the
   key, and every developer logs objects. The `repr` of `Receipt`, `Vault`, and
   `KeySource` shows `key=<redacted 32 bytes>`. No exception message ever contains a key,
   a DEK, or plaintext. This defends against the most common production leak, which is not
   cryptographic — it is logging.
2. **`unseal_to_path()` with an atomic rename.** In streaming mode, if authentication
   fails at the last chunk, partial plaintext has already been written to the destination.
   The low-level API cannot clean up the caller's file, so we offer the safe path as the
   convenient one: write to a temporary file, `fsync`, and rename only if `unseal` returns
   cleanly. On failure, nothing survives.

**Rule:** no blanket `except Exception` in the library. Logging through
`logging.getLogger("aegis")` with a `NullHandler`; the library never configures the host's
logging and never logs a secret.

## 10. Testing strategy

In a cryptography library the suite is not there to catch regressions — it **is** the
argument that the code deserves trust.

**1. Frozen vectors (KAT).** A versioned JSON file in the repo: fixed KEK, DEK,
`nonce_prefix`, context, and plaintext → the exact expected ciphertext, byte for byte.
Generated once and never regenerated. Regenerating that file is, by definition, a format
change — therefore a new `version`. It guards the compatibility promise and is the first
test to write.

**2. Property-based round-trip (Hypothesis).** `seal → unseal == original` for arbitrary
plaintext, with chunk boundaries forced explicitly: 0 bytes, 1 byte, exactly 64 KiB,
64 KiB ± 1, exact multiples. Framing bugs live at those boundaries.

**3. Adversarial suite.** One property, applied to arbitrary mutations of a sealed file:

> **No mutation of the blob ever yields plaintext. It either raises, or produces nothing.**

Instantiated cases: bit flips at any offset (header, chunk, tag), truncation at any
position, reordered or duplicated chunks, headers swapped between files, a different
context, a different KEK. Each one is a real attack, and each one has a line of the design
that blocks it.

**4. Constant memory as a tested invariant.** Seal a large synthetic source (~512 MB
generated as a stream, never touching disk) while measuring the peak with `tracemalloc`
against a fixed ceiling. This turns "fast" in the README from marketing into a verifiable
fact.

**5. Rotation and dogfood.** Rotate, then verify the **file body is byte-identical** —
direct proof that rotation touched only the header. Plus a structural test that fails if
the CLI or the Django adapter import any private module.

**Coverage:** 100% on `stream.py` and `format.py`, non-negotiable. Normal elsewhere.
**CI:** Python 3.10+.

**Benchmarks** live in a separate suite as a guard against throughput regressions — not as
a PR gate.

## 11. Packaging

```
pip install aegis            # core, single dependency: cryptography
pip install aegis[django]    # adapter
pip install aegis[cli]       # CLI
```

The core depends on no framework.

**CLI:**

| Command | Purpose |
|---|---|
| `aegis seal` | Seal a file |
| `aegis unseal` | Open a file |
| `aegis inspect` | Show the header (version, suite, custody, `kek_id`) **without decrypting** |
| `aegis rotate` | Re-wrap the DEK to the primary KEK |

`inspect` serves the "understanding" goal: the developer sees the file's structure before
writing any code.

**Django adapter:**

```python
class Document(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    file = SealedFileField(upload_to="docs/",
                           context=lambda inst: {"user_id": inst.owner_id})
```

The adapter supports **KEK custody only** — `CallerHeld` makes no sense in a field the
server must be able to read. Configuring it that way fails with `UsageError` during
Django's system checks, not at runtime.

## 12. Documentation

The README needs an **honest threat model** section, prominently placed:

> Aegis protects against a database dump and a storage bucket leak. It does **not**
> protect against a server compromised at runtime — in that scenario the KEK is in process
> memory. For that threat you need client-side end-to-end encryption, which Aegis does not
> do.

A developer who is not a cryptographer needs someone stating this plainly. That section is
what separates this library from one more AES wrapper on PyPI.

## 13. Open decisions

Two, both resolvable before the first release, neither blocking implementation:

1. **Name and PyPI availability.** "Aegis" needs to be checked on PyPI; if taken, pick a
   variant. The name appears in the package, in the CLI, **and in the HKDF `info`
   strings** — changing it after 1.0 is expensive, changing it before is trivial.
2. **License.** Recommendation: Apache-2.0, for its explicit patent grant, standard for
   cryptography libraries. MIT is the alternative if simplicity is preferred.

## 14. Next step

Review of this document. Once approved, the next step is the implementation plan.
