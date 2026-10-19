# Architecture

How the code is organised, and why. The byte-level format lives in
[file-format.md](file-format.md); this document is about the shape of the Python. For the same
structure in pictures — modules, key hierarchy, the seal and unseal flows — see
[diagrams.md](diagrams.md).

---

## 1. The one rule

> **Cryptographic risk stays isolated in two small modules, and everything that is not
> crypto does not know what crypto is.**

Every other rule here is a consequence of that one. In `stream.py` (the chunk framing) and
`envelope.py` (the per-file key schedule, the key commitment and the local DEK wrap), a subtle
mistake is a vulnerability rather than a bug. Each must therefore be small enough to read in
one sitting, pure enough to test exhaustively, and boring enough that a reviewer who is a
cryptographer can audit both in an hour.

If either grows past roughly one screen, it has become a junk drawer and something must move
out.

## 2. Module map

| Module | Single responsibility | Depends on | Tested with |
|---|---|---|---|
| `errors.py` | The exception hierarchy | — (leaf) | — |
| `format.py` | Header ↔ dataclasses: the core, the custody record, offsets and labels. No crypto, no I/O | `errors` | raw bytes, fuzzing |
| `context.py` | Canonical serialization → labelled SHA-256 | `format`, `errors` | a table of cases |
| `envelope.py` | Key schedule (body key, nonce prefix, commitment), `kek_id`, local DEK wrap. **Crypto, pure** | `cryptography`, `format`, `errors` | frozen vectors |
| `stream.py` | STREAM: chunking, nonces, the final-chunk flag, truncation classification. **Crypto, pure** | `cryptography`, `errors` | `BytesIO`, frozen vectors |
| `keys.py` | Key configuration: `EnvKey`, `FileKey`, `BytesKey`, `CallerHeld`, the `KeySource` protocol | `envelope`, `errors` | a fake environment, temp files |
| `readers.py` | Pull-style readers over `stream.py`, seekable when the source is | `stream`, `format`, `errors` | `BytesIO`, properties |
| `info.py` | `inspect()`: the header and size-derived numbers, never decrypts | `format`, `errors` | raw bytes |
| `vault.py` | Orchestrates the above and draws all randomness. Reads like prose | all of the above | integration |
| `rotate.py` | In-place custody rewrite with its journal, and `rewrap` | `format`, `envelope`, `keys`, `errors` | temp files |

```
aegis.cli                                      ← adapter: public API only
aegis/__init__.py                              ← the public surface (§ 2.2)
vault.py · rotate.py                           ← orchestration
readers.py · info.py · keys.py · context.py    ← I/O shape and configuration
stream.py · envelope.py · format.py            ← crypto (pure) and the format
errors.py                                      ← leaf, imports nothing
( stream, envelope → cryptography )
```

Dependencies flow downward only. There are no cycles, and the absence of cycles is enforced by
a test, not by good intentions ([tests.md § 6](tests.md#6-layer-5--rotation-and-dogfood)).

### 2.1 Package layout

```
src/aegis/
├── __init__.py        # the public API (§ 2.2)
├── errors.py
├── format.py
├── context.py
├── envelope.py
├── stream.py
├── keys.py
├── readers.py
├── info.py
├── vault.py
├── rotate.py
├── py.typed
└── cli/               # extra: [cli]
    ├── __init__.py
    └── __main__.py
```

The package sits under `src/`, so it is importable only once installed
([ADR-0025](decisions.md#adr-0025-the-package-lives-in-src)); these documents name its files
relative to the package, as `aegis/__init__.py` or `stream.py`. The rest of the repository —
tests, benchmarks, tools, workflows — is laid out in [structure.md](structure.md).

There is no `contrib/` in 1.0. The Django adapter, `aegis.contrib.django`, is planned for V2
([ADR-0034](decisions.md#adr-0034-the-django-adapter-moves-to-v2), [dev/v2-django.md](dev/v2-django.md)).
It will live under `contrib/` so that `import aegis.django` can never shadow or be confused with
the `django` package, and so that "contrib" reads as what it is — an adapter, not the core.

### 2.2 The public API

Everything `aegis/__init__.py` exports, and nothing else:

| Name | What it is |
|---|---|
| `Vault` | `seal`, `unseal`, `seal_bytes`, `unseal_bytes`, `unseal_to_path`, `sealed`, `unsealed`, `rotate`, `rewrap` |
| `EnvKey`, `FileKey`, `BytesKey` | local-KEK key sources ([ADR-0029](decisions.md#adr-0029-local-key-sources-envkey-filekey-and-byteskey-with-an-entropy-floor)) |
| `CallerHeld` | the caller-custody marker |
| `KeySource` | the protocol for external custody (§ 6) |
| `inspect` | reads a header without a key, returns `FileInfo` |
| `Receipt`, `FileInfo`, `RotationResult` | frozen records |
| `SealedReader`, `UnsealedReader` | the reader types, for annotations |
| the errors of § 9 | exceptions |

Anything not exported here is private and may change in a patch release.

## 3. Layering rules

1. **Downward dependencies only.** A module may import modules below it in the table above.
   Never sideways into a peer's internals, never upward.
2. **The core imports no framework.** `aegis` (excluding `cli/`) depends on exactly one
   third-party package: `cryptography`.
3. **Dogfood rule.** `aegis.cli` — and, from V2, `aegis.contrib.django` — may import **only the
   public API**. If an adapter needs a private import, that is not an implementation detail — it
   is proof that the public API is incomplete. Enforced by an AST test that walks the adapter
   packages and fails on any `aegis.<private>` import. The gaps found so far (Q10–Q12, Q38) are
   closed by § 2.2.
4. **No blanket `except Exception`** anywhere in the library. Catch the exception you can
   describe; let the rest propagate.

## 4. The purity boundary: randomness lives at the edges

This is the architectural consequence of demanding frozen test vectors, and it is easy to get
wrong by writing the obvious code first.

- `format.py` and `context.py` are **pure**: bytes in, bytes out. No I/O, no clock, no RNG.
- `envelope.py` and `stream.py` are **pure given their inputs**. They receive the DEK, the salt,
  the KEK and the AAD as parameters. They never call `os.urandom` and never open a file;
  `stream.py` consumes and produces byte segments through iterators.
- `keys.py` is where the environment and key files enter.
- `vault.py` is the **only** module that draws randomness: the DEK and the salt, two calls per
  seal. It passes them to an internal pure function that the frozen vectors call directly.

Because of this split, a known-answer test can pin every byte of the output without
monkey-patching the random module, and the modules carrying all the risk can be tested as pure
functions. If a test ever needs to patch `os.urandom` to reach `envelope.py` or `stream.py`, the
boundary has been violated.

**Sealing never seeks; unsealing seeks only when it can.** `seal`, `unseal`, `sealed` and
`rewrap` treat their streams as forward-only, so a pipe, a socket, an HTTP body or a `BytesIO`
all work identically. Sealing reads one segment ahead in order to know which segment is the
last ([file-format.md § 6.1](file-format.md#61-sealing)); it never rewinds to patch what it
already wrote. `unsealed` seeks when its source is seekable, to authenticate the final chunk
and to serve random access ([file-format.md § 6.3](file-format.md#63-random-access)). `rotate`
seeks, on a real file.

## 5. Control flow

### 5.1 `seal`

```
Vault.seal(src, dst, context)
  │
  ├─ context.canonicalize(context) ──────────────▶ canonical            [pure]   UsageError first
  ├─ os.urandom(32) twice ───────────────────────▶ dek, salt            [random]
  ├─ envelope.schedule(dek, salt) ───────────────▶ body_key, nonce_prefix, commitment   [pure]
  ├─ format.Core(custody, salt, commitment, custody_len).to_bytes() ─▶ 73 bytes        [pure]
  ├─ custody record ─────────────────────────────▶ envelope.wrap_local · source.wrap · none
  ├─ dst.write(core ‖ record)
  ├─ stream.encrypt(body_key, nonce_prefix, aad, src, dst)              [pure-ish: I/O by iterator]
  └─ Receipt(size=…, algorithm=…, version=…, key=…, key_id=…)
```

### 5.2 `unseal`

```
Vault.unseal(src, dst, context, key=None)
  │
  ├─ context.canonicalize(context); custody arguments ──▶ UsageError before any read
  ├─ format.read_header(src) ─────────────────────▶ core + custody record    [pure parsing]
  │     └─ raises NotAnAegisFile / UnsupportedVersion / MalformedHeader
  ├─ custody mode against the vault ──────────────▶ UsageError / UnknownKek
  ├─ recover the DEK ─────────────────────────────▶ caller key · envelope.unwrap_local · source.unwrap
  │     └─ raises UnknownKek before any decryption; KeyMismatch if the record does not authenticate
  ├─ envelope.schedule(dek, salt); compare commitment ─▶ KeyMismatch before the body
  └─ stream.decrypt(body_key, nonce_prefix, aad, src, dst)
        └─ raises UnsealFailed / TruncatedFile (file-format.md § 6.2)
```

`vault.py` contains no cryptographic decision. It reads as a sequence of named steps — if a
reviewer cannot follow it aloud, it is wrong.

### 5.3 The readers

`sealed()` performs § 5.1 lazily: the header on the first read, then one chunk per refill; its
`Receipt` exists once the reader has been read to the end. `unsealed()` performs § 5.2 up to and
including the commitment check when it is called. With a seekable source it then authenticates
the final chunk ([file-format.md § 6.3](file-format.md#63-random-access)) before returning, so a
caller never receives a byte of a truncated file.

## 6. The custody seam

One decision in the constructor, three custody modes:

| `Vault(key=…)` | `custody` byte | Where the DEK goes |
|---|---|---|
| `EnvKey`, `FileKey`, `BytesKey` | `0x01` local KEK | wrapped by Aegis under your KEK, in the header |
| any object implementing `KeySource` | `0x02` external | wrapped by your source — a KMS, an HSM, Vault Transit — in the header |
| `CallerHeld()` | `0x00` caller-held | returned in the `Receipt`; nothing is stored |

Third-party custody is one protocol over plain bytes
([ADR-0026](decisions.md#adr-0026-the-library-draws-every-data-key-key-sources-only-wrap-and-unwrap)):

```python
class KeySource(Protocol):
    key_id: bytes    # 16 bytes, not all zero: the key wrap() uses now
    capacity: int    # the largest payload wrap() returns; fixed for the source
    def wrap(self, dek: bytes, aad: bytes) -> bytes: ...
    def unwrap(self, key_id: bytes, payload: bytes, aad: bytes) -> bytes: ...
```

- **The library draws every DEK.** A source never generates or chooses one; it only wraps and
  unwraps.
- **Bind the associated data.** `aad` is `SHA256("aegis-custody-v1\x00" ‖ header core)`. Bind it
  when your backend can: an AWS KMS encryption context, Google Cloud KMS additional
  authenticated data, Vault Transit associated data. The key commitment detects a wrong DEK
  either way.
- **Failures.** `unwrap` raises `UnknownKek` for a key id it does not manage, and
  `KeyMismatch` when the payload does not authenticate — translate your KMS's "invalid
  ciphertext" answer into it. Operational failures (network, permissions) propagate unchanged;
  Aegis does not catch what it cannot name.
- **Space.** The format stores up to `capacity` payload bytes, padded with zeros, and at most
  4 078 ([file-format.md § 3.4](file-format.md#34-external-custody-custody--0x02)).

A non-normative sketch over AWS KMS. The capacity is a bound chosen with headroom; a source
must never return more:

```python
import hashlib
from aegis import KeyMismatch, UnknownKek

class AwsKms:
    capacity = 512

    def __init__(self, client, key_arn: str) -> None:
        self._kms, self._arn = client, key_arn
        self.key_id = hashlib.sha256(b"aws-kms\x00" + key_arn.encode()).digest()[:16]

    def wrap(self, dek: bytes, aad: bytes) -> bytes:
        return self._kms.encrypt(KeyId=self._arn, Plaintext=dek,
                                 EncryptionContext={"aegis": aad.hex()})["CiphertextBlob"]

    def unwrap(self, key_id: bytes, payload: bytes, aad: bytes) -> bytes:
        if key_id != self.key_id:
            raise UnknownKek(file_key_id=key_id, available_key_ids=(self.key_id,))
        try:
            return self._kms.decrypt(CiphertextBlob=payload, KeyId=self._arn,
                                     EncryptionContext={"aegis": aad.hex()})["Plaintext"]
        except self._kms.exceptions.InvalidCiphertextException:
            raise KeyMismatch(reason="unwrap") from None
```

**This is the whole extension story.** AWS KMS, Google Cloud KMS, Vault, an HSM, a per-tenant
key server: each is two methods, two attributes and zero changes to the core. That is why
bundled providers are out of scope — they would be dependencies, not capabilities.

### 6.1 Local KEKs

`EnvKey`, `FileKey` and `BytesKey` differ only in where the KEK comes from: base64 in an
environment variable, base64 in a file, or bytes you already hold. Each validates every
configured KEK in its constructor and fails with `ConfigurationError` at import or startup —
never in the middle of an upload. A KEK must:
- decode to exactly 32 bytes;
- appear only once across `primary` and `previous`;
- pass the entropy floor: not every byte printable ASCII, and at least 16 distinct byte values
  ([ADR-0029](decisions.md#adr-0029-local-key-sources-envkey-filekey-and-byteskey-with-an-entropy-floor)).

Rotation is then three steps:

```python
EnvKey(primary="AEGIS_KEY_V2", previous=["AEGIS_KEY_V1"])
FileKey(primary="/run/secrets/aegis_key_v2", previous=["/run/secrets/aegis_key_v1"])
# 1. add the new key   2. run `aegis rotate` or vault.rotate()   3. remove the old one
```

## 7. Memory and performance model

**Peak memory is O(chunk size), not O(file size)** — one 64 KiB plaintext segment, one 65552-byte
ciphertext chunk, a header of at most 4 169 bytes, and Python's own overhead. Nothing
accumulates. This holds for `seal`, `unseal`, `unseal_to_path`, and both readers, seekable or
not. A 512 MB run must stay under a fixed ceiling measured by `tracemalloc`, and that ceiling is
a test, not a README claim ([tests.md § 5](tests.md#5-layer-4--constant-memory-as-a-tested-invariant)).

Two rules that keep it true:

- Never `src.read()` without a size argument. Never build a `list` of chunks. Never `b"".join`
  the body.
- `seal_bytes` / `unseal_bytes` are the deliberate exceptions: the caller already holds the
  whole plaintext, so they are implemented over `BytesIO` and documented as O(n).

Throughput is bounded by AES-GCM, which is hardware-accelerated on any CPU with AES-NI or ARMv8
crypto extensions, and by chunk overhead, which at 64 KiB is negligible. The fixed cost per file
is two random draws, three HKDF derivations, one wrap or unwrap, a constant-time comparison and
two hashes. Targets, the measured baseline and the release gates are in
[performance.md](performance.md).

## 8. Concurrency

- A `Vault` is **immutable after construction** and holds no per-operation state. Local key
  sources read their keys once, in `__init__`. Sharing one `Vault` across threads is therefore
  safe, provided the `KeySource` is (the bundled ones are).
- A single `seal`/`unseal` call, and a single reader, is **not** re-entrant across threads: the
  streams belong to the caller and are consumed sequentially. One call, one thread.
- Encryption is CPU-bound. To use more cores, run whole `seal` calls in a `ThreadPoolExecutor`
  or `ProcessPoolExecutor`. There is no async API and no internal threading
  ([ADR-0007](decisions.md#adr-0007-no-async-api-in-10)). An async server reads one chunk per
  thread hop ([usage.md § 10](usage.md#10-django-and-other-web-frameworks)).

## 9. Error model

```
AegisError
├── ConfigurationError    missing env var or key file, bad encoding or length,
│                         low-entropy or duplicate KEK
├── FormatError
│   ├── NotAnAegisFile      nothing to read, or the magic does not match
│   ├── UnsupportedVersion  future version/suite → "upgrade aegis"
│   └── MalformedHeader     truncated or inconsistent header or custody record
├── UnknownKek            key_id matches no configured key, or the file's custody
│                         kind needs another kind of source
│                         "sealed with key a3f1… (local KEK); you have b7c2…"
├── UnsealFailed          "the body does not authenticate: wrong context, or corrupted data"
│   ├── KeyMismatch         the key does not match the file's commitment, or the
│   │                       custody record does not authenticate
│   └── TruncatedFile       the body ends early — proven, not guessed
└── UsageError            a float in context, CallerHeld without a key,
                          a non-blocking stream, …
```

The principle: **diagnose everything possible before touching the body, and past that point be
honest about not knowing.**

AES-GCM alone cannot distinguish a wrong key from a wrong context from a corrupted byte — all
three raise the same `InvalidTag`. Exposing `WrongContextError` would be inventing information
and would send the developer to debug the wrong thing. The header's key commitment
([ADR-0027](decisions.md#adr-0027-a-per-file-salt-drives-the-key-schedule-and-the-header-commits-to-the-key))
changes what *is* distinguishable, and three failures get classes of their own:

- `UnknownKek` — decided by comparing `key_id` against the configured keys, before any
  decryption. It answers "you are missing a key", not "your file is broken", which is the single
  most valuable disambiguation in operations.
- `KeyMismatch` — decided by the commitment, before the body. It means a wrong caller key, a
  custody record copied from another file, or a damaged header — never a wrong context.
- `TruncatedFile` — decided by the final-chunk flag, only where the reader can prove it
  ([file-format.md § 6.2](file-format.md#62-unsealing)).

Past the commitment the key is known to be right, so `UnsealFailed` on a chunk names the two
causes that remain: a wrong context, or damaged data.

Every error class carries structured attributes — for example `UnknownKek.file_key_id`,
`UnknownKek.file_custody`, `UnknownKek.available_key_ids`, `KeyMismatch.reason`
(`"unwrap"` or `"commitment"`), `UnsupportedVersion.version` — never only a formatted string, so
callers can branch without parsing messages.

`ConfigurationError` and `UsageError` should be impossible to reach in a correct integration;
both indicate a bug in the calling code, and both are raised as early as the information
allows: at construction, or before the first byte of a stream is read.

## 10. Secret hygiene

Two footguns the library closes on its own, because they are the ones that actually cause
production leaks:

1. **`__repr__` redacts key material.** `Receipt`, `Vault`, every key source and both readers
   render key bytes as `key=<redacted 32 bytes>`. Every developer logs objects; in caller-held
   mode the `Receipt` carries the only copy of the user's key. No exception message, no log
   record and no `str()` ever contains a key, a DEK, a derived key or plaintext. Enforced by a
   test that asserts secrets never appear in `repr()` or in any raised message.
2. **`unseal_to_path()` writes atomically and durably.** In streaming mode, if authentication
   fails at the last chunk, partial plaintext has already been written to the destination — and
   the low-level API cannot clean up a stream the caller owns. So the safe path is offered as
   the convenient one:
   1. write to a temporary file, mode `0600`, in the destination's directory;
   2. `fsync` it, and `os.replace` it only if `unseal` returns cleanly;
   3. `fsync` the directory on POSIX, so that the rename itself survives a crash.

   On failure the temporary file is removed and nothing survives
   ([ADR-0037](decisions.md#adr-0037-smaller-resolutions), Q21).

Also:

- **Logging** goes through `logging.getLogger("aegis")` with a `NullHandler`. The library never
  configures the host's logging and never logs a secret. `DEBUG` records may contain sizes,
  versions, the custody mode, `key_id` and chunk counts — nothing else.
- **We do not claim to zeroize memory.** Python `bytes` are immutable and the interpreter copies
  freely; "wiping" a key with `ctypes` would be theatre. Where it is cheap we keep key material
  in `bytearray` and clear it after use, but the documentation says plainly that a memory-dump
  adversary is out of scope ([security.md § 3](security.md#3-what-aegis-does-not-defend-against)).

## 11. Typing

The package ships `py.typed`. The public API is fully annotated, `mypy --strict` clean on
`aegis/` (excluding tests), and `Protocol` is used for `KeySource`. The protocol is defined over
`bytes` and `int` only, so third-party implementations need no import from us at runtime.

`bytes` versus `str` is never ambiguous in a signature: keys, DEKs, blobs, key ids and canonical
encodings are `bytes`; environment variable names are `str`; paths are `str | os.PathLike`.

## 12. The CLI

`aegis` exists so that a developer can *see* the structure before writing code — the
"understanding" half of the product goal.

| Command | Purpose |
|---|---|
| `aegis keygen` | Print a fresh 32-byte KEK, base64-encoded |
| `aegis seal` | Seal a file |
| `aegis unseal` | Open a file |
| `aegis inspect` | Show the header — version, suite, custody, `key_id`, header size — and the size-derived chunk count and plaintext size, labelled as unauthenticated. **Never decrypts** |
| `aegis rotate` | Re-wrap the DEK under the primary KEK |

Options ([ADR-0036](decisions.md#adr-0036-inspect-and-the-cli-contract)):

| Option | Meaning |
|---|---|
| `--key-env NAME` | primary KEK from an environment variable (default `AEGIS_MASTER_KEY`) |
| `--key-file PATH` | primary KEK from a file (instead of `--key-env`) |
| `--previous-env NAME`, `--previous-file PATH` | older KEKs, repeatable — for `unseal` and `rotate` |
| `seal --caller-held --key-out PATH` | caller custody; the key goes to a new file, mode `0600`, never to a stream |
| `unseal --key-in PATH` | the caller-held key, read from a file |
| `--context k=v` | a `str` value |
| `--context-int`, `--context-hex`, `--context-bool`, `--context-null` | an `int`, `bytes` (hex), `bool` (`true`/`false`) or `None` value |
| `rotate PATH --recursive [--fail-fast]` | rotate a tree; see below |

Key bytes never appear on argv or on a standard stream.

Exit codes are part of the contract, so the CLI is usable in a shell script:

| Code | Meaning |
|---:|---|
| 0 | success |
| 1 | `UnsealFailed` (including `KeyMismatch` and `TruncatedFile`) |
| 2 | `UsageError` — bad invocation |
| 3 | `FormatError` — not an Aegis file, unsupported version, malformed header |
| 4 | `UnknownKek` |
| 5 | `ConfigurationError` |

The CLI reads and writes standard streams by default, so `aegis seal < in > out` works and never
materialises a file. It never prints key material except from `keygen`, which prints only to a
TTY unless `--force` is given.

`rotate --recursive` (Q15, [ADR-0035](decisions.md#adr-0035-rotation-write-path-torn-write-journal-public-calls-recursive-runs))
works through a whole tree:
- Caller-held files, files that are not Aegis files, and external-custody files (the CLI holds no
  `KeySource`) each get one report line and do not fail the run.
- Per-file errors are reported and the run continues, and a summary ends the output.
- The exit code is `0` if nothing failed, otherwise the code of the first failure.
  `--fail-fast` stops at that failure.

## 13. The Django adapter

Planned for V2 ([ADR-0034](decisions.md#adr-0034-the-django-adapter-moves-to-v2)).
[dev/v2-django.md](dev/v2-django.md) records the decisions already taken — opaque storage names, a
per-upload default context, a lazily resolved vault, an authorized decrypting view, an async
bridge for ASGI — and the questions still open.

Until then, Django projects use the public API directly; [usage.md § 10](usage.md#10-django-and-other-web-frameworks)
shows how to store an upload and serve a download under WSGI and ASGI with constant memory.

## 14. Versioning and compatibility

| Thing | Versioning |
|---|---|
| The library | SemVer. Public API = what `aegis/__init__.py` exports (§ 2.2). |
| The file format | An independent byte. See [file-format.md § 8](file-format.md#8-changing-this-format). |
| Frozen vectors | Immutable. Changing them **is** a format change. |
| Python | 3.11+ at 1.0: every CPython that still receives security fixes ([ADR-0023](decisions.md#adr-0023-python-floor-follows-cpythons-support-window)). A drop is a minor release, announced one release ahead. |
| `cryptography` | A floor, never a ceiling pin, so security updates flow to users. |

Anything not exported from `aegis/__init__.py` is private and may change in a patch release. The
dogfood test exists to prove we believe that.

## 15. Non-goals of this architecture

- **Pluggable ciphers.** The suite byte allows a future suite; the code has no strategy pattern,
  no registry and no `algorithm=` parameter. Configurable cryptography is how users pick the weak
  option. External custody is not an exception: only *where the DEK is kept* varies; the body
  construction never does.
- **A generic streaming framework.** `stream.py` implements STREAM for one suite. It is not an
  abstraction over AEADs.
- **Backwards compatibility with anything.** There is no legacy reader and no migration path from
  another library's format ([ADR-0012](decisions.md#adr-0012-no-legacy-format-reader)).

## 16. Open questions

Collected here so they are decided deliberately rather than by whoever writes the code first.
As of 2026-10-18 every question is either decided or moved to the V2 plan.

| Q | Question | Status |
|---|---|---|
| Q1 | Chunk AAD versus rotation | resolved — ADR-0014, now ADR-0028 |
| Q2 | KEK encoding in environment variables | resolved — ADR-0015 |
| Q3 | May `context` be empty? | resolved — ADR-0020 |
| Q4 | Django contexts on unsaved instances | moved to V2 — ADR-0034 |
| Q5 | Domain separation in the AAD hashes | resolved — ADR-0019 |
| Q6 | The PyPI name | resolved — ADR-0018 |
| Q7 | `Receipt.kek_id` | resolved — ADR-0037 |
| Q8 | Rotation without `pwrite` on Windows | resolved — ADR-0035 |
| Q9 | Torn writes during rotation | resolved — ADR-0035 (option 3) |
| Q10 | No public API behind `aegis inspect` | resolved — ADR-0036 |
| Q11 | No public API behind `aegis rotate` | resolved — ADR-0035 |
| Q12 | `KeySource` and `CustodyBlock` are not exported | resolved — ADR-0026 |
| Q13 | How the CLI receives keys | resolved — ADR-0036 |
| Q14 | Context types the CLI can express | resolved — ADR-0036 |
| Q15 | `aegis rotate --recursive` over mixed directories | resolved — ADR-0035 |
| Q16 | How `SealedFileField` receives its `Vault` | moved to V2 — ADR-0034 |
| Q17 | Hypothesis example database: committed or ignored | resolved — ADR-0037 |
| Q18 | PyPI name reservation | resolved — ADR-0037; the placeholder release is an M0 action |
| Q19 | Public review scheduled after the freeze | resolved — ADR-0037; the review request is an action due now |
| Q20 | The error for a short non-Aegis file | resolved — ADR-0037 |
| Q21 | Durability of `unseal_to_path` | resolved — ADR-0037 |
| Q22 | The 2³² chunk limit | resolved — ADR-0037 |
| Q23 | When `unseal` validates `context` | resolved — ADR-0037 |
| Q24 | `aegis inspect` and unauthenticated sizes | resolved — ADR-0036 |
| Q25 | Missing negative vector for KEK custody | resolved — ADR-0028 |
| Q26 | Custody-mode mismatches | resolved — ADR-0037 |
| Q27 | Key sources chose the data key | resolved — ADR-0026, ADR-0027 |
| Q28 | The Argon2id advice could not work, and would have reused keys | resolved — ADR-0029 |
| Q29 | The custody block could not hold a KMS or HSM wrap | resolved — ADR-0028 |
| Q30 | `TruncatedFile` was unreachable for most truncations | resolved — ADR-0030 |
| Q31 | The reader accepted a second encoding of one plaintext | resolved — ADR-0030 |
| Q32 | No key commitment | resolved — ADR-0027 |
| Q33 | The only key source was an environment variable | resolved — ADR-0029 |
| Q34 | "Every mutation raises" was too strong | resolved — security.md §§ 1, 3 |
| Q35 | Rotation and copies made before it | resolved — security.md § 5.2 |
| Q36 | Short reads and partial writes were unspecified | resolved — ADR-0031 |
| Q37 | Nothing checked that a KEK was random | resolved — ADR-0029 |
| Q38 | The public API could only push | resolved — ADR-0032 |
| Q39 | Django under ASGI loads synchronous bodies into memory | moved to V2 — ADR-0034 |
| Q40 | Nothing could read at an offset | resolved — ADR-0032 |
| Q41 | The Django example bound files to their owner | moved to V2 — ADR-0034 |
| Q42 | Django storage names, URLs, authorization and migration | moved to V2 — ADR-0034 |
| Q43 | Rotation was advertised per terabyte | resolved — ADR-0035 |
| Q44 | Python 3.10 reaches end of life on 2026-10-31 | resolved — ADR-0023 |
| Q45 | Subclasses of accepted context types | resolved — ADR-0033 |
| Q46 | `seal_bytes` had nowhere to return a caller-held key | resolved — ADR-0037 |

Q10–Q26 were found on 2026-09-14 while turning the roadmap into a task list, and Q27–Q46 in the
design review of 2026-10-18. Each entry says what the documents claimed, what breaks, and how it
was decided. Offsets and sizes in Q1–Q26 refer to the 94-byte header that
[ADR-0028](decisions.md#adr-0028-a-typed-bounded-custody-record-replaces-the-fixed-80-byte-block)
replaced. The full original analysis of Q10–Q26, with every option weighed, is in this file's
history at commit `c582ee9`.

**Q1 — Chunk AAD versus rotation. *Resolved.***
`initial-spec.md` § 6 specifies `aad = sha256(header)` over all 94 bytes, but `aegis rotate`
rewrites bytes inside that header, which would invalidate every chunk in the file. The two
cannot coexist. Resolved by hashing the immutable header core only
([file-format.md § 4.3](file-format.md#43-associated-data),
[ADR-0014](decisions.md#adr-0014-chunk-aad-covers-the-immutable-header-core-only)). The
cost is losing the "convert caller-held to KEK custody by rewriting the header" bonus,
which was never a 1.0 feature. ADR-0014 accepted; its core is now the 73-byte core of ADR-0028.

**Q2 — How is a KEK encoded inside an environment variable? *Resolved.***
`initial-spec.md` requires "exactly 32 bytes", but an environment variable holds text.
Decision: strict standard base64
with padding (44 characters), everything else rejected with a `ConfigurationError` that shows
how to generate one; plus an `aegis keygen` command so the developer never has to invent the
incantation. Hex is rejected deliberately — one canonical form
([ADR-0015](decisions.md#adr-0015-keks-in-environment-variables-are-base64), accepted). Key files
use the same encoding ([ADR-0029](decisions.md#adr-0029-local-key-sources-envkey-filekey-and-byteskey-with-an-entropy-floor)).

**Q3 — May `context` be empty? *Resolved.*** `initial-spec.md` § 5.2 says context is
mandatory, but the § 5.1 example calls `vault.seal(src, dst)` with none. Decision: the
parameter is required; `context={}` is legal and canonicalizes to the empty byte string;
`context=None` raises `UsageError`. Making people type `{}` keeps the absence deliberate and
visible in a code review
([ADR-0020](decisions.md#adr-0020-context-is-required-but-may-be-empty)).

**Q4 — Django contexts and unsaved instances. *Moved to V2.*** A callable referencing `inst.pk`
cannot work before the first `INSERT`. Options: document it as the caller's responsibility
(cheap, sharp edge), or raise a specific `UsageError` when the callable touches an unset field
(kind, but requires introspection we may not be able to do reliably). The V2 plan removes the
problem for the default context, which binds a per-upload identifier that exists before the
`INSERT` ([dev/v2-django.md](dev/v2-django.md), decision D2).

**Q5 — Domain separation in the AAD hashes. *Resolved.*** The AAD is
`SHA256(b"aegis-hdr-v1\x00" ‖ core) ‖ SHA256(b"aegis-ctx-v1\x00" ‖ context)` instead of plain
SHA-256. It costs nothing and forecloses cross-protocol collisions; the `\x00` terminator
matches the `kek_id` label
([ADR-0019](decisions.md#adr-0019-domain-separated-aad-hashes)).

**Q6 — Is `aegis` available on PyPI? *Resolved.*** It is not. The PyPI distribution is
`aegis-voynan`; the import package, the CLI and every string in the file format stay
`aegis` ([ADR-0018](decisions.md#adr-0018-distribute-as-aegis-voynan-import-as-aegis)).

**Q7 — Should `Receipt` expose the `kek_id`? *Resolved.*** Useful for operations (recording
which key sealed which row), and it is public metadata anyway. `Receipt.key_id` ships in 1.0:
the 16-byte id of the key that wrapped the DEK, `None` for caller-held files
([ADR-0037](decisions.md#adr-0037-smaller-resolutions)).

**Q8 — Rotation has no `pwrite` on Windows. *Resolved.*** The rotation design wrote the custody
block "as a single `pwrite`". `os.pwrite` is POSIX-only and does not exist on Windows, which is
in the CI matrix. Decision, as proposed: use `os.pwrite` where it exists; elsewhere open the file
`r+b`, seek to the record and issue one `write`; then `fsync` in both cases. Neither is atomic
against power loss, which is Q9
([ADR-0035](decisions.md#adr-0035-rotation-write-path-torn-write-journal-public-calls-recursive-runs)).

**Q9 — A torn write during rotation can make a file permanently unreadable. *Resolved —
option 3.*** The documents claimed that "an interrupted rotation leaves a file that still opens
with the old KEK". That holds when the **process** dies: a single small `write` either reaches
the page cache or it does not. It does **not** hold for **power loss or a kernel crash**
mid-write. The storage layer does not guarantee that a sector is written all-or-nothing, and
filesystems without data journaling (ext4 `data=ordered`, APFS, NTFS) do not add that guarantee.
The result can be a custody block that is half old, half new:

- `kek_id` may name either KEK, but the rest of the block no longer matches it.
- The unwrap fails under **both** KEKs, and the GCM tag cannot tell which bytes are right.
- The DEK is lost, so the file is lost. The body is intact but undecryptable.

The window is small (one sector, milliseconds) but it is repeated once per file across a
whole bucket. A library whose selling point is key rotation must not turn a power cut during
rotation into data loss. Options:

1. **Accept and document.** Say that rotation is crash-safe against process death only, and
   tell operators to back up first. Cheapest, and it moves the risk to the user.
2. **Rewrite the whole file.** Write a temporary copy with the new custody block, `fsync`,
   `os.replace`. Atomic, but it reads and writes the whole body.
3. **Journal the old block (recommended).** Before overwriting, write a sidecar
   `<file>.aegis-rotate` holding the old record and a SHA-256 of it. `fsync` the sidecar and its
   directory. Then write the new record, `fsync` the file, and delete the sidecar. Rotation
   checks for leftover sidecars before doing anything else, keeps whichever record (on disk or
   journaled) opens under a configured key, and restores the other if needed. Cost: two extra
   `fsync`s and one small file per rotated file, no format change.
4. **Redundant custody block in the format.** Store two copies and write them one at a time.
   Robust, but it is a format change, and readers would have to accept a record that does not
   authenticate.

Decision: option 3, specified in
[ADR-0035](decisions.md#adr-0035-rotation-write-path-torn-write-journal-public-calls-recursive-runs).
Object stores (S3, GCS, Azure Blob) cannot overwrite part of an object; there, rotation streams a
new copy with the body bytes copied verbatim (`vault.rewrap`), and object replacement is atomic,
so Q9 does not arise. [usage.md § 8](usage.md#8-rotating-your-master-key) states which storage
gets in-place rotation.

**Q10 — No public API behind `aegis inspect`. *Resolved.*** The dogfood rule lets the CLI import
only what `aegis/__init__.py` exports, and none of the original exports read a header without
decrypting. Applications need the same thing: finding which key sealed a stored blob, without
holding the key. Decision: a public `aegis.inspect(src) -> FileInfo` that never takes a key
([ADR-0036](decisions.md#adr-0036-inspect-and-the-cli-contract)).

**Q11 — No public API behind `aegis rotate`. *Resolved.*** Same rule, same problem: the CLI
command must call something exported, and applications that walk their own storage — a
management command, a background job — need it too. Decision: `vault.rotate(path)` in place and
`vault.rewrap(src, dst)` for object stores, both returning a `RotationResult`; recursion and
reporting stay in the CLI
([ADR-0035](decisions.md#adr-0035-rotation-write-path-torn-write-journal-public-calls-recursive-runs)).

**Q12 — `KeySource` and `CustodyBlock` are not exported. *Resolved.*** § 6 promised that a KMS,
Vault or HSM integration is "two functions and zero changes to the core", and § 11 that
third-party implementations "need no import from us at runtime". But `provision()` returned a
`CustodyBlock` and `recover()` received one, neither was exported, and dataclasses are typed
nominally. Decision: the protocol is redefined over plain bytes, `CustodyBlock` no longer exists,
and `KeySource` is exported
([ADR-0026](decisions.md#adr-0026-the-library-draws-every-data-key-key-sources-only-wrap-and-unwrap)).

**Q13 — How the CLI receives keys. *Resolved.*** The CLI ran `aegis seal in.pdf out.aegis
--context user_id=42` with no key argument, and nothing specified:

- which environment variable `seal`, `unseal` and `rotate` read — `AEGIS_MASTER_KEY` appeared
  only in examples;
- how `rotate` receives the primary and previous KEKs;
- how caller-held custody works from a shell. `seal` must hand the generated key to the user and
  `unseal` must take it back, and both obvious channels are wrong: argv is visible in `ps` and in
  shell history, and stdout already carries the ciphertext when piping.

Decision: `--key-env` / `--key-file`, repeatable `--previous-env` / `--previous-file`, and for
caller-held custody `seal --caller-held --key-out PATH` (mode `0600`, refused if it exists) and
`unseal --key-in PATH` (§ 12, [ADR-0036](decisions.md#adr-0036-inspect-and-the-cli-contract)).

**Q14 — Context types the CLI can express. *Resolved.*** `--context k=v` produced a `str` and
`--context-int k=v` an `int`. The library also accepts `bytes`, `bool` and `None`, and the type
is part of the canonical encoding, so a file sealed with `{"tenant": b"\x01", "archived": False}`
could not be opened from the shell at all — during an incident, exactly when an operator reaches
for the CLI. Decision: `--context-hex`, `--context-bool` and `--context-null` as well
([ADR-0036](decisions.md#adr-0036-inspect-and-the-cli-contract)).

**Q15 — `aegis rotate --recursive` over mixed directories. *Resolved.*** Real directories hold
more than KEK-custody Aegis files: caller-held files, thumbnails and partial uploads, files under
a key that is not configured, and runs where some files fail. Aborting at the first stray file
makes rotating a real bucket impractical; skipping silently makes an `UnknownKek` easy to miss.
Decision, as proposed, with external-custody files added to the skipped set (§ 12,
[ADR-0035](decisions.md#adr-0035-rotation-write-path-torn-write-journal-public-calls-recursive-runs)).

**Q16 — How `SealedFileField` receives its `Vault`. *Moved to V2.*** The field took `upload_to`
and `context` and nothing else — no vault, no key source, no setting name — so it had nothing to
seal with. The V2 plan takes the proposal: a dotted path in a `vault=` argument overriding an
`AEGIS_VAULT` setting, resolved lazily so `manage.py migrate` runs without key material
([dev/v2-django.md](dev/v2-django.md), decision D3).

**Q17 — Hypothesis example database: committed or ignored? *Resolved.*** tests.md committed the
database while roadmap.md M0 ignored `.hypothesis/`. The database is also a poor home for
regressions: it holds whatever examples Hypothesis kept on one machine, in a format that may
change between versions, and a reviewer cannot read it. Decision: ignore `.hypothesis/`, and pin
every failure found as an explicit `@example(...)` on the property it broke
([ADR-0037](decisions.md#adr-0037-smaller-resolutions)).

**Q18 — PyPI name reservation. *Resolved.*** PyPI's documentation says a pending publisher "does
not create a project or reserve a project's name until it is actually used to publish". Decision:
configure the pending publisher, then publish a `0.0.0` placeholder through `release.yml` at M0 —
which also proves the publishing path at M0 instead of at M9
([ADR-0037](decisions.md#adr-0037-smaller-resolutions)).

**Q19 — Public review scheduled after the freeze. *Resolved.*** The public review was requested
at M8, after the M4 freeze, so a finding touching bytes on disk would have left two bad options:
ship 1.0 with a known format flaw, or regenerate frozen vectors. Decision: request review of
file-format.md now, after the 2026-10-18 revision; request review of `stream.py` and
`envelope.py` when M2 closes; make "format review feedback triaged" part of the M4 gate; keep M8
as the final pass ([ADR-0037](decisions.md#adr-0037-smaller-resolutions)).

**Q20 — The error for a short non-Aegis file. *Resolved.*** Reading the whole header before
comparing the magic would make an empty file or a small thumbnail report `MalformedHeader`
instead of `NotAnAegisFile`. Decision: errors follow the bytes that arrive — an empty stream or a
magic mismatch is `NotAnAegisFile`, a matching prefix that ends early is `MalformedHeader`, and
version and suite are checked before the rest of the header is required
([file-format.md § 6.2](file-format.md#62-unsealing), [ADR-0037](decisions.md#adr-0037-smaller-resolutions)).

**Q21 — Durability of `unseal_to_path`. *Resolved.*** On POSIX the rename is a change to the
directory, and it is not durable until the directory is synced; a power loss could undo it after
the caller has deleted the sealed original. Decision: `fsync` the file, `os.replace`, then
`fsync` the directory on POSIX; on Windows, document that the rename's durability is the
filesystem's (§ 10, [ADR-0037](decisions.md#adr-0037-smaller-resolutions)).

**Q22 — The 2³² chunk limit. *Resolved.*** The writer's MUST was untestable — 2³² chunks is
256 TiB — and the reader had no rule, so `counter.to_bytes(4, "big")` would raise
`OverflowError` outside the error model. Decision: one `MAX_CHUNKS` constant in `stream.py`,
checked in both directions, lowered in tests through a parameter
([file-format.md § 7.3](file-format.md#73-limits), [ADR-0037](decisions.md#adr-0037-smaller-resolutions)).

**Q23 — When `unseal` validates `context`. *Resolved.*** With the original order a `float` in
`context` could surface as `UnknownKek` and consume header bytes of a non-seekable stream before
reporting a programming error. Decision: canonicalize `context` and check the call's custody
arguments before reading a byte, in every unseal entry point (§ 5.2,
[ADR-0037](decisions.md#adr-0037-smaller-resolutions)).

**Q24 — `aegis inspect` and unauthenticated sizes. *Resolved.*** `inspect` never decrypts, so its
chunk count and plaintext size can only come from the file size, which nothing authenticates.
Decision: label them as size-derived, flag impossible sizes, and count a non-seekable stream to
its end without decrypting ([ADR-0036](decisions.md#adr-0036-inspect-and-the-cli-contract)).

**Q25 — Missing negative vector for KEK custody. *Resolved.*** The frozen vectors lacked "KEK
custody with an all-zero custody block", the header a buggy writer is likeliest to produce.
Decision: the new custody rules reject that header three ways (zero `key_id`, wrong
`payload_len`, wrong `custody_len`), and the negative vectors carry one case per rule
([ADR-0028](decisions.md#adr-0028-a-typed-bounded-custody-record-replaces-the-fixed-80-byte-block)).

**Q26 — Custody-mode mismatches. *Resolved.*** An `EnvKey` vault opening a caller-held file, a
`CallerHeld` vault opening a KEK-custody file, and `key=` passed to an `EnvKey` vault had no
specified outcome, and the obvious implementation misled in all three. Decision: `UsageError`
for those three (and for `CallerHeld()` without `key=`), raised before any decryption;
`UnknownKek` with `file_custody` set when a local-KEK file meets a `KeySource` or the reverse
([ADR-0037](decisions.md#adr-0037-smaller-resolutions)).

**Q27 — Key sources chose the data key. *Resolved.*** `provision()` returned the DEK, and nonce
uniqueness rested on that DEK being fresh, with a 56-bit random nonce prefix behind it. A source
that caches data keys — a common way to save KMS calls — would reuse DEKs. At a million files the
nonce-collision probability would reach about one in 144 000, far above the 2⁻³² NIST SP 800-38D
sets for random nonces. In GCM a collision leaks two plaintexts' XOR and the authentication key.
Decision: the library draws every DEK and sources only wrap and unwrap
([ADR-0026](decisions.md#adr-0026-the-library-draws-every-data-key-key-sources-only-wrap-and-unwrap)).
The body key and nonce prefix are also derived per file from a 256-bit salt, so even a repeated
DEK cannot repeat a nonce
([ADR-0027](decisions.md#adr-0027-a-per-file-salt-drives-the-key-schedule-and-the-header-commits-to-the-key)).

**Q28 — The Argon2id advice could not work, and would have reused keys. *Resolved.*** usage.md
told caller-held users to derive a key with Argon2id and "pass it as the caller key". `seal`
generated the caller key, so there was nowhere to pass it. Had `seal` accepted one, a single
password-derived key would have encrypted every file directly. Decision: a derived key is a KEK —
`BytesKey(argon2id(...))` — that wraps a fresh DEK per file
([ADR-0029](decisions.md#adr-0029-local-key-sources-envkey-filekey-and-byteskey-with-an-entropy-floor)).

**Q29 — The custody block could not hold a KMS or HSM wrap. *Resolved.*** The 48-byte
`wrapped_dek` field held exactly a 32-byte key and a tag. An AES-GCM wrap with a random IV needs
at least 60 bytes before any key identifier; KMS blobs carry identifiers; RSA wraps are 256–512
bytes. No header field named the custody kind. "Implement `KeySource` over your KMS" could only
be done by re-implementing Aegis' own wrap. Decision: a typed, bounded, length-declared custody
record of up to 4 096 bytes after a fixed 73-byte core
([ADR-0028](decisions.md#adr-0028-a-typed-bounded-custody-record-replaces-the-fixed-80-byte-block)).

**Q30 — `TruncatedFile` was unreachable for most truncations. *Resolved.*** The reader decrypted
the final block only as final, so the rule "a stream that ended after a chunk marked last=False"
never ran. A cut at a chunk boundary or inside a chunk raised `UnsealFailed`, while tests.md and
security.md promised `TruncatedFile` at any offset. Decision: a full-size final block that fails
is retried as non-final, and if it authenticates the cut was at a boundary — `TruncatedFile`. A
remainder of 0–15 bytes is `TruncatedFile`. A cut inside a chunk is `UnsealFailed`, and the
documents say so
([ADR-0030](decisions.md#adr-0030-how-a-reader-classifies-truncation-and-when-a-final-chunk-may-be-empty)).

**Q31 — The reader accepted a second encoding of one plaintext. *Resolved.*** A full final chunk
can also be written as a full non-final chunk followed by an empty final one. The writer never
did, but the reader accepted it — two byte sequences for one plaintext, and room for two
implementations to disagree. Decision: an empty final chunk is valid only when the whole
plaintext is empty, age's rule; otherwise `UnsealFailed`
([ADR-0030](decisions.md#adr-0030-how-a-reader-classifies-truncation-and-when-a-final-chunk-may-be-empty)).

**Q32 — No key commitment. *Resolved.*** AES-GCM lets one ciphertext decrypt validly under two
keys (Albertini et al., USENIX Security 2022). The risk is low while Aegis generates every key,
but a commitment could not be added after M4 without format v2. Decision: a 32-byte HKDF
commitment in the header, checked before the body — the pattern of the AWS Encryption SDK's
committing suites. It also makes a wrong key distinguishable, as `KeyMismatch`
([ADR-0027](decisions.md#adr-0027-a-per-file-salt-drives-the-key-schedule-and-the-header-commits-to-the-key)).

**Q33 — The only key source was an environment variable. *Resolved.*** Environment variables are
inherited by child processes, and they are readable through `/proc/<pid>/environ` — which, per
proc(5), keeps the initial environment even after `unsetenv`. A path-traversal bug therefore
yields the KEK without code execution. Decision: `FileKey` for mounted secrets and `BytesKey` for
secret-manager SDKs, KDFs and tests, beside `EnvKey`. security.md § 5.1 ranks the options
([ADR-0029](decisions.md#adr-0029-local-key-sources-envkey-filekey-and-byteskey-with-an-entropy-floor)).

**Q34 — "Every mutation raises" was too strong. *Resolved.*** An attacker with write access cannot
forge or alter content. They can still replace a blob with another genuine blob sealed under the
same context: an older version of the same document (rollback), or a sibling file when the context
binds only to the owner — which the Django example did. Decision: security.md §§ 1 and 3 state it
as a non-guarantee, with the remedy: put a per-upload or per-version identifier in the context.

**Q35 — Rotation and copies made before it. *Resolved.*** Rotation re-wraps headers, but a backup,
an object version or a replica made before rotation still opens with the old KEK. It yields the
DEK, which opens the current body too, because the DEK never changes. Decision: security.md § 5.2
and usage.md § 8 say so, and point to purging old copies and re-sealing as the remedy after a
suspected KEK leak.

**Q36 — Short reads and partial writes were unspecified. *Resolved.*** The API accepts sockets and
pipes, whose reads return fewer bytes than asked. A writer that treated each read as a segment
would produce files that never open, and `BytesIO`-only tests would not notice. Decision: segments
are byte counts, and writes loop until complete. Non-blocking and text streams raise `UsageError`,
and a short-read source joins the property tests
([ADR-0031](decisions.md#adr-0031-the-stream-io-contract-full-segments-full-writes-blocking-streams)).

**Q37 — Nothing checked that a KEK was random. *Resolved.*** A base64-encoded 32-character
passphrase passed every check. Decision: reject KEKs whose bytes are all printable ASCII or that
have fewer than 16 distinct byte values. The false-positive rate for a key from a CSPRNG is below
2 × 10⁻¹⁴
([ADR-0029](decisions.md#adr-0029-local-key-sources-envkey-filekey-and-byteskey-with-an-entropy-floor)).

**Q38 — The public API could only push. *Resolved.*** `seal(src, dst)` writes into a stream, while
Django storage, `FileResponse`, boto3's `upload_fileobj` and Starlette read from one. Without a
pull form, adapters needed a thread and a pipe or a temporary copy, and the dogfood rule forbade
`stream.py`'s iterators. Decision: the `Vault.sealed()` and `Vault.unsealed()` readers
([ADR-0032](decisions.md#adr-0032-pull-style-readers-vaultsealed-and-vaultunsealed-seekable-when-the-source-is)).

**Q39 — Django under ASGI loads synchronous bodies into memory. *Moved to V2.*** Django's
documentation and its source (5.2, 6.0) agree: a synchronous iterator served under ASGI "must be
fully-consumed" (`sync_to_async(list)`). `FileResponse` over a 10 GB decrypting reader would hold
10 GB. Decision: the V2 adapter ships an async bridge, and usage.md § 10 documents it for 1.0
users ([ADR-0034](decisions.md#adr-0034-the-django-adapter-moves-to-v2)).

**Q40 — Nothing could read at an offset. *Resolved.*** The format allows random access, but the
API was forward-only, so HTTP Range, media seeking and libraries that seek needed whole-file
decryption. Decision: `unsealed()` is seekable when its source is, and authenticates the final
chunk when it opens
([ADR-0032](decisions.md#adr-0032-pull-style-readers-vaultsealed-and-vaultunsealed-seekable-when-the-source-is)).

**Q41 — The Django example bound files to their owner. *Moved to V2.*** `context=lambda inst:
{"user_id": inst.owner_id}` is the pattern usage.md § 4.1 calls a trap, and it lets two files of
one user be swapped (Q34). Decision for V2: bind each upload — model, field and a per-file uuid.
The usage.md examples are fixed now
([ADR-0034](decisions.md#adr-0034-the-django-adapter-moves-to-v2)).

**Q42 — Django storage names, URLs, authorization and migration. *Moved to V2.*** `upload_to`
keeps original filenames in storage keys, `FieldFile.url` would point at ciphertext, a decrypting
view needs an authorization hook, and existing plaintext files need a migration path. Decisions
and open points are in [dev/v2-django.md](dev/v2-django.md).

**Q43 — Rotation was advertised per terabyte. *Resolved.*** "A 10 TB bucket rotates in minutes"
ignored two things: the cost is per file, one or more `fsync`s each, and object stores rewrite
whole objects. P7's "write exactly 80 bytes" also conflicted with the Q9 journal. Decision: the
claims are restated per file, `rewrap` covers object stores, and P7 counts the target file and
the journal separately
([ADR-0035](decisions.md#adr-0035-rotation-write-path-torn-write-journal-public-calls-recursive-runs)).

**Q44 — Python 3.10 reaches end of life on 2026-10-31. *Resolved.*** A security library should not
advertise an interpreter that stops receiving security fixes before its first release. Decision:
floor 3.11, matrix 3.11–3.14
([ADR-0023](decisions.md#adr-0023-python-floor-follows-cpythons-support-window), accepted).

**Q45 — Subclasses of accepted context types. *Resolved.*** `IntEnum`, `StrEnum` and Django's
`SafeString` pass `isinstance` checks although the spec rejects `Enum`, and a subclass can change
how it encodes. Decision: exact types only
([ADR-0033](decisions.md#adr-0033-context-values-must-have-an-exactly-accepted-type)).

**Q46 — `seal_bytes` had nowhere to return a caller-held key. *Resolved.*** It returns only the
blob, so on a `CallerHeld()` vault the key would be lost and the blob unopenable. Decision:
`UsageError` there; caller-held sealing goes through `seal` or `sealed`, whose `Receipt` carries
the key ([ADR-0037](decisions.md#adr-0037-smaller-resolutions)).
