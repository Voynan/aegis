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
   packages and fails on any `aegis.<private>` import. Two such gaps are already known:
   [Q10 and Q11](#16-open-questions).
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

Where the context check belongs in this sequence is open ([Q23](#16-open-questions)).

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

Two parts of this seam are still open: third-party implementations need `CustodyBlock`, which is
not exported yet ([Q12](#16-open-questions)), and nothing specifies what happens when a vault's
custody mode does not match a file's ([Q26](#16-open-questions)).

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
by chunk overhead, which at 64 KiB is negligible. Targets, the measured baseline and the
release gates are in [performance.md](performance.md).

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
   removed and nothing survives. Whether the rename itself survives a crash is open
   ([Q21](#16-open-questions)).

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
| `aegis keygen` | Print a fresh 32-byte KEK, base64-encoded ([Q2](#16-open-questions)) |
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

Still open for the CLI ([§ 16](#16-open-questions)): the public calls behind `inspect` and
`rotate` (Q10, Q11), how it receives keys (Q13), which context types it can express (Q14), how
`rotate --recursive` treats mixed directories (Q15), and how `inspect` reports sizes (Q24).

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
- **Open:** how the field receives its `Vault` ([Q16](#16-open-questions)).

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
first.

| Q | Question | Status | Decide before |
|---|---|---|---|
| Q1 | Chunk AAD versus rotation | resolved — ADR-0014 | — |
| Q2 | KEK encoding in environment variables | resolved — ADR-0015 | — |
| Q3 | May `context` be empty? | resolved — ADR-0020 | — |
| Q4 | Django contexts on unsaved instances | open | M7 |
| Q5 | Domain separation in the AAD hashes | resolved — ADR-0019 | — |
| Q6 | The PyPI name | resolved — ADR-0018 | — |
| Q7 | `Receipt.kek_id` | open | M9 |
| Q8 | Rotation without `pwrite` on Windows | open | M5 |
| Q9 | Torn writes during rotation | open | M4 for option 4, otherwise M5 |
| Q10 | No public API behind `aegis inspect` | open | M3 |
| Q11 | No public API behind `aegis rotate` | open | M5 |
| Q12 | `KeySource` and `CustodyBlock` are not exported | open | M3 |
| Q13 | How the CLI receives keys | open | M6 |
| Q14 | Context types the CLI can express | open | M6 |
| Q15 | `aegis rotate --recursive` over mixed directories | open | M5 |
| Q16 | How `SealedFileField` receives its `Vault` | open | M7 |
| Q17 | Hypothesis example database: committed or ignored | open | M0 |
| Q18 | PyPI name reservation | open | M0 |
| Q19 | Public review scheduled after the freeze | open | M2 |
| Q20 | The error for a short non-Aegis file | open | M1 |
| Q21 | Durability of `unseal_to_path` | open | M3 |
| Q22 | The 2³² chunk limit | open | M2 |
| Q23 | When `unseal` validates `context` | open | M3 |
| Q24 | `aegis inspect` and unauthenticated sizes | open | M6 |
| Q25 | Missing negative vector for KEK custody | open | M4 |
| Q26 | Custody-mode mismatches | open | M3 |

Q10–Q26 were found on 2026-09-14 while turning the roadmap into a task list. Each one says what
the documents claim, what breaks, a proposal, and which documents a decision would change.

**Q1 — Chunk AAD versus rotation. *Resolved.***
`initial-spec.md` § 6 specifies `aad = sha256(header)` over all 94 bytes, but `aegis rotate`
rewrites bytes inside that header, which would invalidate every chunk in the file. The two
cannot coexist. Resolved by hashing the immutable header core only
([file-format.md § 4.3](file-format.md#43-associated-data),
[ADR-0014](decisions.md#adr-0014-chunk-aad-covers-the-immutable-header-core-only)). The
cost is losing the "convert caller-held to KEK custody by rewriting the header" bonus,
which was never a 1.0 feature. ADR-0014 accepted.

**Q2 — How is a KEK encoded inside an environment variable? *Resolved.***
`initial-spec.md` requires "exactly 32 bytes", but an environment variable holds text.
Decision: strict standard base64
with padding (44 characters), everything else rejected with a `ConfigurationError` that shows
how to generate one; plus an `aegis keygen` command so the developer never has to invent the
incantation. Hex is rejected deliberately — one canonical form
([ADR-0015](decisions.md#adr-0015-keks-in-environment-variables-are-base64), accepted).

**Q3 — May `context` be empty? *Resolved.*** `initial-spec.md` § 5.2 says context is
mandatory, but the § 5.1 example calls `vault.seal(src, dst)` with none. Decision: the
parameter is required; `context={}` is legal and canonicalizes to the empty byte string;
`context=None` raises `UsageError`. Making people type `{}` keeps the absence deliberate and
visible in a code review
([ADR-0020](decisions.md#adr-0020-context-is-required-but-may-be-empty)).

**Q4 — Django contexts and unsaved instances.** A callable referencing `inst.pk` cannot
work before the first `INSERT`. Options: document it as the caller's responsibility (cheap,
sharp edge), or raise a specific `UsageError` when the callable touches an unset field
(kind, but requires introspection we may not be able to do reliably). Leaning towards
document + a system check for the common cases.

**Q5 — Domain separation in the AAD hashes. *Resolved.*** The AAD is
`SHA256(b"aegis-hdr-v1\x00" ‖ core) ‖ SHA256(b"aegis-ctx-v1\x00" ‖ context)` instead of plain
SHA-256. It costs nothing and forecloses cross-protocol collisions; the `\x00` terminator
matches the `kek_id` label
([ADR-0019](decisions.md#adr-0019-domain-separated-aad-hashes)).

**Q6 — Is `aegis` available on PyPI? *Resolved.*** It is not. The PyPI distribution is
`aegis-voynan`; the import package, the CLI and every string in the file format stay
`aegis` ([ADR-0018](decisions.md#adr-0018-distribute-as-aegis-voynan-import-as-aegis)).

**Q7 — Should `Receipt` expose the `kek_id`?** Useful for operations (recording which key
sealed which row), and it is public metadata anyway. Additive, so it can wait.

**Q8 — Rotation has no `pwrite` on Windows. *Blocks M5.*** The rotation design
([roadmap.md § M5](roadmap.md#m5--rotatepy), [tests.md § 6](tests.md#6-layer-5--rotation-and-dogfood))
writes the 80-byte custody block "as a single `pwrite`". `os.pwrite` is POSIX-only and does
not exist on Windows, which is in the CI matrix. Proposal: use `os.pwrite` where it exists;
elsewhere open the file `r+b`, `seek(7)` and issue one 80-byte `write`; then `fsync` in both
cases. Neither is atomic against power loss, which is Q9. What Q8 settles is only that the
code path and its tests exist on all three platforms. **Decide before M5.**

**Q9 — A torn write during rotation can make a file permanently unreadable. *Blocks M5.***
The documents claim that "an interrupted rotation leaves a file that still opens with the old
KEK". That holds when the **process** dies: a single 80-byte `write` either reaches the page
cache or it does not. It does **not** hold for **power loss or a kernel crash** mid-write.
The storage layer does not guarantee that a sector is written all-or-nothing, and filesystems
without data journaling (ext4 `data=ordered`, APFS, NTFS) do not add that guarantee. The
result can be a custody block that is half old, half new:

- `kek_id` may name either KEK, but `salt` and `wrapped_dek` no longer match it.
- The unwrap fails under **both** KEKs, and the GCM tag cannot tell which bytes are right.
- The DEK is lost, so the file is lost. The body is intact but undecryptable.

The window is small (one sector, milliseconds) but it is repeated once per file across a
whole bucket. A library whose selling point is key rotation must not turn a power cut during
rotation into data loss. Options:

1. **Accept and document.** Say that rotation is crash-safe against process death only, and
   tell operators to back up first. Cheapest, and it moves the risk to the user.
2. **Rewrite the whole file.** Write a temporary copy with the new custody block, `fsync`,
   `os.replace`. Atomic, but it reads and writes the whole body, destroying the
   "10 TB rotates in minutes" property.
3. **Journal the old block (recommended).** Before overwriting, write a sidecar
   `<file>.aegis-rotate` holding the path, the old 80 bytes and a SHA-256 of them. `fsync`
   the sidecar and its directory. Then write the 80 bytes, `fsync` the file, and delete the
   sidecar. `aegis rotate` checks for leftover sidecars before doing anything else. For
   each, it keeps whichever block (on disk or journaled) unwraps under a configured KEK and
   restores the other if needed. Cost: two extra `fsync`s and one small file per rotated
   file, no format change.
4. **Redundant custody block in the format.** Store two copies and write them one at a
   time. Robust, but it is a format change (94 → 174 bytes) and must land before M4.

Option 3 keeps the headline property and needs no format change. Option 4 is the only one
that also protects rotations done by third-party tools, and it is only free before M4.
**Decide before M4 if option 4 is considered, otherwise before M5.**

Related: in-place rotation assumes a POSIX-like filesystem. Object stores (S3, GCS, Azure
Blob) cannot overwrite 80 bytes of an object; they replace whole objects. There, rotation
means rewriting every object (a server-side copy, or a download and upload), and the
"rotates in the time it takes to enumerate" claim in [usage.md § 8](usage.md#8-rotating-your-master-key)
does not hold. Object replacement is atomic, so Q9 does not arise there. Whatever Q9
decides, usage.md must state which storage gets in-place rotation.

**Q10 — No public API behind `aegis inspect`. *Blocks M3.*** The dogfood rule
([§ 3](#3-layering-rules)) lets the CLI import only what `aegis/__init__.py` exports, which
[§ 2.1](#21-package-layout) lists as `Vault`, `EnvKey`, `CallerHeld`, `Receipt` and the errors.
None of them reads a header without decrypting, so `aegis inspect` ([§ 12](#12-the-cli)) can only
be written by importing `aegis.format` — which the dogfood test
([tests.md § 6](tests.md#6-layer-5--rotation-and-dogfood)) rejects. Applications need the same
thing: finding which KEK sealed a stored blob, the operational use behind Q7, without holding the
key. Proposal: a public `aegis.inspect(src) -> FileInfo`, a frozen record of `version`, `suite`,
`custody`, `kek_id` (or `None`) and, for a seekable source, `chunks` and `plaintext_size` (see
Q24). It never takes a key. Would change: §§ 2.1 and 12, usage.md § 9. **Decide before M3**,
when the public API is fixed.

**Q11 — No public API behind `aegis rotate`. *Blocks M5.*** Same rule, same problem: the CLI
command must call something exported, and nothing is. Applications that walk their own storage —
a Django management command, a background job — need it too. Proposal:
`aegis.rotate(path, *, key: EnvKey) -> RotationResult`, where the result is `rotated`,
`already_current` or `skipped_caller_held`; recursion and reporting stay in the CLI (Q15). It
takes a path, not a stream, because rotation is the only operation that seeks
([§ 4](#4-the-purity-boundary-randomness-lives-at-the-edges)). **Decide before M5.**

**Q12 — `KeySource` and `CustodyBlock` are not exported. *Blocks M3.***
[§ 6](#6-the-custody-seam) promises that a KMS, Vault or HSM integration is "two functions and
zero changes to the core", and [§ 11](#11-typing) uses `Protocol` "so that third-party
implementations need no import from us at runtime". But `provision()` returns a `CustodyBlock`
and `recover()` receives one, and neither `CustodyBlock` nor `KeySource` is exported. A
third-party implementation must import a private module, or define a look-alike class that
`mypy --strict` rejects, because dataclasses are typed nominally. Proposal: export both from
`aegis`, and keep a fake KMS in the test suite that imports only the public API, covered by the
dogfood test. Would change: §§ 2.1, 6 and 11. **Decide before M3.**

**Q13 — How the CLI receives keys. *Blocks M6.*** [usage.md § 9](usage.md#9-cli) runs
`aegis seal in.pdf out.aegis --context user_id=42` with no key argument, and nothing specifies:

- which environment variable `seal`, `unseal` and `rotate` read — `AEGIS_MASTER_KEY` appears only
  in examples;
- how `rotate` receives the primary and previous KEKs that `EnvKey(primary=, previous=)` needs;
- how caller-held custody works from a shell. `seal` must hand the generated key to the user and
  `unseal` must take it back, and both obvious channels are wrong: argv is visible in `ps` and in
  shell history, and stdout already carries the ciphertext when piping.

Proposal: `--key-env NAME` (default `AEGIS_MASTER_KEY`) and a repeatable `--previous-env NAME`;
for caller-held custody, `seal --caller-held --key-out PATH` (created with mode `0600` on POSIX,
refused if it exists) and `unseal --key-file PATH`. Key bytes never appear on argv or on a
standard stream. Would change: § 12, usage.md § 9. **Decide before M6.**

**Q14 — Context types the CLI can express. *Blocks M6.*** `--context k=v` produces a `str` and
`--context-int k=v` an `int` (usage.md § 9). The library also accepts `bytes`, `bool` and `None`
([file-format.md § 5](file-format.md#5-canonical-serialization-of-context)), and the type is part
of the canonical encoding, so a file sealed with `{"tenant": b"\x01", "archived": False}` cannot
be opened from the shell at all — during an incident, exactly when an operator reaches for the
CLI. Proposal: `--context-hex k=HEX` for `bytes`, `--context-bool k=true|false` and
`--context-null k`. The alternative is to state the limitation in usage.md § 9 and leave such
files to the application. **Decide before M6.**

**Q15 — `aegis rotate --recursive` over mixed directories. *Blocks M5.***
[usage.md § 8](usage.md#8-rotating-your-master-key) runs `aegis rotate ./bucket --recursive`.
Real directories hold more than KEK-custody Aegis files, and nothing says what happens with:

- a caller-held file, which has no custody block to re-wrap;
- a file that is not an Aegis file — a thumbnail, a partial upload, a `.DS_Store`;
- a file whose `kek_id` matches no configured KEK;
- a failure midway, and the exit code when some files succeed and others fail — the table in
  [§ 12](#12-the-cli) has one code per run.

Aborting at the first stray file makes rotating a real bucket impractical; skipping silently
makes an `UnknownKek` easy to miss. Proposal: skipped files (caller-held, not Aegis) get one report
line each and do not fail the run; per-file errors are reported and the run continues; a summary
ends the output; the exit code is `0` if nothing failed, otherwise the code of the first failure;
`--fail-fast` stops at that failure. Would change: § 12, usage.md § 8. **Decide before M5.**

**Q16 — How `SealedFileField` receives its `Vault`. *Blocks M7.*** The field in
[§ 13](#13-the-django-adapter) and [usage.md § 10](usage.md#10-django) takes `upload_to` and
`context` and nothing else — no vault, no key source, no setting name — so it has nothing to seal
with. Options: a `vault=` argument; a project-wide `AEGIS_VAULT` setting; or both, the argument
overriding the setting. Either should accept a dotted path resolved lazily: an `EnvKey` built at
model import time would make every `manage.py` command, `migrate` included, fail on a machine
without the key. Proposal: both, as dotted paths; a system check verifies that the vault resolves
and uses KEK custody, next to the existing `CallerHeld` rejection. **Decide before M7.**

**Q17 — Hypothesis example database: committed or ignored? *Blocks M0.***
[tests.md § 4.2](tests.md#42-the-adversarial-suite) commits "a `.hypothesis` example database …
for the failing cases we have found", while [roadmap.md § M0](roadmap.md#m0--repository-scaffolding)
lists `.hypothesis/` among the paths the new `.gitignore` must ignore. Both cannot hold. The
database is also a poor home for regressions: it holds whatever examples Hypothesis kept on the
machine that ran it, in a format that may change between Hypothesis versions, and a reviewer
cannot read it. Proposal: ignore `.hypothesis/`, and pin every failure found as an explicit
`@example(...)` on the property it broke — reviewed, versioned and independent of the database
format. Would change: tests.md § 4.2. **Decide before M0.**

**Q18 — PyPI name reservation. *Blocks M0.*** roadmap.md M0 reserves `aegis-voynan` with "a
pending trusted publisher or a placeholder release", and
[ADR-0018](decisions.md#adr-0018-distribute-as-aegis-voynan-import-as-aegis) says the same.
PyPI's documentation says a pending publisher "does not create a project or reserve a project's
name until it is actually used to publish". Until a first upload, anyone can register the name
that the repository and ADR-0018 already announce. Proposal: configure the pending publisher,
then publish a `0.0.0` placeholder through `release.yml` right away — which also proves the
publishing path at M0 instead of at M9. Would change: roadmap.md M0, and an erratum on ADR-0018.
**Decide before M0.**

**Q19 — Public review scheduled after the freeze. *Blocks M2.*** roadmap.md requests the public
review of `stream.py` and `file-format.md` at M8, but freezes the format at M4
([ADR-0013](decisions.md#adr-0013-freeze-the-format-at-milestone-m4)). A finding at M8 that
touches bytes on disk leaves two bad options: ship 1.0 with a known format flaw and fix it in a
v2, or regenerate frozen vectors and break the rule the compatibility promise rests on
([file-format.md § 8](file-format.md#8-changing-this-format)). The review is also the step with
the least predictable lead time. Proposal: request review of `file-format.md` now, since it is
complete; request review of `stream.py` when M2 closes; make "format review feedback triaged" part
of the M4 gate; keep M8 as the final review of what was built. Would change: roadmap.md M2, M4
and M8; security.md § 4.1. **Decide before M2.**

**Q20 — The error for a short non-Aegis file. *Blocks M1.***
[file-format.md § 6.2](file-format.md#62-unsealing) reads 94 bytes and raises `MalformedHeader`
on a short read *before* comparing the magic. An empty file, a 10-byte text file or a small
thumbnail therefore reports "the first 94 bytes are truncated or inconsistent" instead of
`NotAnAegisFile` — "wrong path, or a double-decrypt"
([usage.md § 6](usage.md#6-errors-and-what-to-do-about-each)) — and sends the developer looking
for a damaged Aegis file that never existed. Proposal: when fewer than 94 bytes arrive, compare
the available prefix (up to 4 bytes) with the magic first: an empty stream or a mismatch raises
`NotAnAegisFile`, a matching prefix raises `MalformedHeader`. This changes exception classes, not
bytes — but the negative vectors pin exception classes. Would change: file-format.md § 6.2,
tests.md § 3. **Decide before M1.**

**Q21 — Durability of `unseal_to_path`. *Blocks M3.*** [§ 10](#10-secret-hygiene) and
[security.md § 6](security.md#6-the-streaming-trust-boundary) describe `unseal_to_path` as:
write a temporary file, `fsync` it, `os.replace` it onto the destination. On POSIX the rename is
a change to the directory, and it is not durable until the directory is synced: a power loss
after `unseal_to_path` has returned can leave the destination missing, or with its previous
content — after the caller has already deleted the sealed original or marked the job done.
Windows cannot open a directory to `fsync` it. Proposal: `fsync` the file, `os.replace`, then
`fsync` the destination directory on POSIX; on Windows, document that the durability of the
rename is the filesystem's. Would change: § 10, security.md § 6, tests.md § 7.
**Decide before M3.**

**Q22 — The 2³² chunk limit. *Blocks M2.*** [file-format.md § 7.3](file-format.md#73-limits) says
a writer that reaches 2³² chunks "MUST raise rather than wrap the counter". Two problems:

- **The rule cannot be tested as written.** 2³² chunks is 256 TiB, and nothing in `stream.py`
  lets a test lower the limit. An untested MUST inside the one module held to 100 % branch
  coverage is a coverage hole by construction.
- **The reader has no rule at all.** It can only reach a 2³²-th chunk after authenticating 2³²
  chunks, so this is not an attack: it takes a file produced with the right key by a
  non-conforming writer. The obvious implementation then calls `counter.to_bytes(4, "big")` with
  `counter == 2**32` and raises `OverflowError`, which is not an `AegisError` and escapes the
  error model ([§ 9](#9-error-model)).

Proposal: one `MAX_CHUNKS = 2**32` constant in `stream.py`, checked before each nonce is built,
in both directions. The writer raises `UsageError` (the input is too large to seal); the reader
raises `UnsealFailed`. Tests lower the constant; that is not randomness, so the purity boundary
([§ 4](#4-the-purity-boundary-randomness-lives-at-the-edges)) holds. Would change:
file-format.md §§ 6.1, 6.2 and 7.3; tests.md § 7. **Decide before M2.**

**Q23 — When `unseal` validates `context`. *Blocks M3.*** [§ 5.2](#52-unseal) orders `unseal` as:
parse the header, recover the key, canonicalize the context, decrypt. [§ 9](#9-error-model) says
`UsageError` is raised "as early as the information allows", and a context can be validated
before a single byte is read. With the documented order,
`vault.unseal(src, dst, context={"ratio": 0.5})` on a file sealed under a KEK that is not
configured raises `UnknownKek`: the developer goes to check the environment, while the actual
bug — a `float` in their own call — is still there once the key problem is fixed. It also
consumes 94 bytes of a non-seekable stream before reporting a programming error. Proposal:
canonicalize `context` first in `unseal`, `unseal_bytes` and `unseal_to_path`, as `seal` already
does. Would change: § 5.2. **Decide before M3.**

**Q24 — `aegis inspect` and unauthenticated sizes. *Blocks M6.*** `inspect` never decrypts
([§ 12](#12-the-cli)), so the `chunks` and `plaintext` lines in usage.md § 9 can only come from
the file size, which nothing authenticates. A file truncated in the middle of a chunk prints a
plausible, wrong plaintext size — while an operator is using `inspect` to diagnose exactly that
kind of damage. Some sizes are impossible for a valid container and detectable without a key: a
body shorter than 16 bytes, or `(size − 94) mod 65552` between 1 and 15. A non-seekable stdin has
no size at all. Proposal: label both lines as derived from the file size; print
`inconsistent size — truncated, or not an Aegis file` for impossible sizes; on stdin, count bytes
to the end without decrypting. Would change: § 12, usage.md § 9. **Decide before M6.**

**Q25 — Missing negative vector for KEK custody. *Blocks M4.***
[file-format.md § 6.2](file-format.md#62-unsealing) requires the custody block to be zero if and
only if the file is caller-held, so two headers raise `MalformedHeader`: a non-zero block in
caller-held mode, and an all-zero block under KEK custody.
[tests.md § 3](tests.md#3-layer-1--frozen-vectors-kat) lists only the first. The missing case is
the one a buggy writer is likeliest to produce — a header assembled before the wrap was filled
in. Unit tests cover the rule in this implementation, but the frozen vectors are the contract any
other implementation is checked against: a future port could accept such a header and still pass
them. Proposal: add "KEK custody with an all-zero custody block → `MalformedHeader`" to the
negative vectors. Would change: tests.md § 3. **Decide before M4**: after the freeze, adding a
case means touching a frozen file.

**Q26 — Custody-mode mismatches. *Blocks M3.*** Three calls are plausible mistakes, and none has
a specified outcome:

- an `EnvKey` vault unsealing a caller-held file — there is no wrapped key to recover;
- a `CallerHeld` vault unsealing a KEK-custody file — the caller's key is not that file's key;
- `key=` passed to `unseal` on an `EnvKey` vault — the argument is silently meaningless.

Left to the implementation, the first ends in `UnknownKek` reporting a KEK id of zeros, and the
second in `UnsealFailed` ("wrong key, wrong context, or corrupted file"). Both mislead: the
custody mode is in the header's `flags` and decidable before any decryption, which is exactly
the kind of failure
[ADR-0008](decisions.md#adr-0008-collapse-indistinguishable-failures-into-one-error) gives its
own answer. The third hides a misunderstanding of custody. Proposal: `UsageError` in all three
cases, raised after the header is parsed and before any decryption, naming the file's custody
mode and the call that opens it. Would change: §§ 6 and 9, usage.md § 6. **Decide before M3.**
