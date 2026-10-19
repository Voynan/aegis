# Aegis file format v1 — normative specification

This document defines the `.aegis` container, byte for byte. It is the one artifact in the
project that **cannot change**. Code gets rewritten; a user's file has to open years from
now.

Anything here marked **MUST** / **MUST NOT** is enforced by the reader and covered by a test.
Where this document departs from [`initial-spec.md`](initial-spec.md), the departure is boxed
and justified.

> **Revision of 2026-10-18 (before the freeze).** The design review of that date reshaped the
> header and the key schedule ([ADR-0026](decisions.md#adr-0026-the-library-draws-every-data-key-key-sources-only-wrap-and-unwrap)
> to [ADR-0033](decisions.md#adr-0033-context-values-must-have-an-exactly-accepted-type)). No file
> has ever been written in the earlier 94-byte layout, so the version byte stays `0x01`. From the
> M4 freeze on, every change is a new version (§ 8).

---

## 1. Overview

```
┌─ HEADER CORE — 73 bytes, immutable ───────────────────────────────┐
│  magic          4 B   "AEG\x00"                                   │
│  version        1 B   0x01                                        │
│  suite          1 B   0x01 = AES-256-GCM / HKDF-SHA256 / STREAM   │
│  custody        1 B   0x00 caller-held · 0x01 local · 0x02 extern │
│  salt          32 B   random per file                             │
│  commitment    32 B   key commitment                              │
│  custody_len    2 B   length of the custody record                │
├─ CUSTODY RECORD — custody_len bytes, rewritten by rotation ───────┤
│  key_id        16 B   which key wrapped the DEK                   │
│  payload_len    2 B                                               │
│  payload        …     the wrapped DEK                             │
│  padding        …     zeros                                       │
└───────────────────────────────────────────────────────────────────┘
┌─ CHUNKS — N ≥ 1 ──────────────────────────────────────────────────┐
│  [ up to 65536 B plaintext, encrypted ] ‖ [ 16 B GCM tag ]        │
│  nonce = nonce_prefix(7) ‖ counter_be32(4) ‖ last_flag(1)         │
│  aad   = SHA256(L_hdr ‖ core) ‖ SHA256(L_ctx ‖ context)           │
└───────────────────────────────────────────────────────────────────┘
```

All multi-byte integers are **big-endian**. There is no alignment requirement. The format is
not self-delimiting: the container ends where the file ends.

## 2. Header

### 2.1 The core

| Offset | Size | Field | Contents |
|---:|---:|---|---|
| 0 | 4 | `magic` | `41 45 47 00` — ASCII `AEG` followed by `0x00` |
| 4 | 1 | `version` | `0x01` |
| 5 | 1 | `suite` | `0x01` |
| 6 | 1 | `custody` | `0x00`, `0x01` or `0x02` (§ 2.4) |
| 7 | 32 | `salt` | 32 random bytes, fresh for every file |
| 39 | 32 | `commitment` | key commitment (§ 3.2) |
| 71 | 2 | `custody_len` | length of the custody record, `u16` |
| 73 | `custody_len` | custody record | § 2.5 |
| 73 + `custody_len` | | | first chunk begins |

`header_core` means bytes 0–72. They never change after sealing: rotation rewrites only the
custody record, and the core is inside the associated data of every chunk (§ 4.3).

### 2.2 `suite`

`suite` names the complete cryptographic configuration as one byte. `0x01` means, and will
always mean:

- AEAD: AES-256-GCM (96-bit nonce, 128-bit tag)
- Construction: STREAM — 65 536-byte segments, 32-bit counter, final-segment flag
- Per-file key schedule: HKDF-SHA256 from the DEK and a 256-bit salt, producing the body key, the
  nonce prefix and the key commitment
- Local DEK wrap: AES-256-GCM under HKDF-SHA256 of the KEK and the salt
- Hashes: SHA-256

A different value for any of those is a different suite byte, never a redefinition of `0x01`.
Readers **MUST** reject unknown suites with `UnsupportedVersion`.

### 2.3 `version` and forward compatibility

Readers **MUST** check `magic`, `version` and `suite` as soon as their bytes arrive, before
requiring any other byte (§ 6.2). A future version whose header is shorter, longer or shaped
differently therefore fails as `UnsupportedVersion`, never as a parse error.

### 2.4 `custody`

| Value | Mode | `custody_len` | Record |
|---:|---|---|---|
| `0x00` | **caller-held** — the caller keeps the DEK (§ 3.5) | exactly `0` | none |
| `0x01` | **local KEK** — Aegis wraps the DEK under the caller's KEK (§ 3.3) | exactly `66` | `payload_len = 48` |
| `0x02` | **external** — a key source wraps the DEK: a KMS, an HSM, Vault Transit (§ 3.4) | `19` to `4096` | `1 ≤ payload_len ≤ custody_len − 18`; payload opaque to the format |

Any other value **MUST** be rejected with `MalformedHeader`, and so must a `custody_len` outside
its row.

### 2.5 The custody record

| Offset in the record | Size | Field | Contents |
|---:|---:|---|---|
| 0 | 16 | `key_id` | which key wrapped the DEK; **MUST NOT** be all zeros |
| 16 | 2 | `payload_len` | `u16` |
| 18 | `payload_len` | `payload` | the wrapped DEK |
| 18 + `payload_len` | the rest | padding | **MUST** be all zeros |

A reader **MUST** reject with `MalformedHeader` a record that breaks any rule of § 2.4 or of this
table. It is the only mutable region of the file: rotation rewrites it with a record of the same
length, at the same offset.

Exact lengths and zero padding make the format canonical: one plaintext, one key, one context
and fixed randomness produce exactly one byte sequence, and there is no slack in which to hide
data. An all-zero `key_id` is what a writer produces when it assembles a header before filling
in the wrap; rejecting it catches that bug in any implementation.

## 3. Key hierarchy

```
KEK, or a key in your KMS ──wraps──▶ DEK (32 B, random per file, drawn by Aegis)
                                        │
                              HKDF-SHA256(DEK, salt)
                     ┌──────────────────┼──────────────────┐
                 body_key          nonce_prefix        commitment
              (32 B, secret)      (7 B, secret)    (32 B, in the header)
```

The KEK never encrypts file data; it only wraps a DEK. The DEK does not encrypt file data
directly either; it only seeds the per-file key schedule.

### 3.1 The data key

The DEK is 32 bytes drawn with `os.urandom` for every seal, by the library. No key source,
bundled or third-party, generates or chooses it
([ADR-0026](decisions.md#adr-0026-the-library-draws-every-data-key-key-sources-only-wrap-and-unwrap)).

### 3.2 Per-file key schedule and commitment

```
body_key     = HKDF-SHA256(ikm=DEK, salt=salt, info=b"aegis-body-key-v1",     length=32)
nonce_prefix = HKDF-SHA256(ikm=DEK, salt=salt, info=b"aegis-nonce-prefix-v1", length=7)
commitment   = HKDF-SHA256(ikm=DEK, salt=salt, info=b"aegis-commitment-v1",   length=32)
```

The three derivations share one HKDF-Extract; computing it once and expanding three times is
equivalent.

A reader **MUST** recompute `commitment` from the DEK it holds and compare it with the header's,
in constant time, **before decrypting any chunk**. A mismatch raises `KeyMismatch`.

What this buys
([ADR-0027](decisions.md#adr-0027-a-per-file-salt-drives-the-key-schedule-and-the-header-commits-to-the-key)):

- **Nonce uniqueness does not depend on the DEK being fresh.** Two files share a body key and a
  nonce prefix only if they share both DEK and salt; the salt alone has a birthday bound of 2¹²⁸.
- **Key commitment.** A header opens under exactly one DEK: two DEKs with the same commitment
  would be an HMAC-SHA256 collision. AES-GCM alone does not have this property.
- **A precise error.** A wrong key is detected before the body, so it is reported as a wrong key.

The construction follows established formats: age derives its payload key with HKDF from a
random nonce, Tink's AES-GCM-HKDF streaming derives a per-ciphertext key from a random salt, and
the AWS Encryption SDK's committing suites use a 256-bit random salt and store a 32-byte key
commitment in the header.

> **Change from `initial-spec.md` § 6.** The spec encrypted the body directly under the DEK, with
> a random 7-byte nonce prefix stored in the header, and had no key commitment. Nonce uniqueness
> then rested on every key source returning a fresh DEK, and a ciphertext could be built to open
> under two keys. See [ADR-0026](decisions.md#adr-0026-the-library-draws-every-data-key-key-sources-only-wrap-and-unwrap)
> and [ADR-0027](decisions.md#adr-0027-a-per-file-salt-drives-the-key-schedule-and-the-header-commits-to-the-key).

### 3.3 Local-KEK custody (`custody = 0x01`)

```
kek_id       = SHA256(b"aegis-kek-id\x00" ‖ KEK)[:16]
wrapping_key = HKDF-SHA256(ikm=KEK, salt=salt, info=b"aegis-dek-wrap-v1", length=32)
custody_aad  = SHA256(b"aegis-custody-v1\x00" ‖ header_core)
wrapped_dek  = AES-256-GCM(wrapping_key).encrypt(
                   nonce = b"\x00" * 12,               # safe: see below
                   data  = DEK,
                   aad   = custody_aad ‖ kek_id)
record       = kek_id ‖ u16be(48) ‖ wrapped_dek          # 66 bytes
```

`kek_id` is derived, never configured
([ADR-0011](decisions.md#adr-0011-kek_id-is-derived-never-configured)). A reader finds the
matching KEK among the configured ones, and fails with `UnknownKek` before attempting any
decryption if there is none. It reveals *which* KEK sealed a file, never anything about the
content.

**Why an all-zero nonce is safe here.** The GCM requirement is that a key and nonce pair never
encrypts two different inputs. `wrapping_key` is unique to one KEK and one file, because the
salt is 256 random bits. Within a file, every wrap under a given KEK encrypts the same DEK with
the same associated data, since the core never changes. Re-wrapping — rotating back to an
earlier KEK, say — therefore reproduces identical bytes rather than reusing a nonce on new
input. There is no birthday bound on how many files one KEK may protect beyond the salt's.

The associated data binds the record to this exact core — version, suite, custody mode, salt,
commitment, record length — and to its own key id. A record transplanted into another header
fails to unwrap.

### 3.4 External custody (`custody = 0x02`)

```
custody_aad = SHA256(b"aegis-custody-v1\x00" ‖ header_core)
payload     = source.wrap(DEK, custody_aad)          # 1 … source.capacity bytes
record      = source.key_id ‖ u16be(len(payload)) ‖ payload ‖ zeros(source.capacity − len(payload))
custody_len = 18 + source.capacity
```

The payload's format belongs to the key source: a KMS ciphertext blob, an RSA-OAEP wrap, a Vault
Transit token. Sources **SHOULD** bind `custody_aad` when their backend can — as an AWS KMS
encryption context, Google Cloud KMS additional authenticated data, or Vault Transit associated
data.

A reader passes `key_id`, the payload without its padding, and `custody_aad` to
`source.unwrap`, which raises `UnknownKek` for a key it does not manage and `KeyMismatch` for a
payload that does not authenticate. The reader **MUST** check that the result is 32 bytes and
that it passes the commitment check of § 3.2. That check detects a wrong or transplanted DEK
whether or not the source binds the associated data.

### 3.5 Caller-held custody (`custody = 0x00`)

There is no record. Aegis returns the DEK in the `Receipt` and persists nothing. The caller's key
**is** the DEK: 32 bytes of high-entropy material produced by `os.urandom`, not a passphrase (see
[usage.md § 5.4](usage.md#54-password-derived-keys) for password-derived keys).

Losing that key means losing the file. There is no recovery path, by design. A wrong key fails
the commitment check and raises `KeyMismatch`, not a failure on the body.

## 4. Chunks

### 4.1 Framing

The plaintext is split into segments of exactly **65536 bytes**, except the last, which holds
1–65536 bytes — or 0 bytes if and only if the plaintext is empty.

```
number_of_chunks = max(1, ceil(len(plaintext) / 65536))
```

> **Spec addition (not stated in `initial-spec.md`).** A zero-length plaintext produces **one**
> chunk containing 0 bytes of ciphertext and a 16-byte tag. Without this rule an empty file
> would be a bare header, which is byte-identical to a maliciously truncated file and would make
> "header only" a valid container. `N ≥ 1` always
> ([ADR-0016](decisions.md#adr-0016-a-zero-length-plaintext-still-produces-one-chunk)).

Each chunk on disk is `len(segment) + 16` bytes: the AES-GCM ciphertext, the same length as the
plaintext segment, followed by the 16-byte tag. Non-final chunks are therefore always exactly
65552 bytes.

A plaintext whose length is an exact multiple of 65536 ends with a *full* final chunk. No empty
trailing chunk is appended, and a reader **MUST** reject one (§ 6.2).

Segment boundaries are byte counts. They never depend on how many bytes a single `read()` of the
source happened to return
([ADR-0031](decisions.md#adr-0031-the-stream-io-contract-full-segments-full-writes-blocking-streams)).

### 4.2 Nonce

```
nonce = nonce_prefix (7 B) ‖ counter (4 B, big-endian) ‖ last_flag (1 B)
        └─ derived, § 3.2 ┘  └─ 0, 1, 2, … ─┘            └ 0x00 or 0x01 ┘
```

96 bits in total, as AES-GCM requires. `counter` starts at `0` for the first chunk.
`last_flag` is `0x01` for the final chunk and `0x00` for every other chunk. This is the segment
nonce layout of Tink's AES-GCM-HKDF streaming.

`nonce_prefix` is derived per file and never stored. Nonce uniqueness rests on the per-file body
key: two files can share a key and a prefix only by sharing both DEK and salt.

The counter is what makes chunk reordering and duplication detectable: chunk *i* only
authenticates at position *i*.

The `last_flag` is what makes truncation detectable. Without it, chunked streaming AEAD is
trivially truncatable — any prefix of the chunk sequence is a valid shorter file.

### 4.3 Associated data

Every chunk is encrypted with the same 64-byte associated data:

```
L_hdr = b"aegis-hdr-v1\x00"                  # 13 bytes
L_ctx = b"aegis-ctx-v1\x00"                  # 13 bytes
aad   = SHA256(L_hdr ‖ header_core) ‖ SHA256(L_ctx ‖ canonical_context)
```

`header_core` is the 73-byte core of § 2.1. Because it contains the salt and the commitment, the
body is bound to the key commitment as well as to the format version, suite and custody mode.

The labels are domain separation: they tie each digest to one role and one format version, so
neither hash can coincide with a SHA-256 computed of the same bytes for any other purpose. Every
hash label ends in `\x00`, and every HKDF `info` is a distinct fixed string. See
[ADR-0019](decisions.md#adr-0019-domain-separated-aad-hashes).

> **Change from `initial-spec.md` § 6.** The spec says `aad = sha256(header) ‖ sha256(context)`
> over the *whole* header. That is incompatible with its own rotation design: rotation rewrites
> the custody bytes, which would change `sha256(header)` and invalidate the tag of every chunk in
> the file. Rotation and a whole-header AAD cannot both exist.
>
> **Resolution:** the chunk AAD covers the *immutable* core only — the bytes rotation never
> touches. The custody record stays authenticated by other means (§ 4.4). The rule comes from
> [ADR-0014](decisions.md#adr-0014-chunk-aad-covers-the-immutable-header-core-only); the core it
> applies to is the one of [ADR-0028](decisions.md#adr-0028-a-typed-bounded-custody-record-replaces-the-fixed-80-byte-block).
>
> The one casualty is the "fixed-size bonus" in `initial-spec.md` § 6.1 — converting a
> caller-held file to KEK custody by rewriting only the header. The custody byte is inside the
> authenticated core, so that conversion means re-sealing. It was never a 1.0 feature.

### 4.4 Every header byte is authenticated

The header carries no tag of its own; it does not need one.

| Field | Authenticated by | Tampering produces |
|---|---|---|
| `magic`, `version`, `suite` | chunk AAD; custody AAD | `NotAnAegisFile` or `UnsupportedVersion` first |
| `custody`, `custody_len` | chunk AAD; custody AAD; strict parsing | `MalformedHeader`, `UsageError` or `UnknownKek` before any decryption |
| `salt` | input to the key schedule and the wrap key; chunk AAD; custody AAD | `KeyMismatch` |
| `commitment` | checked against the DEK; chunk AAD; custody AAD | `KeyMismatch` |
| `key_id` | custody AAD for local KEKs; key selection | `UnknownKek`, or `KeyMismatch` |
| `payload_len`, padding | strict parsing | `MalformedHeader` |
| `payload` | its own GCM tag (local) or the source's integrity check; then the commitment | `KeyMismatch` |

Every byte of the header is either authenticated, an input to a key derivation, or pinned by an
exact parsing rule. There is no unauthenticated slack anywhere in the file.

Pasting one file's whole header onto another file's body yields a header that opens — but its
body key and its core belong to the other file, so chunk 0 fails. Transplanting only a custody
record into another header changes the record's associated data and the DEK it yields, so the
unwrap or the key check fails before any chunk. Swapping two chunks changes their counters, so
both fail.

## 5. Canonical serialization of `context`

`context` is the caller's binding data. It is **never stored in the file** — only its hash
enters the AAD (see § 7.2).

The context is a mapping. Accepted types are **exactly** these, with no subclasses
([ADR-0033](decisions.md#adr-0033-context-values-must-have-an-exactly-accepted-type)):

- keys: `str`;
- values: `str`, `bytes`, `int`, `bool` or `None`.

`float` is rejected with `UsageError`: its representation is not stable enough to be a
cryptographic input. Nested dicts and sequences are rejected in v1.

Encoding, with keys sorted by their **UTF-8 byte sequence** (not by Unicode code point, not by
locale):

```
for each (key, value) in sorted order:
    u32be(len(key_utf8)) ‖ key_utf8 ‖ type_tag(1 B) ‖ u32be(len(value_bytes)) ‖ value_bytes
```

| Type | Tag | Value bytes |
|---|---|---|
| `str` | `0x01` | UTF-8 |
| `bytes` | `0x02` | the bytes themselves |
| `int` | `0x03` | 8 bytes, big-endian, **two's-complement signed** |
| `bool` | `0x04` | 1 byte: `0x00` or `0x01` |
| `None` | `0x05` | empty, length `0` |

Then `context_hash = SHA256(b"aegis-ctx-v1\x00" ‖ canonical_bytes)` (§ 4.3).

An empty context `{}` is legal and canonicalizes to the empty byte string. `context=None` is not
a context and raises `UsageError`
([ADR-0020](decisions.md#adr-0020-context-is-required-but-may-be-empty)).

**Why length prefixes and type tags.** Length prefixing removes separator ambiguity:
`{"a|b": "c"}` and `{"a": "b|c"}` must not collide. Type tags separate `1` from `"1"` from `True`,
which in Python are three different values that a naive `str()` encoding would merge. `bool` is
checked **before** `int`, because `isinstance(True, int)` is `True` in Python; getting that order
wrong makes `True` and `1` collide.

Additional rules a writer **MUST** enforce, all raising `UsageError`:

- An `int` outside the signed 64-bit range.
- A key or value whose encoded length exceeds `2**32 - 1`.
- A `str` containing lone surrogates (it cannot be UTF-8 encoded).
- Any type not in the table above. That includes `float`, `dict`, `list`, `tuple`, `set`,
  `Decimal` and `datetime`, and also subclasses of accepted types — `IntEnum`, `StrEnum`, Django's
  `SafeString` — and `bytearray` and `memoryview`. Callers convert deliberately; the library
  never guesses.

## 6. Algorithms

### 6.1 Sealing

```
1.  canonical = canonicalize(context)                             → UsageError
2.  dek  = os.urandom(32)
    salt = os.urandom(32)
3.  body_key, nonce_prefix, commitment = schedule(dek, salt)       # § 3.2
4.  core   = magic ‖ version ‖ suite ‖ custody ‖ salt ‖ commitment ‖ u16be(custody_len)
5.  record = local wrap (§ 3.3), source wrap (§ 3.4), or empty (caller-held)
6.  aad    = SHA256(L_hdr ‖ core) ‖ SHA256(L_ctx ‖ canonical)
7.  write_all(core ‖ record)
8.  counter = 0
    for each segment of exactly 65536 bytes (fewer only at the end of the input),
    knowing whether it is the last:
        if counter == MAX_CHUNKS                                   → UsageError
        nonce = nonce_prefix ‖ u32be(counter) ‖ (0x01 if last else 0x00)
        write_all(AESGCM(body_key).encrypt(nonce, segment, aad))
        counter += 1
9.  return Receipt(size, algorithm, version,
                   key=dek if caller-held else None, key_id=record's key_id or None)
```

- *Read ahead.* Step 8 requires knowing whether a segment is the last **before** encrypting it,
  so the writer reads one segment ahead. Implementations **MUST NOT** rewind and rewrite: the
  output stream may be a pipe or a network socket.
- *Full segments.* A segment is filled by as many reads as it takes; a short read is not the end
  of the input.
- *Full writes.* `write_all` loops until every byte is accepted.
- *Rejected streams.* A non-blocking stream (`None` from `read` or `write`), a text stream, or a
  `read` that returns more than was asked raises `UsageError`.

These four rules are [ADR-0031](decisions.md#adr-0031-the-stream-io-contract-full-segments-full-writes-blocking-streams).

### 6.2 Unsealing

```
1.  canonical = canonicalize(context); check the call's custody arguments   → UsageError
2.  read the header, checking each field as its bytes arrive:
      first 4 bytes empty, or not a prefix of the magic              → NotAnAegisFile
      a matching prefix that ends before 4 bytes                     → MalformedHeader
      version missing → MalformedHeader;   version ≠ 0x01            → UnsupportedVersion
      suite   missing → MalformedHeader;   suite   ≠ 0x01            → UnsupportedVersion
      the rest of the core short; custody or custody_len rules (§ 2.4) → MalformedHeader
      the custody record short; record rules (§ 2.5)                 → MalformedHeader
3.  custody mode against the vault (caller-held / local / external)  → UsageError, UnknownKek
4.  dek = the caller's key | local unwrap (§ 3.3) | source.unwrap (§ 3.4)
        · key_id not among the configured keys                       → UnknownKek
        · the wrap does not authenticate (local tag, or the source)  → KeyMismatch
5.  schedule(dek, salt); commitment ≠ header.commitment             → KeyMismatch
6.  aad = SHA256(L_hdr ‖ core) ‖ SHA256(L_ctx ‖ canonical)
7.  counter = 0
    loop:
        if counter == MAX_CHUNKS                                     → UnsealFailed
        block = read_exactly(65552)
        if a further byte exists:                                    # not the last chunk
            plain = decrypt(block, counter, last=False)              → UnsealFailed
            emit(plain); counter += 1; continue
        # the final block
        if len(block) < 16                                           → TruncatedFile
        plain = decrypt(block, counter, last=True)
        if that fails:
            len(block) == 65552 and decrypt(block, counter, last=False) succeeds
                                                                     → TruncatedFile
            otherwise                                                → UnsealFailed
        if len(plain) == 0 and counter > 0                           → UnsealFailed
        emit(plain); break
```

Steps 1 and 3 settle everything the call itself decides before a single byte is read. Steps 2–5
settle everything the header decides before a single chunk is decrypted.

**What is distinguishable.** `UnknownKek` and `KeyMismatch` are decided before the body. Past
the commitment check the key is known to be right, so a failing chunk means a wrong context or
damaged data, and `UnsealFailed` says exactly that. Truncation is classified by
[ADR-0030](decisions.md#adr-0030-how-a-reader-classifies-truncation-and-when-a-final-chunk-may-be-empty):

| How the body ends | Outcome |
|---|---|
| no chunk at all | `TruncatedFile` |
| 1–15 bytes after the last complete chunk | `TruncatedFile` |
| at a chunk boundary, after a chunk marked non-final | `TruncatedFile` — that chunk is not emitted |
| inside a chunk, leaving 16 bytes or more | `UnsealFailed` — indistinguishable from corruption |
| with an empty final chunk after a full one | `UnsealFailed` — non-canonical |

Each `TruncatedFile` is proven by the final-chunk flag, not guessed. The extra decryption at a
boundary costs one GCM operation on a failing file only.

### 6.3 Random access

A reader over a seekable source may locate any chunk from the container's size. Before it
returns any byte, it **MUST** authenticate the final chunk:

```
header_len = 73 + custody_len
body_len   = container_size − header_len
body_len == 0                                            → TruncatedFile
N          = ceil(body_len / 65552)
last_len   = body_len − (N − 1) × 65552
1 ≤ last_len ≤ 15                                        → TruncatedFile
N > MAX_CHUNKS                                           → UnsealFailed
decrypt chunk N − 1 with last=True, applying the final-block rules of § 6.2
                                                         → TruncatedFile / UnsealFailed
plaintext_size = (N − 1) × 65536 + (last_len − 16)
chunk i starts at header_len + i × 65552 and is decrypted with last = (i == N − 1)
```

A reader that has authenticated the final chunk this way knows the exact plaintext size and that
the file is complete. Every chunk it returns afterwards is authenticated at its own index. Tink's
specification allows random access on the same footing: an API must never let end of file be
confused with a decryption error.

### 6.4 Rotation

```
1.  read the header (§ 6.2, steps 2–3); caller-held → nothing to rotate
2.  dek = unwrap with the configured key that matches key_id         → UnknownKek
3.  commitment check (§ 3.2)                                         → KeyMismatch
4.  key_id == the primary key's id → no-op, nothing written
5.  record' = wrap(dek) under the primary key, with the same custody_len
                                                                     → UsageError if it cannot fit
6.  overwrite bytes 73 … 73 + custody_len − 1 with record'           # journaled, ADR-0035
```

Bytes 0–72 and the entire body are untouched. For a local KEK the new record is deterministic
given the KEK, the salt and the DEK. On a seekable file this is one write of `custody_len`
bytes at offset 73. Its cost is per file — a few `fsync`s for the journal of
[ADR-0035](decisions.md#adr-0035-rotation-write-path-torn-write-journal-public-calls-recursive-runs)
— not per byte. Object stores cannot overwrite part of an object; there, rotation streams a new
copy with the body bytes copied verbatim and never decrypted (`rewrap`). That "the body is
byte-identical after rotation" is a **tested invariant**, not a claim
(see [tests.md § 6](tests.md#6-layer-5--rotation-and-dogfood)).

Rotation never changes the DEK, so it does not re-key the file body. An attacker who already
captured a file's DEK keeps it, and an older copy of a file still opens with the key it was
sealed under. Rotation limits the blast radius of a *KEK* compromise for copies the attacker
does not have; see [security.md § 5.2](security.md#52-what-rotation-does-and-does-not-do).

## 7. Properties and their price

### 7.1 What the layout buys

- **Key commitment** — a header opens under exactly one key, checked before the body (§ 3.2).
- **Nonce safety without trust** — body key and nonce prefix are unique per file even if a DEK
  were repeated.
- **Truncation resistance** — the final chunk is marked in its own nonce.
- **Rotation without touching contents** — an immutable core and a rewritable custody record of
  fixed length.
- **Bring-your-own KMS** — external custody holds any wrap up to 4 KiB.
- **~0.024 % overhead** — 16 bytes per 64 KiB, plus a header of 139 bytes for a local KEK or 73
  for caller-held custody. 100 MB → 100.025 MB, against ~133 MB for base64.
- **Constant memory** — one 64 KiB segment in flight, regardless of file size.
- **Random access** — any chunk can be located and authenticated on its own (§ 6.3).
- **Authenticated header** — see § 4.4. A tampered file never decrypts to garbage; it raises.
- **Canonical encoding** — one plaintext, key and context yield exactly one byte sequence, given
  fixed randomness. This is what makes frozen test vectors possible.

### 7.2 Accepted consequences

1. **`context` is not recoverable from the file.** Only its hash enters the AAD, so the blob
   leaks no `user_id` to whoever obtains the bucket. The price is that when the context does not
   match, the library cannot tell you what it expected. Security beats ergonomics here,
   knowingly.

   **Corollary the caller must respect: the context must remain reproducible for the entire life
   of the blob.** Binding to a mutable field — an owner that can be transferred, a path that can
   be renamed — makes the file unopenable the moment that field changes. See
   [usage.md § 4](usage.md#4-context-the-one-thing-to-get-right).
2. **Equal contexts are interchangeable.** Aegis proves a blob is genuine and bound to its
   context; it cannot know whether it is the *current* blob for that context. Replacing a blob
   with another genuine blob sealed under an equal context — an older version, or a sibling file
   when the context names only the owner — is not detected. Put a per-file or per-version
   identifier in the context; see [security.md § 3](security.md#3-what-aegis-does-not-defend-against).
3. **Forward-only streaming has a trust boundary.** Output is emitted chunk by chunk, each one
   authenticated, but the file is only proven whole once `unseal()` returns without raising. A
   consumer acting on partial output may act on truncated-but-authentic data. This is inherent to
   every streaming AEAD.

   Mitigations: `unseal_to_path()` (atomic), `unseal_bytes()` (all-or-nothing), and seekable
   readers, which authenticate the final chunk first (§ 6.3). See
   [security.md § 6](security.md#6-the-streaming-trust-boundary).
4. **`key_id` and the custody mode are visible.** See § 3.3.
5. **No compression** — see [product.md § 4](product.md#4-what-aegis-deliberately-does-not-do).

### 7.3 Limits

| Limit | Value | Source |
|---|---|---|
| Maximum plaintext per file | **256 TiB** | 2³² chunks × 64 KiB |
| Maximum files per key | effectively unbounded | a 256-bit salt per file: birthday bound 2¹²⁸ |
| Header | 73 + `custody_len` bytes, at most 4 169 | § 2 |
| Maximum `context` key or value | 4 GiB − 1 each | `u32be` length prefix |
| Maximum `int` in `context` | signed 64-bit | fixed 8-byte encoding |

`MAX_CHUNKS = 2**32` is checked before each nonce is built, in both directions. A writer raises
`UsageError` rather than wrap the counter. A reader raises `UnsealFailed`, since only a
non-conforming writer could produce such a file.

## 8. Changing this format

The format version byte exists so that this document never has to be edited in place.

- Any change to any byte described here — a field, an offset, a derivation string, the chunk
  size, the context encoding — is a **new `version` value**, plus a new frozen test vector file.
  It is never an edit to v1. The one exception is the revision boxed at the top of this
  document, made before the freeze, when no v1 file existed yet.
- Consequently, **regenerating the frozen vectors is by definition a format change.** If a code
  change makes `tests/vectors/v1.json` fail, the code is wrong. The vectors are not refreshed to
  match the code, ever. That rule is what the compatibility promise is made of.
- The reader keeps understanding every version it ever shipped. The writer emits the newest
  version only on explicit opt-in.

## 9. Reference vectors (to be generated at M4)

`tests/vectors/v1.json` will pin, for a fixed DEK, salt, KEK or test key source, context and
plaintext:
- the derived body key, nonce prefix and commitment;
- the exact expected bytes of the whole container;
- a list of byte sequences that must be rejected, each with its exact exception.

The vectors are generated once, by hand-checked code, and never regenerated. Format and freeze
policy: [tests.md § 3](tests.md#3-layer-1--frozen-vectors-kat).
