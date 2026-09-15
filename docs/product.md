# Aegis — what it is

**Aegis is a Python library for encrypting files at rest, designed so that a developer who
is not a cryptographer cannot hold it wrong.**

It is a standalone open source project. It has no dependency on, coupling to, or knowledge
of any consuming application.

---

## 1. The problem it solves

A backend developer storing user files knows they should encrypt them. They know "AES is
the right one". They copy `Fernet` from a blog post, and then hit the question that
actually blocks them:

> Where do I put the key?

Every wrong answer to that question is a real system in production today: the key next to
the ciphertext, the key in the same database row, the key hard-coded in settings, the key
in the repository. The algorithm was never the hard part.

Aegis answers that question — once, in the constructor — and then asks the developer to
stop thinking about cryptography.

## 2. Who it is for

A Python backend developer (Django or FastAPI), solo or on a small team, building a product
that stores user files. They know what AES is. They do not know what happens when a nonce
repeats, and they have never heard of envelope encryption.

**Success criterion:** they adopt Aegis in an afternoon, without reading up on cryptography,
and the result is correct by construction.

Aegis is *not* aimed at cryptographers building protocols. They should use `cryptography`
directly and will find Aegis' opinions constraining. That is the intended trade.

## 3. What Aegis provides

| Capability | What it means in practice |
|---|---|
| **Envelope encryption** | A fresh data key per file, wrapped by your master key. You never handle key bytes. |
| **Streaming, constant memory** | A 10 GB file uses the same RAM as a 10 KB one. No `.read()` of the whole file. |
| **A versioned, self-describing format** | Files carry their version and suite. Frozen test vectors guarantee today's file opens in five years. |
| **Binary output, ~0.024 % overhead** | 16 bytes per 64 KiB chunk. A 100 MB file becomes 100.02 MB — not 133 MB, as base64 would make it. |
| **Mandatory context binding** | Every blob is cryptographically bound to its record. User 42's ciphertext will not open as user 99. |
| **Key rotation in minutes** | Rotating re-wraps an 80-byte custody block per file. File bodies are never re-encrypted or even read. |
| **Truncation detection** | Cutting a file short is detected, not silently accepted as a shorter file. |
| **A precise error hierarchy** | Actionable exceptions. No blanket `except Exception`, ever, anywhere in the library. |
| **Secrets that resist logging** | `repr()` of every object that touches key material is redacted. No exception message contains a key or plaintext. |

Four operations, and nothing else:

```python
vault.seal(src, dst, context=...)          # streaming — the main path
vault.unseal(src, dst, context=...)
vault.seal_bytes(data, context=...)        # sugar when you already hold the bytes
vault.unseal_bytes(blob, context=...)
```

Plus one safety helper, `vault.unseal_to_path()`, which writes atomically.

Optional, behind extras: a Django field (`aegis[django]`) and a CLI (`aegis[cli]`).

## 4. What Aegis deliberately does not do

Refusals are as much a part of the product as features. Each of these is a decision with a
reason, recorded in [decisions.md](decisions.md).

| Not in Aegis | Why |
|---|---|
| **Compression** | Compressing before encrypting leaks plaintext through ciphertext length (the CRIME class of attack). If you accept that risk for your data, compress before calling `seal`. |
| **Plaintext hashing / blockchain anchoring** | Business logic of the consumer, not of a crypto library. Use `hashlib`. |
| **Bundled KMS providers** (AWS KMS, Vault, HSM) | Aegis defines the extension point — two functions. Concrete providers live outside the core, so the core keeps one dependency. |
| **A legacy-format reader** | There is no production user data in another format to preserve. Every byte of compatibility code is a byte of attack surface. |
| **Browser-side / end-to-end encryption** | Would require a TypeScript or WASM implementation kept byte-for-byte in sync with this one. Out of 1.0. |
| **An async API** | Encryption is CPU-bound. `async` buys nothing on its own here and would double the public surface and the test matrix. Run `seal` in a thread or process pool. |
| **Password-derived keys** | 1.0 takes 32 bytes of high-entropy key material, not a passphrase. A password KDF (Argon2id) is a post-1.0 candidate, not an afternoon's work. |
| **Generic encryption of arbitrary values** | Aegis seals *files and byte blobs*. It is not a general-purpose cipher, and the `seal`/`unseal` vocabulary exists partly to discourage that use. |

## 5. How it compares

| Alternative | Where it wins | Why Aegis exists anyway |
|---|---|---|
| **`cryptography` (raw `AESGCM`)** | Maximum control | Leaves every hard decision to you: nonce management, chunking, key storage, AAD. That is exactly the set of decisions that go wrong. |
| **`Fernet`** | Simple, in the same package | Loads the whole plaintext into memory, has no envelope encryption, no AAD, no rotation story, and base64-encodes its output (+33 %). |
| **`age` / pyrage** | The best security story — zero original cryptography, interoperable with the `age` CLI | Its X25519 identity model distorts the ergonomics exactly at key custody, which is the heart of this library, and rules out a custom AAD. Adds a native wheel. |
| **Google Tink `StreamingAEAD`** | Audited, keysets and rotation built in | Imports Tink's conceptual weight — keysets, templates, primitives — against our simplicity requirement. The product would become "an easier way to use Tink", which is a different product. |
| **Cloud KMS SDKs** | Keys never leave the HSM | Solve key custody but not file format, streaming, or per-record binding. Aegis is complementary: implement `KeySource` over your KMS. |

## 6. Compatibility promise

- **Format version is independent of library version.** A file written by Aegis 1.0 opens
  in Aegis 9.x. That is the promise the frozen test vectors defend.
- **Library versioning is [SemVer](https://semver.org).** The public API is what
  `aegis/__init__.py` exports and what these documents describe. Anything else is private
  and may change in a patch release.
- **A new format version is never written by default.** If a v2 format is ever introduced,
  writing it requires an explicit opt-in; reading v1 keeps working.
- **Reading a future version fails loudly** with `UnsupportedVersion` and the message
  "upgrade aegis" — never with a partial or garbage decryption.
- **Python support** follows the [SPEC 0](https://scientific-python.org/specs/spec-0000/)
  style: 3.10+ at 1.0; a minor Python drop is a minor Aegis release, announced one release
  ahead.

## 7. Project shape

- **License:** MIT (see [`LICENSE`](../LICENSE)).
- **Dependencies:** one — `cryptography`. Extras add `django` and `click` (or `typer`).
- **Distribution:** PyPI as `aegis-voynan` (imported as `aegis`,
  [ADR-0018](decisions.md#adr-0018-distribute-as-aegis-voynan-import-as-aegis)). Pure Python;
  no native wheels of our own.
- **Status:** pre-1.0, pre-implementation. See [roadmap.md](roadmap.md).
- **Security reports:** see [security.md § Reporting a vulnerability](security.md#8-reporting-a-vulnerability).

## 8. The honest sentence

> Aegis protects against a database dump and a storage bucket leak. It does **not** protect
> against a server compromised at runtime — in that scenario the KEK is in process memory.
> For that threat you need client-side end-to-end encryption, which Aegis does not do.

That paragraph belongs at the top of the README, not in a footnote. A developer who is not
a cryptographer needs someone to state it plainly, and stating it is what separates this
library from one more AES wrapper on PyPI.
