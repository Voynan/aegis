# Usage

Everything a developer needs, in the order they need it. This document describes the
intended 1.0 API; no code exists yet.

---

## 1. Install

```bash
pip install aegis-voynan              # core — one dependency: cryptography
pip install "aegis-voynan[cli]"       # + the aegis command
```

The PyPI name is `aegis-voynan`; everything else is `aegis` — `import aegis`, the `aegis`
command. Do not install it next to the unrelated `aegis` distribution (an aiohttp auth
library): both ship a top-level `aegis` package and would overwrite each other.

A Django adapter is planned for V2 ([dev/v2-django.md](dev/v2-django.md)). § 10 shows how to use the
core from Django, FastAPI and S3 today.

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

### 3.1 Seal and unseal, in three shapes

```python
# push — you own the destination stream; constant memory
receipt = vault.seal(src, dst, context={...})
vault.unseal(src, dst, context={...})

# pull — you get a stream to read from; constant memory
reader = vault.sealed(src, context={...})       # read() returns the sealed container
reader = vault.unsealed(src, context={...})     # read() returns plaintext; seekable if src is

# bytes — you already hold everything; O(n) memory, by definition
blob = vault.seal_bytes(data, context={...})
data = vault.unseal_bytes(blob, context={...})
```

Push when you write to a file or a socket you own. Pull when an API wants something to *read
from*: a storage backend, an HTTP response, a boto3 upload.

`src` and `dst` are any binary file-like objects: real files, `BytesIO`, sockets, a Django
`UploadedFile`, an S3 body. Short reads and partial writes are handled; segment boundaries never
depend on how much one `read()` returned. Non-blocking and text streams are rejected with
`UsageError`.

### 3.2 And one safety helper

```python
vault.unseal_to_path(src_stream, "out.pdf", context={...})
```

Use this whenever the destination is a path on disk: it writes atomically and durably, and the
file is created with mode `0600`. See § 7 for why it matters.

### 3.3 The receipt

```python
receipt = vault.seal(src, dst, context={...})
receipt.size        # plaintext bytes processed
receipt.algorithm   # "AES-256-GCM/STREAM"
receipt.version     # 1
receipt.key_id      # the 16-byte id of the key that wrapped the DEK; None when caller-held
receipt.key         # bytes, in CallerHeld mode only; None otherwise
repr(receipt)       # "Receipt(size=1024, …, key=<redacted 32 bytes>)" — never the key
```

### 3.4 The readers

```python
with vault.unsealed(src, context={...}) as reader:
    reader.size                  # the authenticated plaintext size if src is seekable, else None
    reader.seek(1_000_000)       # random access, when src is seekable
    part = reader.read(4096)
    for chunk in reader.chunks():    # up to 64 KiB each
        ...

reader = vault.sealed(src, context={...})
s3.upload_fileobj(reader, "bucket", "contract.aegis")
receipt = reader.receipt         # available once the reader has been read to the end
```

- **Errors come early.** Opening an unsealed reader checks the header, recovers the key and
  verifies the key commitment. With a seekable source, it also authenticates the final chunk.
  `UnknownKek`, `KeyMismatch` and a truncated seekable file raise at open, before you read a
  byte.
- **A reader owns its source.** Closing the reader closes `src`, as `io` wrappers do.
- **`chunks()` closes the reader** when it is exhausted or abandoned, so it can go straight into a
  streaming HTTP response.
- **Readers have no `name`.** Pass the filename and content type to your framework yourself;
  a ciphertext's name would give the wrong size.
- **One reader, one thread.** Readers are not thread-safe.

## 4. `context`: the one thing to get right

`context` is mandatory and becomes the AEAD's associated data. It binds the blob to its
record: a ciphertext belonging to user 42 will not open as user 99 — authentication simply
fails. If your database is swapped row-for-row, or a blob is copied to a record with a
different context, decryption stops rather than succeeding on the wrong file.

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
# good — immutable identifiers of this file and this version of it
context={"tenant": "acme", "document_id": str(doc.uuid), "revision": doc.revision}

# risky — every file of one owner is interchangeable, and a transfer breaks them all
context={"user_id": doc.owner_id}

# broken — not reproducible
context={"read_at": time.time()}   # also rejected: floats raise UsageError
```

### 4.2 Name the file, not only its owner

Two blobs sealed under equal contexts are interchangeable. Aegis proves a blob is genuine and
bound to its context, but it cannot know which of two genuine blobs is the current one. An
attacker with write access to your storage could:
- restore an older version of a document (rollback);
- swap two documents of the same user, when the context names only the user.

Include an identifier of the file, and a revision if files are replaced under the same
identifier, and keep it in your database ([security.md § 3](security.md#3-what-aegis-does-not-defend-against)).

### 4.3 Accepted types

| Type | Notes |
|---|---|
| `str` | keys must be `str`; encoded as UTF-8 |
| `bytes` | used verbatim |
| `int` | signed 64-bit range |
| `bool` | distinct from `0` / `1` — the encoding tags types |
| `None` | a legitimate value |

Types must match **exactly**. Subclasses are rejected with `UsageError`: `IntEnum`, `StrEnum`,
Django's `SafeString`. So are `bytearray` and `memoryview`. Convert explicitly with `int(v)`,
`str(v)` or `bytes(v)`.

`float` is **rejected** with `UsageError`: its representation is not stable enough to be a
cryptographic input. So are `dict`, `list`, `tuple`, `set`, `Decimal`, `datetime` and
`Enum`. Convert them yourself, deliberately, so the encoding is visible in your code rather
than guessed by ours.

Ordering does not matter: `{"a": 1, "b": 2}` and `{"b": 2, "a": 1}` produce the same bytes
([file-format.md § 5](file-format.md#5-canonical-serialization-of-context)).

If a payload genuinely has no record to bind to, pass `context={}` explicitly. Omitting the
argument or passing `None` raises `UsageError`: the absence of binding should be a visible
choice in your code, not an accident.

## 5. Key custody: the only knob

The `key` argument is the only thing that changes between the three modes.

### 5.1 Your server holds the key

```python
vault = Vault(key=EnvKey("AEGIS_MASTER_KEY"))                  # base64 in an environment variable
vault = Vault(key=FileKey("/run/secrets/aegis_master_key"))    # base64 in a mounted secret file
vault = Vault(key=BytesKey(secrets_client.get("aegis-kek")))   # 32 bytes you fetched yourself
receipt = vault.seal(src, dst, context={...})
receipt.key   # None — the data key is wrapped inside the file
```

The server can read every file it stores. This is what you want for a normal product where
the application renders, indexes or processes user documents.

All three validate at construction, so a bad key fails at startup with `ConfigurationError`,
never in the middle of an upload. A key must:
- decode to exactly 32 bytes;
- look random: Aegis rejects a key whose bytes are all printable characters, which is what a
  base64-encoded passphrase looks like;
- appear only once across `primary` and `previous`.

`FileKey` accepts the file with or without one trailing newline. In production, prefer
`FileKey` or `BytesKey` to `EnvKey`: environment variables are inherited by child processes and
readable through `/proc` ([security.md § 5.1](security.md#51-choosing-a-key-source)).

### 5.2 Your KMS holds the key

```python
class MyKms:                 # satisfies aegis.KeySource; no import needed at runtime
    key_id: bytes            # 16 bytes identifying the KMS key in use
    capacity: int            # the most bytes wrap() ever returns

    def wrap(self, dek: bytes, aad: bytes) -> bytes: ...
    def unwrap(self, key_id: bytes, payload: bytes, aad: bytes) -> bytes: ...

vault = Vault(key=MyKms(...))
```

- **Aegis draws the data key.** Your source only wraps and unwraps it, and stores up to
  `capacity` bytes in the header.
- **Bind `aad`.** Pass it as the encryption context or additional authenticated data when your
  KMS supports one.
- **Errors from `unwrap`.** Raise `UnknownKek` for a key id you do not manage, and
  `KeyMismatch` when your KMS rejects the payload as an invalid ciphertext.

The master key never enters your process. A worked sketch over AWS KMS is in
[architecture.md § 6](architecture.md#6-the-custody-seam).

### 5.3 The caller holds the key

```python
from aegis import Vault, CallerHeld

vault = Vault(key=CallerHeld())
receipt = vault.seal(src, dst, context={...})
receipt.key      # 32 bytes — give these to the user; Aegis stores nothing

vault.unseal(src, dst, context={...}, key=user_key)   # required in this mode
```

Nothing about the key is persisted. **If the user loses it, the file is gone** — there is no
recovery, by design. A wrong key raises `KeyMismatch`, before any byte of the body is read.

`seal_bytes` raises `UsageError` in this mode: it returns only the blob, so the key would be
lost. Use `seal` or `sealed`, whose `Receipt` carries the key.

### 5.4 Password-derived keys

Aegis 1.0 has no password-based key derivation of its own. If you need one, derive 32 bytes with
Argon2id yourself and use them as a **KEK**:

```python
kek = argon2id(password, salt=user_salt, length=32)   # your Argon2id library and parameters
vault = Vault(key=BytesKey(kek))
```

A KEK wraps a fresh data key for every file. Never use a derived key as a caller key (§ 5.3):
a caller key *is* the data key, and one key would then encrypt every file.

The header's `key_id` lets an attacker who holds a file test password guesses offline at
Argon2id's cost per guess. Choose Argon2id parameters with that in mind.

## 6. Errors, and what to do about each

```
AegisError
├── ConfigurationError    → your startup is wrong. Fix the key or its source; never happens at runtime.
├── FormatError
│   ├── NotAnAegisFile    → this is not an Aegis file. Wrong path, or a double-decrypt.
│   ├── UnsupportedVersion→ written by a newer Aegis. Upgrade the library.
│   └── MalformedHeader   → the header is truncated or inconsistent.
├── UnknownKek            → you are missing a key, not looking at a broken file.
│                           "sealed with key a3f1… (local KEK); you have b7c2…"
├── UnsealFailed          → "wrong context, or corrupted data" — the key is already verified.
│   ├── KeyMismatch       → the key does not belong to this file: a wrong caller key,
│   │                       or a custody record copied from another file.
│   └── TruncatedFile     → the file is provably incomplete. A failed upload, a partial copy.
└── UsageError            → your call is wrong. A float in context, CallerHeld without a key.
```

**Why `UnsealFailed` no longer says "wrong key".** AES-GCM alone cannot tell a wrong key from a
wrong context from a flipped bit. Aegis checks the key first, against the commitment stored in
the header, so a wrong key gets its own error, `KeyMismatch`. Once the body is being read the
key is known to be right, and two causes remain: the context, or the data. A library that
offered `WrongContextError` would still be guessing between those two.

**Truncation, precisely.** A cut that leaves no chunk, a sliver of 1–15 bytes, or ends exactly at
a chunk boundary is provable and raises `TruncatedFile`. A cut inside a chunk looks exactly like
corruption and raises `UnsealFailed`.

**Debugging an `UnsealFailed`, in order:**
1. Is the context byte-identical to what you sealed with — same keys, same types, `42` not `"42"`?
2. Is the file complete? `aegis inspect` prints `size consistent: no` for impossible sizes. A
   complete file is exactly `header + n + 16 × max(1, ceil(n / 65536))` bytes, where the header is
   139 bytes for a local KEK and 73 for caller-held.
3. Has the file been through anything text-oriented — a `TextIOWrapper`, a JSON round-trip, git
   without `-b`?

**Custody mismatches** raise before any decryption:
- a caller-held file opened by a server-custody vault, a server-custody file opened by
  `CallerHeld()`, or `key=` passed to a server-custody vault → `UsageError`;
- a file wrapped by your KMS opened with a local key, or the reverse → `UnknownKek`.

## 7. The streaming trust boundary — read this one

A forward-only `unseal` emits plaintext chunk by chunk. Every chunk it emits is authentic, but
**the file is only proven complete when `unseal()` returns without raising.** If the file was
truncated, your destination already holds a valid prefix of the plaintext when the exception
arrives.

This is inherent to every streaming AEAD over a stream that cannot seek, not a defect of
Aegis. Four ways to live with it:

```python
# 1. Best when the destination is a path: atomic and durable. Nothing survives a failure.
vault.unseal_to_path(src, "out.pdf", context={...})

# 2. Best when the source can seek: truncation is caught at open, before any byte.
with vault.unsealed(open("contract.aegis", "rb"), context={...}) as reader:
    ...

# 3. Small payloads: all-or-nothing by construction.
data = vault.unseal_bytes(blob, context={...})

# 4. Streaming from a non-seekable source to a client: do not act on bytes until the end.
#    An HTTP client may receive a truncated file with a 200 status. If that matters,
#    unseal from a seekable source or to a path first.
```

## 8. Rotating your master key

Three steps, and file bodies are never touched.

```python
vault = Vault(key=EnvKey(primary="AEGIS_KEY_V2", previous=["AEGIS_KEY_V1"]))
```

```bash
# 1. add AEGIS_KEY_V2 to the environment and deploy with previous=[...]
# 2. re-wrap every file
aegis rotate ./bucket --recursive --key-env AEGIS_KEY_V2 --previous-env AEGIS_KEY_V1
# 3. remove AEGIS_KEY_V1 from the environment and from `previous`
```

Rotation unwraps each data key with the old KEK and re-wraps it with the new one. Where it
happens depends on the storage:

- **Local and network filesystems:** `vault.rotate(path)` or `aegis rotate` rewrites the custody
  record — 66 bytes for a local KEK — in place. A small journal makes a power cut mid-write
  recoverable.
- **Object stores** (S3, GCS, Azure Blob) cannot overwrite part of an object. Use
  `vault.rewrap(src, dst)`: it streams a new copy with the record re-wrapped and the body copied
  byte for byte, never decrypted.

**Plan by file count, not by size.** Each file costs a few `fsync`s on a filesystem, or one object
copy on an object store, whatever its size.

During step 2, files in both states are readable, so there is no downtime and no ordering
requirement. A reader that happens to race the rewrite of one file can fail once with
`KeyMismatch` and succeed on retry.

**After a suspected key leak**, rotating is not enough on its own. Backups, object versions and
replicas made before rotation still open with the old key. Purge or re-seal them
([security.md § 5.2](security.md#52-what-rotation-does-and-does-not-do)).

Rotation does not re-encrypt file contents, so it does not help against an attacker who
already extracted the data key of a specific file. It contains the compromise of a *KEK*,
which is the realistic one; re-sealing contains the other.

## 9. CLI

```bash
aegis keygen --force > /run/secrets/aegis_master_key    # a fresh base64 KEK (TTY only without --force)
aegis seal    in.pdf out.aegis --context user_id=42
aegis unseal  out.aegis out.pdf --context user_id=42
aegis inspect out.aegis                                  # header only — never decrypts
aegis rotate  ./bucket --recursive
```

**Keys.** The primary KEK comes from `--key-env NAME` (default `AEGIS_MASTER_KEY`) or
`--key-file PATH`. Older KEKs come from `--previous-env NAME` and `--previous-file PATH`, which
may repeat. Key bytes never appear on the command line or on a standard stream:

```bash
aegis seal   in.pdf out.aegis --caller-held --key-out user.key --context user_id=42   # user.key is created 0600
aegis unseal out.aegis out.pdf --key-in user.key --context user_id=42
```

**Context.** `--context key=value` is always a `str`. The typed forms reproduce every other
accepted type:

| Option | Value type |
|---|---|
| `--context-int user_id=42` | `int` |
| `--context-hex tenant=0a1b` | `bytes` |
| `--context-bool archived=false` | `bool` |
| `--context-null parent` | `None` |

Mixing up `--context` and `--context-int` is the most likely cause of an `UnsealFailed` from
the command line.

`aegis inspect` is the fastest way to understand the format before writing any code:

```
$ aegis inspect contract.aegis
file              contract.aegis
version           1
suite             1  (AES-256-GCM / HKDF-SHA256 / STREAM / 64 KiB)
custody           local KEK
key_id            a3f1c0de9b7742e1…
header            139 bytes
size consistent   yes
chunks            1 632               (from the file size — not authenticated)
plaintext         106 954 752 bytes   (from the file size — not authenticated)
```

`inspect` never decrypts and needs no key. It reports sizes derived from the file's length and
says when that length is impossible for a valid container. On standard input it counts the bytes
to the end.

**`rotate --recursive`.** Caller-held files, non-Aegis files and files wrapped by a KMS each get
one report line and do not fail the run; the CLI holds no `KeySource`, so rotate those from
Python. Per-file errors are reported, the run continues, and a summary ends the output.
`--fail-fast` stops at the first error.

Exit codes: `0` ok, `1` unseal failed (including `KeyMismatch` and `TruncatedFile`), `2` usage,
`3` format, `4` unknown KEK, `5` configuration. A recursive run exits with the code of its first
failure.

## 10. Django and other web frameworks

The Django adapter is planned for V2 ([dev/v2-django.md](dev/v2-django.md)). Until then, the readers of
§ 3.4 connect Aegis to any framework with constant memory. The examples below are sketches of
that wiring; authorization is always yours.

### 10.1 Storing an upload (Django)

```python
from django.core.files import File
from django.core.files.storage import default_storage

def store(upload, doc):
    context = {"document_id": str(doc.uuid), "revision": doc.revision}
    sealed = vault.sealed(upload, context=context)
    return default_storage.save(f"docs/{doc.uuid}.aegis", File(sealed))
```

Name stored objects with an opaque identifier, not the user's filename: storage keys and object
metadata are not encrypted. Keep the original name in a model field if you need it.

### 10.2 Serving a file under WSGI (Django)

```python
from django.http import FileResponse
from django.shortcuts import get_object_or_404

def download(request, pk):
    doc = get_object_or_404(Document, pk=pk, owner=request.user)      # authorization is yours
    context = {"document_id": str(doc.uuid), "revision": doc.revision}
    reader = vault.unsealed(default_storage.open(doc.blob_name, "rb"), context=context)
    return FileResponse(reader, as_attachment=True, filename=doc.filename,
                        content_type=doc.content_type)
```

When the storage file is seekable, `FileResponse` takes `Content-Length` from the reader's
authenticated size, and a truncated file fails before the response starts.

### 10.3 Serving a file under ASGI (Django)

Under ASGI, Django consumes a *synchronous* response iterator completely before sending it — its
documentation says so, and `FileResponse` is no exception. A 10 GB file would sit in memory.
Give Django an asynchronous iterator that reads one chunk per thread hop:

```python
from asgiref.sync import sync_to_async
from django.http import StreamingHttpResponse

async def aiter_chunks(reader, size=65536):
    read = sync_to_async(reader.read)
    try:
        while chunk := await read(size):
            yield chunk
    finally:
        await sync_to_async(reader.close)()

def open_plaintext(doc):
    context = {"document_id": str(doc.uuid), "revision": doc.revision}
    return vault.unsealed(default_storage.open(doc.blob_name, "rb"), context=context)

async def download(request, pk):
    doc = ...                                                            # look up and authorize
    reader = await sync_to_async(open_plaintext)(doc)                    # storage I/O off the loop
    response = StreamingHttpResponse(aiter_chunks(reader), content_type=doc.content_type)
    if reader.size is not None:
        response["Content-Length"] = str(reader.size)
    return response
```

### 10.4 FastAPI and Starlette

```python
from fastapi.responses import StreamingResponse

@app.get("/documents/{doc_id}")
def download(doc_id: str):
    doc = ...                                                            # look up and authorize
    reader = vault.unsealed(open(doc.path, "rb"), context={"document_id": doc_id})
    headers = {"Content-Length": str(reader.size)} if reader.size is not None else {}
    return StreamingResponse(reader.chunks(), media_type=doc.content_type, headers=headers)
```

Starlette runs a synchronous iterator in its thread pool, one chunk at a time. Pass
`reader.chunks()`, not the reader itself: iterating a binary file object yields *lines*, and a
file without newlines is a single line.

### 10.5 S3 with boto3

```python
s3.upload_fileobj(vault.sealed(open("video.mp4", "rb"), context=context), bucket, key)

body = s3.get_object(Bucket=bucket, Key=key)["Body"]      # not seekable: a forward-only reader
with vault.unsealed(body, context=context) as reader, open("video.mp4", "wb") as out:
    shutil.copyfileobj(reader, out, 65536)
```

boto3 buffers multipart parts itself; memory stays bounded by its transfer settings, not by the
file size. A forward-only download has the trust boundary of § 7 — prefer `unseal_to_path`
when the destination is a file.

## 11. Pitfalls checklist

- [ ] The key comes from a mounted secret file, a secret manager or a KMS in production — never
      from the repository, never from `settings.py`, never from the database that holds the
      ciphertext.
- [ ] The context is built from immutable, reproducible fields, and names the file, not only its
      owner.
- [ ] `context` values have the same **types** at seal and unseal time (`42` ≠ `"42"`).
- [ ] Files are opened in **binary** mode (`"rb"` / `"wb"`). A `TextIOWrapper` will corrupt
      ciphertext.
- [ ] `unseal_to_path` or a seekable `unsealed` reader is used wherever truncation would matter.
- [ ] Nothing acts on forward-only `unseal` output before the call returns.
- [ ] `receipt.key` is not logged, not stored server-side in caller-held mode, and not put
      in a URL.
- [ ] The blob is stored as **binary** (`BinaryField`, `bytea`, a bucket object) — not
      base64 in a text column, which would undo the 0.024 % overhead.
- [ ] Storage names are opaque identifiers, not user filenames.
- [ ] A `previous=[...]` key list exists in the deployment before you need to rotate.
- [ ] Under ASGI, responses stream through an asynchronous iterator (§ 10.3).

## 12. FAQ

**Can I encrypt a database column with this?** Technically yes via `seal_bytes`, but Aegis
is shaped for files. For short values consider whether an application-level solution with
searchability is what you actually need.

**Can I search or index encrypted files?** No. Aegis is not searchable encryption. Index
the metadata you keep in cleartext.

**Can I read part of a file without decrypting all of it?** Yes, when the source is seekable:
`vault.unsealed(src, …)` supports `seek()` and decrypts only the chunks a read covers, after
authenticating the last one.

**Can two servers share a vault?** Yes — they need the same KEK, or access to the same KMS key.

**Is the output deterministic?** No, and it must not be: the data key and the salt are random
per file. Sealing the same file twice yields different bytes. Compare plaintexts, not
ciphertexts.

**Does it work with S3 / GCS?** Yes. Upload with `vault.sealed(...)` as the readable body, and
download through `vault.unsealed(...)` (§ 10.5). Rotation there uses `vault.rewrap`, because an
object cannot be edited in place (§ 8).

**Does it work with a KMS?** Yes: implement `KeySource` (§ 5.2). The header stores whatever your
KMS returns, up to 4 KiB.

**How much larger are my files?** 16 bytes per 64 KiB — about 0.024 % — plus the header: 139
bytes for a local KEK, 73 for caller-held, 91 plus your source's capacity for a KMS.

**Why not just use Fernet?** It loads the whole file into memory, has no envelope
encryption, no associated data, no rotation story, and base64-encodes its output (+33 %).

**Can I compress first?** You can, and Aegis will not do it for you: compressing before
encrypting leaks information about the plaintext through the ciphertext length. If you
understand that trade-off for your data, compress before calling `seal`.
