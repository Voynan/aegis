# Security

What Aegis defends against, what it does not, and how to report a problem.

The honest paragraph first, because a developer who is not a cryptographer needs someone to
state it plainly:

> **Aegis protects against a database dump and a storage bucket leak. It does not protect
> against a server compromised at runtime** — in that scenario the KEK is in process memory.
> For that threat you need client-side end-to-end encryption, which Aegis does not do.

---

## 1. Threat model

**Assets:** the plaintext of sealed files, and the key material that opens them.

**In scope.** An adversary who obtains any subset of:

| The adversary gets | Aegis' claim |
|---|---|
| The storage bucket / disk / backup of sealed files | Learns nothing but file sizes (± 0.03 %), file count, and which KEK id sealed each one. |
| A database dump containing blobs and metadata | Same. Blobs contain no context, no user id, no plaintext-derived value. |
| Both of the above, plus write access | Cannot produce a blob that decrypts to anything. Every mutation raises. |
| One user's blob, wanting to open it as another user | Fails: the context binds the blob to its record. |
| Unlimited ciphertexts sealed under one KEK | No degradation: a fresh HKDF salt per file removes the birthday bound on wraps. |

**Assumed of the environment.** `os.urandom` is a sound CSPRNG; the `cryptography` package
and its OpenSSL are correct; the host is not actively executing attacker code while Aegis
runs.

## 2. Guarantees

| Property | Mechanism |
|---|---|
| **Confidentiality** at rest | AES-256-GCM under a per-file data key |
| **Integrity and authenticity** | GCM tag on every 64 KiB chunk; every header byte is authenticated or pinned to zero ([file-format.md § 4.4](file-format.md#44-every-header-byte-is-authenticated)) |
| **Binding to a record** | The caller's `context` is the AEAD associated data |
| **Order and completeness** | Chunk counter in the nonce; final-chunk marker in the nonce |
| **Truncation detection** | A stream ending without an authenticated final chunk raises `TruncatedFile` |
| **Key separation** | The KEK only ever encrypts a 32-byte data key, never file data |
| **Blast-radius containment** | Per-file data key: compromising one file's DEK compromises exactly that file |
| **Nonce uniqueness** | Per-file random DEK **and** per-file random 7-byte nonce prefix — reuse needs both to collide |
| **Forward compatibility** | Version and suite bytes; unknown values raise rather than guess |

**The stated adversarial invariant**, tested directly
([tests.md § 4.2](tests.md#42-the-adversarial-suite)):

> No mutation of a sealed file ever yields plaintext. It either raises, or produces nothing.

## 3. What Aegis does not defend against

Stated plainly, because a security library that is vague about its limits is worse than
none.

- **A compromised running server.** The KEK is in process memory whenever the application
  can read files. Code execution on that host beats Aegis. Nothing at rest can fix this.
- **A memory-dump adversary.** Python `bytes` are immutable and the interpreter copies
  freely; we do not claim to zeroize key material and would be lying if we did.
- **Traffic and size analysis.** Ciphertext length reveals plaintext length to within
  0.03 %. If file size is sensitive, pad before sealing.
- **Metadata.** Filenames, paths, timestamps, row counts and access patterns are yours to
  protect. `kek_id` is deliberately in cleartext.
- **A malicious or coerced operator.** Whoever holds the KEK can read every file. Use
  caller-held custody if the server must not be able to.
- **Key loss.** There is no recovery, no escrow, no backdoor. In caller-held mode a lost key
  is a lost file.
- **Side channels.** We rely on `cryptography`/OpenSSL for constant-time AES-GCM. Aegis
  adds no secret-dependent branching of its own, but makes no timing claim about the host.
- **Denial of service.** A caller who unseals a hostile 256 TiB file spends 256 TiB of I/O.
  Enforce your own size limits before calling.
- **Anything about the plaintext's own security** — Aegis seals bytes; whether those bytes
  should exist is your decision.

## 4. Cryptographic construction

No new cryptography is invented here. The pieces are standard and the composition is a
published construction.

| Piece | Choice | Standard |
|---|---|---|
| AEAD | AES-256-GCM, 96-bit nonce, 128-bit tag | NIST SP 800-38D |
| Segmented encryption | STREAM | Hoang, Reyhanitabar, Rogaway, Vizár (CRYPTO 2015) |
| Key derivation for the wrap | HKDF-SHA256, `info=b"aegis-dek-wrap-v1"` | RFC 5869 |
| Key fingerprint | SHA-256, truncated to 128 bits | FIPS 180-4 |
| AAD hashes | SHA-256 with domain-separation labels `aegis-hdr-v1\x00`, `aegis-ctx-v1\x00` | FIPS 180-4 |
| Randomness | `os.urandom` | OS CSPRNG |
| Primitive implementation | `cryptography` (OpenSSL) | — |

Details, including why an all-zero nonce is safe for the DEK wrap, are in
[file-format.md § 3](file-format.md#3-key-hierarchy).

### 4.1 The accepted risk

**The chunk framing is our code.** STREAM is a published construction, but this
implementation of it — the nonce layout, the final-chunk marker, the AAD composition — is
ours. A subtle bug there is our bug, and it is the single largest risk in the project.

Mitigations, all of them mandatory before 1.0:

1. Frozen known-answer vectors, generated once and never regenerated
   ([tests.md § 3](tests.md#3-layer-1--frozen-vectors-kat)).
2. A property-based adversarial suite over arbitrary mutations
   ([tests.md § 4.2](tests.md#42-the-adversarial-suite)).
3. 100 % branch coverage on `stream.py` and `format.py`, non-negotiable.
4. `stream.py` kept small enough to audit in one sitting.
5. **A public review request before 1.0** — the release is not cut until independent eyes
   have looked at `stream.py` and `file-format.md`. When to request it relative to the M4
   freeze is open ([Q19](architecture.md#16-open-questions)).

## 5. Key management

Aegis holds no opinion about where your KEK is stored beyond this: **not next to the
ciphertext.** The whole point of envelope encryption is that stealing the blobs is not
enough.

**Do**

- Keep the KEK in the environment, a secret manager, or a KMS — a different trust domain
  from the blob storage and from the database.
- Generate it with a CSPRNG: `os.urandom(32)`, or `aegis keygen`.
- Deploy with `previous=[...]` populated *before* you need to rotate, so rotation is a
  configuration change rather than an emergency.
- Rotate on a schedule, and immediately on suspicion.

**Do not**

- Commit it, put it in `settings.py`, or store it in the same database as the ciphertext.
- Derive it from a password without a real KDF (Aegis 1.0 provides none).
- Reuse one KEK across environments — a staging leak should not open production files.
- Log it. `repr()` is redacted throughout, but a `print(os.environ)` is still yours to
  avoid.

**What rotation does and does not do.** `aegis rotate` re-wraps each file's data key under
the new KEK. It contains the compromise of a *KEK*. It does not re-encrypt file bodies, so
an attacker who already extracted one file's data key keeps that one file. Full re-keying
means unsealing and re-sealing, which Aegis can do but does not call rotation.

## 6. The streaming trust boundary

`unseal` authenticates every chunk before emitting it, but a file is only proven *complete*
when the call returns. A consumer acting on partial output may act on
truncated-but-authentic data.

This is inherent to streaming AEAD — the alternative is buffering the entire plaintext,
which defeats the purpose. Aegis' answer is to make the safe path the convenient one:

- `unseal_to_path()` writes to a temporary file, `fsync`s, and `os.replace`s only after a
  clean return. On failure, nothing survives. Whether the rename itself survives a crash is
  open ([Q21](architecture.md#16-open-questions)).
- `unseal_bytes()` is all-or-nothing by construction.
- Streaming directly to an HTTP client means the client may receive a truncated body under
  a `200` status. If that matters, unseal to a path first.

## 7. Secret hygiene in the library

- `repr()` of `Receipt`, `Vault`, `CustodyBlock` and every `KeySource` renders key material
  as `<redacted 32 bytes>`. This defends against the most common production leak, which is
  not cryptographic — it is logging.
- No exception message, log record or `str()` contains a key, a data key, or plaintext.
  Enforced by a test.
- Logging goes through `logging.getLogger("aegis")` with a `NullHandler`. The library never
  configures the host's logging.
- No blanket `except Exception` anywhere in the library.

## 8. Reporting a vulnerability

**Do not open a public issue for a security problem.**

- Use GitHub's **Report a vulnerability** (private security advisory) on this repository.
- Include a description, affected versions, and a reproduction if you have one.
- Expect an acknowledgement within **72 hours** and an assessment within **7 days**.
- Coordinated disclosure: we aim to ship a fix within **90 days** and will credit you in
  the advisory unless you prefer otherwise.

**In scope:** anything that breaks a guarantee in § 2 — recovering plaintext without the
key, forging or mutating a file that decrypts, key material leaking into a log or a
`repr()`, a nonce reuse, a parsing flaw reachable from untrusted input.

**Out of scope:** everything in § 3, plus vulnerabilities in `cryptography` or OpenSSL
(report those upstream) and findings that require an already-compromised host.

## 9. Supply chain

- One runtime dependency in the core: `cryptography`. Extras add `django` and the CLI
  framework.
- Dependencies are floored, not pinned, so security updates reach users without a release
  from us. CI pins for reproducibility.
- Releases are built and published from CI with **trusted publishing** (OIDC) — no
  long-lived PyPI token exists.
- Artifacts carry provenance attestations; tags are signed.
- No native code of our own; wheels are pure Python.

## 10. Audit status

**Not audited.** No third-party review has taken place. Before 1.0, § 4.1's public review
request is a release blocker; that is a review, not an audit, and the README will say so in
those words. If you need an audited library today, `age` and Tink are the honest
recommendations.
