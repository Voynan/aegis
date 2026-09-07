# Architecture

How the code is organised, and why. The byte-level format lives in
[file-format.md](file-format.md); this document is about the shape of the Python.

---

## 1. The one rule

> **Cryptographic risk stays isolated in one small module, and everything that is not
> crypto does not know what crypto is.**

Every other rule here is a consequence of that one. `stream.py` is the module where a
subtle mistake is a vulnerability rather than a bug; it must therefore be small enough to
read in one sitting, pure enough to test exhaustively, and boring enough that a reviewer
who is a cryptographer can audit it in an hour.

If `stream.py` grows past roughly one screen, it has become a junk drawer and something
must move out.

## 2. Module map

| Module | Single responsibility | Depends on | Tested with |
|---|---|---|---|
| `errors.py` | The exception hierarchy | — (leaf) | — |
| `format.py` | Header ↔ dataclass. No crypto, no I/O | `errors` | raw bytes, fuzzing |
| `context.py` | Canonical serialization → SHA-256 | `errors` | a table of cases |
| `stream.py` | STREAM: chunking, nonces, chunk↔chunk. **All the risk lives here** | `cryptography`, `errors` | `BytesIO`, frozen vectors |
| `keys.py` | The `KeySource` contract, `EnvKey`, `CallerHeld` | `cryptography`, `format`, `errors` | a fake environment |
| `vault.py` | Orchestrates the above. Reads like prose | all of the above | integration |
| `rotate.py` | DEK re-wrap. Touches the custody block only | `format`, `keys`, `errors` | temp files |

```
        aegis.django          aegis.cli          ← adapters: public API only
                  \             /
                 aegis/__init__.py                ← the public surface
                  /             \
            vault.py          rotate.py           ← orchestration
           /   |    \          /     \
    stream  keys  context  format     |           ← single-responsibility units
          \    |      |     /         |
                errors.py                         ← leaf, imports nothing
          ( stream, keys → cryptography )
```

Dependencies flow downward only. There are no cycles, and the absence of cycles is
enforced by a test, not by good intentions
([tests.md § 6](tests.md#6-layer-5--rotation-and-dogfood)).

### 2.1 Package layout

```
aegis/
├── __init__.py        # the public API: Vault, EnvKey, CallerHeld, Receipt, errors
├── errors.py
├── format.py
├── context.py
├── stream.py
├── keys.py
├── vault.py
├── rotate.py
├── py.typed
├── cli/               # extra: [cli]
│   ├── __init__.py
│   └── __main__.py
└── contrib/
    └── django/        # extra: [django]
        ├── __init__.py
        ├── fields.py  # SealedFileField
        ├── storage.py
        └── checks.py  # Django system checks
tests/
├── vectors/v1.json    # frozen, never regenerated
├── unit/
├── property/
├── adversarial/
└── integration/
docs/
benchmarks/            # separate suite, not a PR gate
```

`aegis.contrib.django` rather than `aegis.django`, so that `import aegis.django` can never
shadow or be confused with the `django` package, and so that "contrib" reads as what it
is — an adapter, not the core.

## 3. Layering rules

1. **Downward dependencies only.** A module may import modules below it in the table above.
   Never sideways into a peer's internals, never upward.
2. **The core imports no framework.** `aegis` (excluding `contrib/` and `cli/`) depends on
   exactly one third-party package: `cryptography`.
3. **Dogfood rule.** `aegis.contrib.django` and `aegis.cli` may import **only the public
   API**. If either needs a private import, that is not an implementation detail — it is
   proof that the public API is incomplete. Enforced by an AST test that walks the adapter
   packages and fails on any `aegis.<private>` import.
4. **No blanket `except Exception`** anywhere in the library. Catch the exception you can
   describe; let the rest propagate.

## 4. The purity boundary: randomness lives at the edges

This is the architectural consequence of demanding frozen test vectors, and it is easy to
get wrong by writing the obvious code first.

- `format.py` and `context.py` are **pure**: bytes in, bytes out. No I/O, no clock, no RNG.
- `stream.py` is **pure given its inputs**. It receives the DEK, the `nonce_prefix` and the
  AAD as parameters. It never calls `os.urandom` and never opens a file — it consumes and
  produces byte segments through iterators.
- `keys.py` and `vault.py` are where randomness and the environment enter: `os.urandom` for
  the DEK, the salt and the `nonce_prefix`; `os.environ` for `EnvKey`.

Because of this split, a known-answer test can pin every byte of the output without
monkey-patching the random module, and the module carrying all the risk can be tested as a
pure function. If a test ever needs to patch `os.urandom` to reach `stream.py`, the
boundary has been violated.

**Encryption never seeks.** Both `seal` and `unseal` treat their streams as forward-only,
so a pipe, a socket, an `HttpResponse` or a `BytesIO` all work identically. `seal` reads
one segment ahead in order to know which segment is the last
([file-format.md § 6.1](file-format.md#61-sealing)); it never rewinds to patch what it
already wrote. Only `rotate` seeks, and only on a real file.

## 5. Control flow

### 5.1 `seal`

```
Vault.seal(src, dst, context)
  │
  ├─ context.canonicalize(context) ──────────────▶ context_hash        [pure]
  ├─ key_source.provision() ─────────────────────▶ (dek, CustodyBlock) [random]
  ├─ os.urandom(7) ──────────────────────────────▶ nonce_prefix        [random]
  ├─ format.Header(...).to_bytes() ──────────────▶ 94 bytes            [pure]
  ├─ dst.write(header)
  ├─ stream.encrypt(dek, nonce_prefix, aad, src, dst)                  [pure-ish: I/O by iterator]
  └─ Receipt(key=…, size=…, algorithm=…, version=…)
```

### 5.2 `unseal`

```
Vault.unseal(src, dst, context, key=None)
  │
  ├─ format.Header.from_bytes(src.read(94)) ─────▶ validated header    [pure]
  │     └─ raises NotAnAegisFile / UnsupportedVersion / MalformedHeader
  ├─ key_source.recover(header.custody, key) ────▶ dek
  │     └─ raises UnknownKek before any decryption attempt
  ├─ context.canonicalize(context) ──────────────▶ context_hash        [pure]
  └─ stream.decrypt(dek, header.nonce_prefix, aad, src, dst)
        └─ raises UnsealFailed / TruncatedFile
```

`vault.py` contains no cryptographic decision. It reads as a sequence of named steps — if a
reviewer cannot follow it aloud, it is wrong.

## 6. The custody seam

One protocol, two functions, and the entire "where do I put the key" question routes
through it:

```python
class KeySource(Protocol):
    def provision(self) -> tuple[bytes, CustodyBlock]: ...
    def recover(self, block: CustodyBlock, caller_key: bytes | None) -> bytes: ...


@dataclass(frozen=True)
class CustodyBlock:
    kek_id: bytes        # 16 B
    salt: bytes          # 16 B
    wrapped_dek: bytes   # 48 B
```

`CustodyBlock` is exactly the header's mutable region
([file-format.md § 2.3](file-format.md#23-the-custody-triple)) — all zeros in caller-held
mode.

| Implementation | `provision` | `recover` |
|---|---|---|
| `EnvKey` | random DEK, wrapped under the primary KEK | selects the KEK by `kek_id`, unwraps |
| `CallerHeld` | random DEK, empty block; DEK travels in the `Receipt` | returns `caller_key`; raises `UsageError` if it is missing or not 32 bytes |

**This is the whole extension story.** AWS KMS, Vault, an HSM, a per-tenant key server:
each is two functions and zero changes to the core. That is why bundled providers are out
of scope — they would be dependencies, not capabilities.

`EnvKey` validates in its constructor that every configured KEK decodes to exactly 32
bytes, failing with `ConfigurationError` at import/startup — never in the middle of an
upload. Rotation is then three steps:

```python
EnvKey(primary="AEGIS_KEY_V2", previous=["AEGIS_KEY_V1"])
# 1. add the new env var   2. run `aegis rotate`   3. remove the old one
```

## 7. Memory and performance model

**Peak memory is O(chunk size), not O(file size)** — one 64 KiB plaintext segment, one
65552-byte ciphertext segment, the 94-byte header, and Python's own overhead. Nothing
accumulates. A 512 MB seal must stay under a fixed ceiling measured by `tracemalloc`, and
that ceiling is a test, not a README claim
([tests.md § 5](tests.md#5-layer-4--constant-memory-as-a-tested-invariant)).

Two rules that keep it true:

- Never `src.read()` without a size argument. Never build a `list` of chunks. Never
  `b"".join` the body.
- `seal_bytes` / `unseal_bytes` are the deliberate exceptions: the caller already holds the
  whole plaintext, so they are implemented over `BytesIO` and documented as O(n).

Throughput is bounded by AES-GCM, which is hardware-accelerated on any CPU with AES-NI, and
by chunk overhead, which at 64 KiB is negligible. Real numbers come from the benchmark
suite, not from this document.

## 8. Concurrency

- A `Vault` is **immutable after construction** and holds no per-operation state.
  `EnvKey` reads the environment once, in `__init__`. Sharing one `Vault` across threads is
  therefore safe, provided the `KeySource` is (both bundled ones are).
- A single `seal`/`unseal` call is **not** re-entrant across threads: the streams belong to
  the caller and are consumed sequentially. One call, one thread.
- Encryption is CPU-bound. To use more cores, run whole `seal` calls in a
  `ThreadPoolExecutor` or `ProcessPoolExecutor`. There is no async API and no internal
  threading ([ADR-0007](decisions.md#adr-0007-no-async-api-in-10)).

## 9. Error model

```
AegisError
├── ConfigurationError    missing env var, KEK of invalid length or encoding
├── FormatError
│   ├── NotAnAegisFile      magic does not match
│   ├── UnsupportedVersion  future version/suite → "upgrade aegis"
│   └── MalformedHeader     truncated or internally inconsistent header
├── UnknownKek            kek_id matches no configured KEK
│                         "sealed with KEK a3f1…; you have b7c2…"
├── UnsealFailed          "wrong key, wrong context, or corrupted file"
│   └── TruncatedFile       final chunk missing — this one we do detect
└── UsageError            CallerHeld without a key, a float in context, …
```

The principle: **diagnose everything possible before touching the AEAD, and past that point
be honest about not knowing.**

AES-GCM cannot distinguish a wrong key from a wrong context from a corrupted byte — all
three raise the same `InvalidTag`. Exposing `WrongKeyError` and `WrongContextError`
separately would be inventing information and would send the developer to debug the wrong
thing. So `UnsealFailed` says all three possibilities out loud, and the two failures that
*are* genuinely distinguishable get their own classes:

- `UnknownKek` — decided by comparing `kek_id` against the configured KEKs, before any
  decryption. It answers "you are missing a key", not "your file is broken", which is the
  single most valuable disambiguation in operations.
- `TruncatedFile` — decided by our own final-chunk marker.

Every error class carries structured attributes (e.g. `UnknownKek.file_kek_id`,
`UnknownKek.available_kek_ids`), never only a formatted string, so callers can branch
without parsing messages.

`ConfigurationError` and `UsageError` should be impossible to reach in a correct
integration; both indicate a bug in the calling code and both are raised as early as the
information allows.

## 10. Secret hygiene

Two footguns the library closes on its own, because they are the ones that actually cause
production leaks:

1. **`__repr__` redacts key material.** `Receipt`, `Vault`, `KeySource` implementations and
   `CustodyBlock` render key bytes as `key=<redacted 32 bytes>`. Every developer logs
   objects; in caller-held mode the `Receipt` carries the only copy of the user's key. No
   exception message, no log record and no `str()` ever contains a key, a DEK or plaintext.
   Enforced by a test that asserts secrets never appear in `repr()` or in any raised
   message.
2. **`unseal_to_path()` writes atomically.** In streaming mode, if authentication fails at
   the last chunk, partial plaintext has already been written to the destination — and the
   low-level API cannot clean up a stream the caller owns. So the safe path is offered as
   the convenient one: write to a temporary file in the destination's directory, `fsync`,
   and `os.replace` only if `unseal` returns cleanly. On failure the temporary file is
   removed and nothing survives.

Also:

- **Logging** goes through `logging.getLogger("aegis")` with a `NullHandler`. The library
  never configures the host's logging and never logs a secret. `DEBUG` records may contain
  sizes, versions, `kek_id` and chunk counts — nothing else.
- **We do not claim to zeroize memory.** Python `bytes` are immutable and the interpreter
  copies freely; "wiping" a key with `ctypes` would be theatre. Where it is cheap we keep
  key material in `bytearray` and clear it after use, but the documentation says plainly
  that a memory-dump adversary is out of scope
  ([security.md § 3](security.md#3-what-aegis-does-not-defend-against)).

## 11. Typing

The package ships `py.typed`. The public API is fully annotated, `mypy --strict` clean on
`aegis/` (excluding tests), and `Protocol` is used for `KeySource` so that third-party
implementations need no import from us at runtime.

`bytes` versus `str` is never ambiguous in a signature: keys, DEKs, blobs and canonical
encodings are `bytes`; env var names and paths are `str`.

## 12. The CLI

`aegis` exists so that a developer can *see* the structure before writing code — the
"understanding" half of the product goal.

| Command | Purpose |
|---|---|
| `aegis keygen` | Print a fresh 32-byte KEK, base64-encoded (**proposed addition**, [Q2](#16-open-questions)) |
| `aegis seal` | Seal a file |
| `aegis unseal` | Open a file |
| `aegis inspect` | Show the header — version, suite, custody, `kek_id`, chunk count, plaintext size — **without decrypting** |
| `aegis rotate` | Re-wrap the DEK to the primary KEK |

Exit codes are part of the contract, so the CLI is usable in a shell script:

| Code | Meaning |
|---:|---|
| 0 | success |
| 1 | `UnsealFailed` (including `TruncatedFile`) |
| 2 | `UsageError` — bad invocation |
| 3 | `FormatError` — not an Aegis file, unsupported version, malformed header |
| 4 | `UnknownKek` |
| 5 | `ConfigurationError` |

The CLI reads and writes standard streams by default, so `aegis seal < in > out` works and
never materialises a file. It never prints key material except from `keygen`, which prints
only to a TTY unless `--force` is given.

## 13. The Django adapter

```python
class Document(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    file  = SealedFileField(upload_to="docs/",
                            context=lambda inst: {"user_id": inst.owner_id})
```

- **KEK custody only.** `CallerHeld` makes no sense in a field the server must be able to
  read; configuring it that way fails during Django's **system checks**, not at runtime.
- The `context` callable receives the model instance and **must only use fields that are
  already populated when the file is written**. Referring to `inst.pk` on an unsaved
  instance is a documented error, not a surprise ([Q4](#16-open-questions)).
- The `context` callable **must be stable for the life of the row**. Binding to a
  transferable owner means a transfer makes the file unopenable. The adapter documents this
  in bold and the check framework warns when the callable references a nullable or
  editable field it can detect.
- Streaming is preserved end to end: the field wraps Django's `Storage`, so a large upload
  never lands in memory.

## 14. Versioning and compatibility

| Thing | Versioning |
|---|---|
| The library | SemVer. Public API = what `aegis/__init__.py` exports. |
| The file format | An independent byte. See [file-format.md § 8](file-format.md#8-changing-this-format). |
| Frozen vectors | Immutable. Changing them **is** a format change. |
| Python | 3.10+ at 1.0. A drop is a minor release, announced one release ahead. |
| `cryptography` | A floor, never a ceiling pin, so security updates flow to users. |

Anything not exported from `aegis/__init__.py` is private and may change in a patch
release. The dogfood test exists to prove we believe that.

## 15. Non-goals of this architecture

- **Pluggable ciphers.** The suite byte allows a future suite; the code has no strategy
  pattern, no registry and no `algorithm=` parameter. Configurable cryptography is how
  users pick the weak option.
- **A generic streaming framework.** `stream.py` implements STREAM for one suite. It is not
  an abstraction over AEADs.
- **Backwards compatibility with anything.** There is no legacy reader and no migration
  path from another library's format ([ADR-0012](decisions.md#adr-0012-no-legacy-format-reader)).

## 16. Open questions

Collected here so they are decided deliberately rather than by whoever writes the code
first. **Q1 and Q2 block implementation; Q3–Q7 do not.**

**Q1 — Chunk AAD versus rotation. *Resolved here; needs confirmation.***
`initial-spec.md` § 6 specifies `aad = sha256(header)` over all 94 bytes, but `aegis rotate`
rewrites bytes inside that header, which would invalidate every chunk in the file. The two
cannot coexist. Resolved by hashing the immutable header core only
([file-format.md § 4.3](file-format.md#43-associated-data),
[ADR-0014](decisions.md#adr-0014-chunk-aad-covers-the-immutable-header-core-only)). The
cost is losing the "convert caller-held to KEK custody by rewriting the header" bonus,
which was never a 1.0 feature. **Confirm before M2.**

**Q2 — How is a KEK encoded inside an environment variable?** `initial-spec.md` requires
"exactly 32 bytes", but an environment variable holds text. Proposal: strict standard base64
with padding (44 characters), everything else rejected with a `ConfigurationError` that shows
how to generate one; plus an `aegis keygen` command so the developer never has to invent the
incantation. Hex is rejected deliberately — one canonical form
([ADR-0015](decisions.md#adr-0015-keks-in-environment-variables-are-base64)). **Confirm before
M3.**

**Q3 — May `context` be empty?** `initial-spec.md` § 5.2 says context is mandatory, but the §
5.1 example calls `vault.seal(src, dst)` with none. Proposal: the parameter is required;
`context={}` is legal and canonicalizes to the empty byte string; `context=None` raises
`UsageError`. Making people type `{}` keeps the absence deliberate and visible in a code
review.

**Q4 — Django contexts and unsaved instances.** A callable referencing `inst.pk` cannot
work before the first `INSERT`. Options: document it as the caller's responsibility (cheap,
sharp edge), or raise a specific `UsageError` when the callable touches an unset field
(kind, but requires introspection we may not be able to do reliably). Leaning towards
document + a system check for the common cases.

**Q5 — Domain separation in the AAD hashes.** Should the AAD be
`SHA256(b"aegis-hdr-v1" ‖ core) ‖ SHA256(b"aegis-ctx-v1" ‖ context)` instead of plain
SHA-256? It costs nothing and forecloses cross-protocol collisions. It must be decided
before the vectors freeze at M4, because afterwards it is a new format version.

**Q6 — Is `aegis` available on PyPI?** The name appears in the package, the CLI **and the
HKDF `info` strings**. Changing it after 1.0 is expensive; before M4 it is trivial.

**Q7 — Should `Receipt` expose the `kek_id`?** Useful for operations (recording which key
sealed which row), and it is public metadata anyway. Additive, so it can wait.
