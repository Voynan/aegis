# Aegis file format v1 — normative specification

This document defines the `.aegis` container, byte for byte. It is the one artifact in the
project that **cannot change**. Code gets rewritten; a user's file has to open years from
now.

Anything here marked **MUST** / **MUST NOT** is enforced by the reader and covered by a test.
Where this document departs from [`initial-spec.md`](initial-spec.md), the departure is boxed
and justified.

---

## 1. Overview

```
┌─ HEADER — 94 bytes, fixed size ────────────────────────────────┐
│  magic          4 B   "AEG\x00"                                │
│  version        1 B   0x01                                     │
│  suite          1 B   0x01 = AES-256-GCM / STREAM / 64 KiB     │
│  flags          1 B   bit0: 0 = wrapped DEK, 1 = caller-held   │
│  kek_id        16 B   KEK fingerprint      (zeros if caller)   │
│  salt          16 B   HKDF salt            (zeros if caller)   │
│  wrapped_dek   48 B   ciphertext 32 + tag 16 (zeros if caller) │
│  nonce_prefix   7 B   random, STREAM base                      │
└────────────────────────────────────────────────────────────────┘
┌─ CHUNKS — N ≥ 1 ───────────────────────────────────────────────┐
│  [ up to 65536 B plaintext, encrypted ] ‖ [ 16 B GCM tag ]      │
│  nonce = nonce_prefix(7) ‖ counter_be32(4) ‖ last_flag(1)      │
│  aad   = sha256(header_core) ‖ sha256(canonical_context)       │
└────────────────────────────────────────────────────────────────┘
```

All multi-byte integers are **big-endian**. There is no padding and no alignment
requirement. The format is not self-delimiting: the container ends where the file ends.

## 2. Header

| Offset | Size | Field | Contents |
|---:|---:|---|---|
| 0 | 4 | `magic` | `41 45 47 00` — ASCII `AEG` followed by `0x00` |
| 4 | 1 | `version` | `0x01` |
| 5 | 1 | `suite` | `0x01` |
| 6 | 1 | `flags` | bit 0 = custody mode; bits 1–7 reserved |
| 7 | 16 | `kek_id` | KEK fingerprint, or 16 zero bytes |
| 23 | 16 | `salt` | HKDF salt, 16 random bytes, or 16 zero bytes |
| 39 | 48 | `wrapped_dek` | AES-GCM ciphertext (32 B) ‖ tag (16 B), or 48 zero bytes |
| 87 | 7 | `nonce_prefix` | 7 random bytes |
| **94** | | | first chunk begins |

### 2.1 `suite`

`suite` names the complete cryptographic configuration as one byte. `0x01` means, and will
always mean:

- AEAD: AES-256-GCM (96-bit nonce, 128-bit tag)
- Construction: STREAM (segmented AEAD with a counter and a final-segment marker)
- Chunk size: 65536 bytes of plaintext
- DEK wrap KDF: HKDF-SHA256
- Context hash: SHA-256

A different value for any of those is a different suite byte, never a redefinition of
`0x01`. Readers **MUST** reject unknown suites with `UnsupportedVersion`.

### 2.2 `flags`

| Bit | Meaning |
|---:|---|
| 0 | `0` = DEK is wrapped in this header (KEK custody); `1` = DEK is held by the caller |
| 1–7 | Reserved. Writers **MUST** set them to `0`; readers **MUST** reject non-zero with `MalformedHeader`. |

Rejecting reserved bits rather than ignoring them keeps the bits genuinely available for a
future version, and makes bit-flip fuzzing deterministic.

### 2.3 The custody triple

`kek_id`, `salt` and `wrapped_dek` (offsets 7–86, 80 bytes) form the **custody block**. It
is the only mutable region of the file: `aegis rotate` rewrites those 80 bytes and nothing
else.

When `flags` bit 0 is `1` (caller-held), all 80 bytes **MUST** be zero on write, and a
reader **MUST** reject a non-zero custody block with `MalformedHeader`. Requiring zeros
rather than ignoring the region removes a covert channel and makes the format canonical:
one plaintext plus one key plus one context produces exactly one byte sequence.

## 3. Key hierarchy

```
KEK (32 B, yours)  ──HKDF-SHA256(salt, "aegis-dek-wrap-v1")──▶  wrapping key (32 B)
                                                                      │
DEK (32 B, random per file) ──────AES-256-GCM──────────────────▶ wrapped_dek (48 B)
     │
     └─── encrypts the file body via STREAM
```

The KEK **never** encrypts file data directly. It only ever encrypts a 32-byte DEK.

### 3.1 `kek_id`

```
kek_id = SHA256(b"aegis-kek-id\x00" ‖ kek)[:16]
```

Derived, never configured. This eliminates the entire "I configured the wrong key id"
class of error, and it makes rotation self-describing: a reader looks at `kek_id`, finds
the matching KEK among the configured ones, and fails with `UnknownKek` before attempting
any decryption if there is none.

`kek_id` is the only cleartext metadata in the file. It reveals *that* a KEK was used and
*which* one — never anything about the content. Accepted in exchange for cheap rotation.

### 3.2 Wrapping the DEK

```
salt         = 16 random bytes                       # fresh per file
wrapping_key = HKDF-SHA256(ikm=kek, salt=salt,
                           info=b"aegis-dek-wrap-v1", length=32)
wrapped_dek  = AES-256-GCM(wrapping_key).encrypt(
                   nonce = b"\x00" * 12,             # safe: see below
                   data  = dek,
                   aad   = header[0:23])             # magic..kek_id
```

**Why an all-zero nonce is safe here.** The GCM requirement is that a (key, nonce) pair is
never reused. `wrapping_key` is derived with a fresh random 16-byte salt for every file, so
each wrap uses a distinct key and the nonce carries no uniqueness burden. This is
deliberately stronger than a random nonce per file with a shared key: it removes any
birthday bound on how many files a single KEK may protect.

The AAD binds the wrap to `magic ‖ version ‖ suite ‖ flags ‖ kek_id`, so a wrapped DEK
cannot be transplanted into a header claiming a different version, suite or custody mode.

### 3.3 Caller-held custody

`flags` bit 0 = `1`. No wrap happens. Aegis generates the DEK, returns it in the
`Receipt`, and persists nothing. The caller's key **is** the DEK: 32 bytes of
high-entropy material produced by `os.urandom`, not a passphrase (see
[product.md § 4](product.md#4-what-aegis-deliberately-does-not-do)).

Losing that key means losing the file. There is no recovery path, by design.

## 4. Chunks

### 4.1 Framing

The plaintext is split into segments of exactly **65536 bytes**, except the last, which
holds 1–65536 bytes — or 0 bytes if and only if the plaintext is empty.

```
number_of_chunks = max(1, ceil(len(plaintext) / 65536))
```

> **Spec addition (not stated in `initial-spec.md`).** A zero-length plaintext produces **one**
> chunk containing 0 bytes of ciphertext and a 16-byte tag. Without this rule an empty file
> would be a bare 94-byte header, which is byte-identical to a maliciously truncated file
> and would make "header only" a valid container. `N ≥ 1` always.

Each chunk on disk is `len(segment) + 16` bytes: the AES-GCM ciphertext (same length as the
plaintext segment) followed by the 16-byte tag. Non-final chunks are therefore always
exactly 65552 bytes.

A plaintext whose length is an exact multiple of 65536 ends with a *full* final chunk. No
empty trailing chunk is appended.

### 4.2 Nonce

```
nonce = nonce_prefix (7 B) ‖ counter (4 B, big-endian) ‖ last_flag (1 B)
        └─ from header ─┘   └─ 0, 1, 2, … ─┘            └ 0x00 or 0x01 ┘
```

96 bits total, as AES-GCM requires. `counter` starts at `0` for the first chunk.
`last_flag` is `0x01` for the final chunk and `0x00` for every other chunk.

`nonce_prefix` is 7 fresh random bytes per file. Nonce uniqueness therefore rests on two
independent facts: the DEK is unique per file, *and* the prefix is unique per file. Reuse
would require both a DEK collision and a prefix collision.

The counter is what makes chunk reordering and duplication detectable: chunk *i* only
authenticates at position *i*.

The `last_flag` is what makes truncation detectable. Without it, chunked streaming AEAD is
trivially truncatable — any prefix of the chunk sequence is a valid shorter file.

### 4.3 Associated data

Every chunk is encrypted with the same 64-byte AAD:

```
header_core = header[0:7] ‖ header[87:94]        # magic, version, suite, flags, nonce_prefix
aad         = SHA256(header_core) ‖ SHA256(canonical_context)
```

> **Change from `initial-spec.md` § 6.** The spec says
> `aad = sha256(header) ‖ sha256(context)` over the *whole* 94-byte header. That is
> incompatible with the spec's own rotation design: `aegis rotate` rewrites `kek_id`,
> `salt` and `wrapped_dek`, which changes `sha256(header)`, which would invalidate the tag
> of every chunk in the file. Rotation and a whole-header AAD cannot both exist.
>
> **Resolution:** the chunk AAD covers the *immutable* header core only — the 14 bytes that
> rotation never touches. The custody block stays authenticated by other means (§ 4.4), so
> no property from `initial-spec.md` § 6.1 is lost. See
> [ADR-0014](decisions.md#adr-0014-chunk-aad-covers-the-immutable-header-core-only).
>
> The one casualty is the "fixed-size bonus" in `initial-spec.md` § 6.1 — converting a
> caller-held file to KEK custody by rewriting only the header. `flags` is inside the
> authenticated core, so that conversion now requires rewriting the body. It was never a
> 1.0 feature.

### 4.4 Every header byte is authenticated

The header carries no tag of its own; it does not need one.

| Field | Authenticated by | Tampering produces |
|---|---|---|
| `magic`, `version`, `suite`, `flags` | chunk AAD **and** wrap AAD | `UnsealFailed` (or `NotAnAegisFile` / `UnsupportedVersion` first) |
| `nonce_prefix` | chunk AAD | `UnsealFailed` on chunk 0 |
| `kek_id` | wrap AAD | `UnknownKek`, or `UnsealFailed` on unwrap |
| `salt` | HKDF input — a wrong salt yields a wrong wrapping key | `UnsealFailed` on unwrap |
| `wrapped_dek` | its own GCM tag | `UnsealFailed` on unwrap |

In caller-held mode the custody triple is required to be all zeros (§ 2.3), so every byte
of the header is either authenticated or pinned to a constant. There is no unauthenticated
slack anywhere in the file.

Pasting one file's header onto another file's body changes `nonce_prefix` (and the DEK), so
chunk 0 fails. Swapping two chunks changes their counters, so both fail.

## 5. Canonical serialization of `context`

`context` is the caller's binding data. It is **never stored in the file** — only its hash
enters the AAD (see § 7.1).

Accepted types: `str` keys; `str`, `bytes`, `int`, `bool` or `None` values. `float` is
rejected with `UsageError` — its representation is not stable enough to be a cryptographic
input. Nested dicts and sequences are rejected in v1.

Encoding, with keys sorted by their **UTF-8 byte sequence** (not by Unicode code point, not
by locale):

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

Then `context_hash = SHA256(canonical_bytes)`.

**Why length prefixes and type tags.** Length prefixing removes separator ambiguity —
`{"a|b": "c"}` and `{"a": "b|c"}` must not collide. Type tags separate `1` from `"1"` from
`True`, which in Python are three different values that a naive `str()` encoding would
merge. `bool` is checked **before** `int`, because `isinstance(True, int)` is `True` in
Python; getting that order wrong makes `True` and `1` collide.

Additional rules a writer **MUST** enforce, all raising `UsageError`:

- `int` outside the signed 64-bit range.
- A key or value whose encoded length exceeds `2**32 - 1`.
- A `str` containing lone surrogates (it cannot be UTF-8 encoded).
- Any type not in the table above — including `float`, `dict`, `list`, `tuple`, `set`,
  `Decimal`, `datetime` and `Enum`. Callers convert deliberately; the library never guesses.

## 6. Algorithms

### 6.1 Sealing

```
1.  dek, custody = key_source.provision()          # 32 random bytes + the custody block
2.  nonce_prefix = os.urandom(7)
3.  header       = assemble(magic, version, suite, flags, custody, nonce_prefix)
4.  aad          = SHA256(header[0:7] ‖ header[87:94]) ‖ SHA256(canonical(context))
5.  write(header)
6.  counter = 0
    for each 65536-byte segment, knowing whether it is the last:
        nonce = nonce_prefix ‖ u32be(counter) ‖ (0x01 if last else 0x00)
        write(AESGCM(dek).encrypt(nonce, segment, aad))
        counter += 1
7.  return Receipt(key=dek if caller_held else None, size=…, algorithm=…, version=…)
```

Step 6 requires knowing whether a segment is the last **before** encrypting it, which means
the writer reads one segment ahead. Implementations **MUST NOT** rewind and rewrite: the
output stream may be a pipe or a network socket.

### 6.2 Unsealing

```
1.  header = read_exactly(94)                    → MalformedHeader on short read
2.  header.magic   == b"AEG\x00"                 → NotAnAegisFile
    header.version == 0x01                       → UnsupportedVersion
    header.suite   == 0x01                       → UnsupportedVersion
    header.flags   reserved bits == 0            → MalformedHeader
    custody triple zero iff caller-held          → MalformedHeader
3.  dek = key_source.recover(custody, caller_key)
        · kek_id not among configured KEKs       → UnknownKek  (before any decryption)
        · unwrap tag mismatch                    → UnsealFailed
        · caller-held with no key supplied       → UsageError
4.  aad = SHA256(header[0:7] ‖ header[87:94]) ‖ SHA256(canonical(context))
5.  counter = 0
    loop:
        block = read_exactly(65552)              # one full chunk, if available
        if a further byte exists:                # not the last chunk
            plain = decrypt(block, last=False)   → UnsealFailed
            emit(plain); counter += 1; continue
        # otherwise this is the final chunk: 16..65552 bytes
        if len(block) < 16                       → TruncatedFile
        plain = decrypt(block, last=True)        → UnsealFailed
        emit(plain); break
    if the stream ended after a chunk marked last=False → TruncatedFile
```

`TruncatedFile` is genuinely distinguishable — the final-chunk marker is ours, so a stream
that ends without an authenticated final chunk is provably incomplete. Nothing else is
distinguishable: a wrong key, a wrong context and a corrupted byte all produce the same GCM
`InvalidTag`, and reporting them separately would be a lie that sends the developer to
debug the wrong thing.

### 6.3 Rotation

```
1.  read header[0:94]
2.  dek = unwrap with the KEK matching header.kek_id     → UnknownKek if absent
3.  if header.kek_id == kek_id(primary): no-op, exit
4.  salt' = os.urandom(16)
    wrapped' = wrap(dek, primary_kek, salt')
5.  overwrite header[7:87] with (kek_id(primary) ‖ salt' ‖ wrapped')
```

Bytes 0–6, 87–93 and the entire body are untouched. On a seekable file this is an 80-byte
in-place write; a 10 TB bucket rotates in the time it takes to list it. That "the body is
byte-identical after rotation" is a **tested invariant**, not a claim
(see [tests.md § 6](tests.md#6-layer-5--rotation-and-dogfood)).

Rotation never changes the DEK, so it does not re-key the file body. An attacker who
already captured the DEK for a specific file keeps it. Rotation limits the blast radius of
a *KEK* compromise, which is the realistic one — see
[security.md § 5](security.md#5-key-management).

## 7. Properties and their price

### 7.1 What the layout buys

- **Truncation resistance** — the final chunk is marked in its own nonce.
- **Rotation without touching contents** — fixed-size header, isolated custody block.
- **~0.024 % overhead** — 16 bytes per 64 KiB plus a 94-byte header. 100 MB → 100.024 MB
  (against ~133 MB for base64).
- **Constant memory** — one 64 KiB segment in flight, regardless of file size.
- **Authenticated header** — see § 4.4. A tampered file never decrypts to garbage; it
  raises.
- **Canonical encoding** — one plaintext, key and context yield exactly one byte sequence,
  given fixed randomness. This is what makes frozen test vectors possible.

### 7.2 Accepted consequences

1. **`context` is not recoverable from the file.** Only its hash enters the AAD, so the
   blob leaks no `user_id` to whoever obtains the bucket. The price: when the context does
   not match, the library cannot tell you what it expected. Security beating ergonomics,
   knowingly. **Corollary the caller must respect: the context must remain reproducible for
   the entire life of the blob.** Binding to a mutable field (an owner that can be
   transferred, a path that can be renamed) makes the file unopenable the moment that field
   changes. See [usage.md § 4](usage.md#4-context-the-one-thing-to-get-right).
2. **Streaming has a trust boundary.** Output is emitted chunk by chunk, each one
   authenticated, but the file is only proven whole once `unseal()` returns without
   raising. A consumer acting on partial output may act on truncated-but-authentic data.
   This is inherent to every streaming AEAD. Mitigations: `unseal_to_path()` (atomic) and
   `unseal_bytes()` (all-or-nothing) — see
   [security.md § 6](security.md#6-the-streaming-trust-boundary).
3. **`kek_id` is visible.** See § 3.1.
4. **No compression** — see [product.md § 4](product.md#4-what-aegis-deliberately-does-not-do).

### 7.3 Limits

| Limit | Value | Source |
|---|---|---|
| Maximum plaintext per file | **256 TiB** | 2³² chunks × 64 KiB |
| Maximum files per KEK | effectively unbounded | fresh HKDF salt per file removes the birthday bound |
| Maximum `context` key/value | 4 GiB − 1 each | `u32be` length prefix |
| Maximum `int` in `context` | signed 64-bit | fixed 8-byte encoding |

A writer that reaches 2³² chunks **MUST** raise rather than wrap the counter.

## 8. Changing this format

The format version byte exists so that this document never has to be edited in place.

- Any change to any byte described here — a field, an offset, a derivation string, the
  chunk size, the context encoding — is a **new `version` value**, plus a new frozen test
  vector file. It is never an edit to v1.
- Consequently, **regenerating the frozen vectors is by definition a format change.** If a
  code change makes `tests/vectors/v1.json` fail, the code is wrong. The vectors are not
  refreshed to match the code, ever. That rule is what the compatibility promise is made
  of.
- The reader keeps understanding every version it ever shipped. The writer emits the newest
  version only on explicit opt-in.

## 9. Reference vector (to be generated at M4)

`tests/vectors/v1.json` will pin, for a fixed KEK, DEK, salt, `nonce_prefix`, context and
plaintext, the exact expected bytes of the whole container. Generated once, by hand-checked
code, and never regenerated. Format and freeze policy: [tests.md § 3](tests.md#3-layer-1--frozen-vectors-kat).
