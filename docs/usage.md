# Usage

Everything a developer needs, in the order they need it. This document describes the
intended 1.0 API; no code exists yet.

---

## 1. Install

```bash
pip install aegis              # core — one dependency: cryptography
pip install "aegis[django]"    # + the Django field
pip install "aegis[cli]"       # + the aegis command
```

## 2. Sixty seconds

```bash
# 1. Make a master key and put it in the environment (never in the repository)
export AEGIS_MASTER_KEY="$(python -c 'import os,base64;print(base64.b64encode(os.urandom(32)).decode())')"
```

```python
from aegis import Vault, EnvKey

vault = Vault(key=EnvKey("AEGIS_MASTER_KEY"))

with open("contract.pdf", "rb") as src, open("contract.aegis", "wb") as dst:
    receipt = vault.seal(src, dst, context={"user_id": 42, "file_id": 7})

with open("contract.aegis", "rb") as src, open("out.pdf", "wb") as dst:
    vault.unseal(src, dst, context={"user_id": 42, "file_id": 7})
```

That is the whole library. The rest of this document is about the two decisions inside it:
where the key comes from, and what goes in `context`.

## 3. The mental model

**A vault configured once, used everywhere.** You make one decision — where the key comes
from — and then stop thinking about cryptography.

```python
vault = Vault(key=EnvKey("AEGIS_MASTER_KEY"))
```

Build it once at startup (module level, a Django setting, a FastAPI dependency) and share
it. A `Vault` is immutable and safe to use from multiple threads.

### 3.1 The four operations

```python
# streaming — the main path, constant memory whatever the file size
receipt = vault.seal(src_stream, dst_stream, context={...})
vault.unseal(src_stream, dst_stream, context={...})

# sugar for when you already hold the bytes — O(n) memory, by definition
blob = vault.seal_bytes(data, context={...})
data = vault.unseal_bytes(blob, context={...})
```

`src` and `dst` are any binary file-like objects: real files, `BytesIO`, sockets, a Django
`UploadedFile`, an S3 body. They are read and written forward only, never seeked, so pipes
work.

### 3.2 And one safety helper

```python
vault.unseal_to_path(src_stream, "out.pdf", context={...})
```

Use this whenever the destination is a path on disk. See § 7 for why it matters.

### 3.3 The receipt

```python
receipt = vault.seal(src, dst, context={...})
receipt.size        # plaintext bytes processed
receipt.algorithm   # "AES-256-GCM/STREAM"
receipt.version     # 1
receipt.key         # bytes, in CallerHeld mode only; None otherwise
repr(receipt)       # "Receipt(size=1024, …, key=<redacted 32 bytes>)" — never the key
```

## 4. `context`: the one thing to get right

`context` is mandatory and becomes the AEAD's associated data. It binds the blob to its
record: a ciphertext belonging to user 42 will not open as user 99 — authentication simply
fails. If your database is swapped row-for-row, or a blob is copied from one record to
another, decryption stops rather than succeeding on the wrong file.

To open a file you must reproduce the same context. **Losing it means not opening the
file, and that is the intent.**

### 4.1 Three rules

1. **Reproducible.** You must be able to rebuild the exact same dictionary at read time,
   from data you still have.
2. **Immutable for the life of the blob.** Bind to things that never change. `owner_id` is
   a trap if ownership can be transferred; the file becomes unopenable the moment it is.
   Prefer an immutable surrogate: the row's primary key, a UUID assigned at creation, a
   tenant id that never moves.
3. **Not secret.** The context is not stored in the file and only its hash is used, so it
   leaks nothing — but it is also not a second password. Its job is binding, not secrecy.

```python
# good — immutable identifiers
context={"tenant": "acme", "document_id": str(doc.uuid)}

# risky — breaks the day a document is reassigned
context={"user_id": doc.owner_id}

# broken — not reproducible
context={"read_at": time.time()}   # also rejected: floats raise UsageError
```

### 4.2 Accepted types

| Type | Notes |
|---|---|
| `str` | keys must be `str`; encoded as UTF-8 |
| `bytes` | used verbatim |
| `int` | signed 64-bit range |
| `bool` | distinct from `0` / `1` — the encoding tags types |
| `None` | a legitimate value |

`float` is **rejected** with `UsageError`: its representation is not stable enough to be a
cryptographic input. So are `dict`, `list`, `tuple`, `set`, `Decimal`, `datetime` and
`Enum` — convert them yourself, deliberately, so the encoding is visible in your code
rather than guessed by ours.

Ordering does not matter: `{"a": 1, "b": 2}` and `{"b": 2, "a": 1}` produce the same bytes
([file-format.md § 5](file-format.md#5-canonical-serialization-of-context)).

## 5. Key custody: the only knob

The `key` argument is the only thing that changes between the two modes.

### 5.1 Server holds the key (the default)

```python
vault = Vault(key=EnvKey("AEGIS_MASTER_KEY"))
receipt = vault.seal(src, dst, context={...})
receipt.key   # None — the data key is wrapped inside the file
```

The server can read every file it stores. This is what you want for a normal product where
the application renders, indexes or processes user documents.

### 5.2 The caller holds the key

```python
from aegis import Vault, CallerHeld

vault = Vault(key=CallerHeld())
receipt = vault.seal(src, dst, context={...})
receipt.key      # 32 bytes — give these to the user; Aegis stores nothing

vault.unseal(src, dst, context={...}, key=user_key)   # required in this mode
```

Nothing about the key is persisted. **If the user loses it, the file is gone** — there is
no recovery, by design. That key is 32 bytes of high-entropy material generated by Aegis,
not a passphrase; Aegis 1.0 has no password-based key derivation. If you need one, derive a
32-byte key with Argon2id yourself and pass it as the caller key.

## 6. Errors, and what to do about each

```
AegisError
├── ConfigurationError    → your startup is wrong. Fix the env var; this never happens at runtime.
├── FormatError
│   ├── NotAnAegisFile    → this is not an Aegis file. Wrong path, or a double-decrypt.
│   ├── UnsupportedVersion→ written by a newer Aegis. Upgrade the library.
│   └── MalformedHeader   → the first 94 bytes are truncated or inconsistent.
├── UnknownKek            → you are missing a key, not looking at a broken file.
│                           "sealed with KEK a3f1…; you have b7c2…"
├── UnsealFailed          → "wrong key, wrong context, or corrupted file" — all three at once.
│   └── TruncatedFile     → the file is incomplete. A failed upload, a partial copy.
└── UsageError            → your call is wrong. A float in context, CallerHeld without a key.
```

**Why `UnsealFailed` is vague on purpose.** AES-GCM cannot tell a wrong key from a wrong
context from a flipped bit — all three produce the same failure. A library that offered
`WrongContextError` would be guessing, and would send you to debug the wrong thing. So the
message names all three possibilities, and the two cases that genuinely *are*
distinguishable get their own class: `UnknownKek` (decided before any decryption) and
`TruncatedFile` (decided by our own end-of-file marker).

**Debugging an `UnsealFailed`, in order:** (1) is the context byte-identical to what you
sealed with — same keys, same types, `42` not `"42"`? (2) is the file complete — does its
size match `94 + n + 16 × max(1, ceil(n/65536))`? (3) has the file been through anything
text-oriented — a `TextIOWrapper`, a JSON round-trip, git without `-b`?

## 7. The streaming trust boundary — read this one

`unseal` emits plaintext chunk by chunk. Every chunk it emits is authentic, but **the file
is only proven complete when `unseal()` returns without raising.** If the file was
truncated, your destination already holds a valid prefix of the plaintext when the
exception arrives.

This is inherent to every streaming AEAD, not a defect of Aegis. Three ways to live with
it:

```python
# 1. Best: let Aegis write the file atomically. Nothing survives a failure.
vault.unseal_to_path(src, "out.pdf", context={...})

# 2. Small payloads: all-or-nothing by construction.
data = vault.unseal_bytes(blob, context={...})

# 3. Streaming to a client: do not act on bytes until unseal() has returned.
#    Streaming an HTTP response body means the client may receive a truncated file
#    with a 200 status. If that matters, buffer or use unseal_to_path first.
```

## 8. Rotating your master key

Three steps, and file bodies are never touched.

```python
vault = Vault(key=EnvKey(primary="AEGIS_KEY_V2", previous=["AEGIS_KEY_V1"]))
```

```bash
# 1. add AEGIS_KEY_V2 to the environment and deploy with `previous=[...]`
# 2. re-wrap every file
aegis rotate ./bucket --recursive
# 3. remove AEGIS_KEY_V1 from the environment and from `previous`
```

Rotation unwraps the data key with the old KEK and re-wraps it with the new one, rewriting
80 bytes per file. A 10 TB bucket rotates in the time it takes to enumerate it. During step
2 files in both states are readable, so there is no downtime and no ordering requirement.

Rotation does not re-encrypt file contents, so it does not help against an attacker who
already extracted the data key of a specific file. It contains the compromise of a *KEK*,
which is the realistic one.

## 9. CLI

```bash
aegis keygen                                  # print a fresh base64 KEK
aegis seal   in.pdf  out.aegis  --context user_id=42
aegis unseal out.aegis out.pdf  --context user_id=42
aegis inspect out.aegis                       # header only — never decrypts
aegis rotate ./bucket --recursive
```

`aegis inspect` is the fastest way to understand the format before writing any code:

```
$ aegis inspect contract.aegis
file        contract.aegis
version     1
suite       1  (AES-256-GCM / STREAM / 64 KiB)
custody     KEK-wrapped
kek_id      a3f1c0de9b7742e1…
chunks      1 632
plaintext   106 954 752 bytes  (overhead 26 206 B, 0.024 %)
```

`--context` takes `key=value` pairs, which are always `str`. To reproduce a context
containing an `int` from the shell you need the CLI's typed form (`--context-int
user_id=42`); mixing the two up is the most likely cause of an `UnsealFailed` from the
command line.

Exit codes: `0` ok, `1` unseal failed, `2` usage, `3` format, `4` unknown KEK, `5`
configuration.

## 10. Django

```python
from aegis.contrib.django import SealedFileField

class Document(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    file  = SealedFileField(upload_to="docs/",
                            context=lambda inst: {"user_id": inst.owner_id})
```

- Uploads are sealed as they stream to storage; nothing is buffered in memory.
- Reading the field unseals transparently.
- **KEK custody only.** Caller-held makes no sense in a field the server must read;
  configuring it fails during `manage.py check`, not at runtime.
- The context callable must only use fields that are populated **before** the file is
  written — `inst.pk` is not available on a first save.
- The context callable must be **stable for the life of the row**. The example above binds
  to `owner_id`; if your product can transfer ownership, bind to something immutable
  instead.

## 11. Pitfalls checklist

- [ ] The KEK is in the environment or a secret manager — never in the repository, never in
      `settings.py`, never in the same database as the ciphertext.
- [ ] The context is built from immutable, reproducible fields.
- [ ] `context` values have the same **types** at seal and unseal time (`42` ≠ `"42"`).
- [ ] Files are opened in **binary** mode (`"rb"` / `"wb"`). A `TextIOWrapper` will corrupt
      ciphertext.
- [ ] `unseal_to_path` is used wherever the destination is a path.
- [ ] Nothing acts on `unseal` output before the call returns.
- [ ] `receipt.key` is not logged, not stored server-side in caller-held mode, and not put
      in a URL.
- [ ] The blob is stored as **binary** (`BinaryField`, `bytea`, a bucket object) — not
      base64 in a text column, which would undo the 0.024 % overhead.
- [ ] A `previous=[...]` key list exists in the deployment before you need to rotate.

## 12. FAQ

**Can I encrypt a database column with this?** Technically yes via `seal_bytes`, but Aegis
is shaped for files. For short values consider whether an application-level solution with
searchability is what you actually need.

**Can I search or index encrypted files?** No. Aegis is not searchable encryption. Index
the metadata you keep in cleartext.

**Can two servers share a vault?** Yes — they need the same KEK. That is the whole point of
`EnvKey`.

**Is the output deterministic?** No, and it must not be: the DEK, salt and nonce prefix are
random per file. Sealing the same file twice yields different bytes. Compare plaintexts,
not ciphertexts.

**Does it work with S3 / GCS?** Yes. `seal` writes to any file-like object; multipart
uploads work because the stream is forward-only.

**How much larger are my files?** 94 bytes plus 16 bytes per 64 KiB — about 0.024 %.

**Why not just use Fernet?** It loads the whole file into memory, has no envelope
encryption, no associated data, no rotation story, and base64-encodes its output (+33 %).

**Can I compress first?** You can, and Aegis will not do it for you: compressing before
encrypting leaks information about the plaintext through the ciphertext length. If you
understand that trade-off for your data, compress before calling `seal`.
