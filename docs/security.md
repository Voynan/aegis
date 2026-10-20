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
| The storage bucket / disk / backup of sealed files | Learns file sizes (± 0.03 %), file count, and each file's custody mode and key id — nothing about content. |
| A database dump containing blobs and metadata | Same. Blobs contain no context, no user id, no plaintext-derived value. |
| Both of the above, plus write access | Cannot forge, alter, reorder or truncate content without detection: every such change raises. **Can** delete files, and can substitute another genuine blob sealed under an equal context — see § 3. |
| One user's blob, wanting it opened as another user | Fails when the context names the user: the context is bound into every chunk. |
| Unlimited files sealed under one key | No degradation: every file has its own 256-bit salt, body key and nonce prefix. |
| A key source that repeats data keys | Cannot cause nonce reuse. Aegis draws every DEK itself, and the per-file salt would keep body keys distinct even if a DEK repeated. |
| A ciphertext crafted to decrypt under two keys | Rejected: the header commits to exactly one key, checked before the body. |

**Assumed of the environment.** `os.urandom` is a sound CSPRNG; the `cryptography` package
and its OpenSSL are correct; the host is not actively executing attacker code while Aegis
runs.

## 2. Guarantees

| Property | Mechanism |
|---|---|
| **Confidentiality** at rest | AES-256-GCM under a per-file body key, derived from a per-file DEK and a per-file salt |
| **Integrity and authenticity** | GCM tag on every 64 KiB chunk; every header byte is authenticated, a key-derivation input, or pinned by an exact parsing rule ([file-format.md § 4.4](file-format.md#44-every-header-byte-is-authenticated)) |
| **Key commitment** | A 32-byte HKDF commitment in the header, checked in constant time before any chunk: a header opens under exactly one DEK |
| **Binding to a record** | The caller's `context` is in the associated data of every chunk |
| **Order and completeness** | Chunk counter in the nonce; final-chunk flag in the nonce |
| **Truncation detection** | A body that ends early never decrypts as complete. `TruncatedFile` where the reader can prove a cut; `UnsealFailed` where a cut inside a chunk is indistinguishable from corruption ([file-format.md § 6.2](file-format.md#62-unsealing)). Seekable readers detect truncation before returning any byte |
| **Key separation** | The KEK only wraps DEKs; a DEK only seeds its file's key schedule |
| **Blast-radius containment** | Per-file data key: compromising one file's DEK compromises exactly that file |
| **Nonce uniqueness** | Body key and nonce prefix derived per file from the DEK and a 256-bit salt; DEKs are drawn by Aegis, never by a key source |
| **Forward compatibility** | Magic, version and suite checked first; unknown values raise rather than guess |

**The stated adversarial invariant**, tested directly
([tests.md § 4.2](tests.md#42-the-adversarial-suite)):

> No mutation of a sealed file ever yields plaintext. It either raises, or produces nothing.

## 3. What Aegis does not defend against

Stated plainly, because a security library that is vague about its limits is worse than
none.

- **A compromised running server.** The KEK, or access to the KMS, is in the process whenever the
  application can read files. Code execution on that host beats Aegis. Nothing at rest can fix
  this.
- **A memory-dump adversary.** Python `bytes` are immutable and the interpreter copies freely; we
  do not claim to zeroize key material and would be lying if we did.
- **Traffic and size analysis.** Ciphertext length reveals plaintext length to within 0.03 %. If
  file size is sensitive, pad before sealing.
- **Metadata.** Filenames, paths, timestamps, row counts and access patterns are yours to
  protect. `key_id` and the custody mode are deliberately in cleartext.
- **Substitution and rollback.** Aegis proves that a blob is genuine and bound to its context;
  it cannot know whether it is the *current* blob for that context. An attacker with write
  access can put back an older version sealed under the same context, or swap two files whose
  contexts are equal — two documents of one user, when the context names only the user.

  The remedy is in the context: include an identifier that changes with every upload or version,
  such as `{"document_id": …, "revision": …}`, and keep it in your database
  ([usage.md § 4](usage.md#4-context-the-one-thing-to-get-right)).
- **A malicious or coerced operator.** Whoever holds the KEK can read every file. Use caller-held
  custody if the server must not be able to.
- **Key loss.** There is no recovery, no escrow, no backdoor. In caller-held mode a lost key is a
  lost file.
- **Side channels.** We rely on `cryptography`/OpenSSL for constant-time AES-GCM. Aegis adds no
  secret-dependent branching of its own and compares the commitment in constant time, but makes
  no timing claim about the host.
- **Denial of service.** A caller who unseals a hostile 256 TiB file spends 256 TiB of I/O.
  Enforce your own size limits before calling; `aegis.inspect` reads the size without a key.
- **Anything about the plaintext's own security** — Aegis seals bytes; whether those bytes should
  exist is your decision.

## 4. Cryptographic construction

No new cryptography is invented here. The pieces are standard and the composition follows
published, deployed designs.

| Piece | Choice | Standard / precedent |
|---|---|---|
| AEAD | AES-256-GCM, 96-bit nonce, 128-bit tag | NIST SP 800-38D |
| Segmented encryption | STREAM, Tink's segment nonce layout | Hoang, Reyhanitabar, Rogaway, Vizár (CRYPTO 2015) |
| Per-file key schedule | HKDF-SHA256 from the DEK and a 256-bit salt: body key and nonce prefix | RFC 5869; the pattern of age's payload key and Tink's AES-GCM-HKDF streaming |
| Key commitment | HKDF-SHA256 output stored in the header, compared in constant time | the AWS Encryption SDK's committing suites; Albertini et al., *How to Abuse and Fix Authenticated Encryption Without Key Commitment* (USENIX Security 2022) |
| Local DEK wrap | AES-256-GCM under HKDF-SHA256(KEK, salt), all-zero nonce | RFC 5869, NIST SP 800-38D |
| Key fingerprint | SHA-256, truncated to 128 bits | FIPS 180-4 |
| AAD hashes | SHA-256 with domain-separation labels `aegis-hdr-v1\x00`, `aegis-ctx-v1\x00`, `aegis-custody-v1\x00` | FIPS 180-4 |
| Randomness | `os.urandom`, drawn in `vault.py` only | OS CSPRNG |
| Primitive implementation | `cryptography` (OpenSSL) | — |

Details, including why an all-zero nonce is safe for the DEK wrap, are in
[file-format.md § 3](file-format.md#3-key-hierarchy).

### 4.1 The accepted risk

**The composition is our code.** STREAM, HKDF and key commitment are published constructions,
but this implementation of them — the nonce layout, the final-chunk flag, the key schedule, the
AAD composition — is ours. A subtle bug in `stream.py` or `envelope.py` is our bug, and it is the
single largest risk in the project.

Mitigations, all of them mandatory before 1.0:

1. Frozen known-answer vectors, generated once and never regenerated
   ([tests.md § 3](tests.md#3-layer-1--frozen-vectors-kat)).
2. A property-based adversarial suite over arbitrary mutations
   ([tests.md § 4.2](tests.md#42-the-adversarial-suite)).
3. 100 % branch coverage on `stream.py`, `envelope.py` and `format.py`, non-negotiable.
4. `stream.py` and `envelope.py` kept small enough to audit in one sitting.
5. **Public review before the format freezes.** Review of [file-format.md](file-format.md) is
   requested now, before M2; review of `stream.py` and `envelope.py` when M2 closes; feedback
   triage gates the M4 freeze; M8 is the final pass
   ([ADR-0037](decisions.md#adr-0037-smaller-resolutions), Q19). The release is not cut until
   independent eyes have looked at all three.

## 5. Key management

Aegis holds no opinion about where your KEK is stored beyond this: **not next to the
ciphertext.** The whole point of envelope encryption is that stealing the blobs is not enough.

### 5.1 Choosing a key source

| Source | Where the master key lives | What can expose it |
|---|---|---|
| **External custody** — a `KeySource` over a KMS or HSM | never in your process | only per-file DEKs pass through memory; a file-read bug in the application does not reveal the master key |
| **`FileKey`** — a mounted secret file | process memory; the file | an attacker who can read arbitrary files and knows the path |
| **`BytesKey`** — bytes you fetched, e.g. from a secret manager at startup | process memory | the channel you fetched it through |
| **`EnvKey`** — an environment variable | process memory; the environment | see below |

The environment is the leakiest of these channels:
- Every child process inherits it, unless you pass `env=` to `subprocess`. Apps that store files
  are the ones that run ImageMagick, ffmpeg or a virus scanner.
- It is readable through `/proc/<pid>/environ` by anything with the process's privileges. proc(5)
  documents that this file keeps the *initial* environment, so deleting the variable at runtime
  does not remove it there. A path-traversal bug can therefore read the KEK without executing any
  code.
- Crash reporters, orchestrator manifests and `docker inspect` routinely copy environment
  variables.

**Recommendation:** external custody where you have a KMS; otherwise `FileKey` (Docker
`/run/secrets`, a Kubernetes secret volume, systemd credentials) or `BytesKey`. Reserve `EnvKey`
for development and simple deployments, knowing the list above.

**Do**

- Keep the master key in a different trust domain from the blob storage and from the database.
- Generate it with a CSPRNG: `aegis keygen`, or `os.urandom(32)`. Aegis rejects keys that look
  like text or have too little variety
  ([ADR-0029](decisions.md#adr-0029-local-key-sources-envkey-filekey-and-byteskey-with-an-entropy-floor)).
- Deploy with `previous=[...]` populated *before* you need to rotate, so rotation is a
  configuration change rather than an emergency.
- Rotate on a schedule, and immediately on suspicion — then deal with old copies (§ 5.2).
- With `EnvKey`, pass an explicit `env=` to every subprocess you start.

**Do not**

- Commit it, put it in `settings.py`, or store it in the same database as the ciphertext.
- Derive it from a password without a real KDF. When you do derive one with Argon2id, use the
  result as a KEK (`BytesKey`), never as a caller key
  ([usage.md § 5.4](usage.md#54-password-derived-keys)).
- Reuse one KEK across environments — a staging leak should not open production files.
- Log it. `repr()` is redacted throughout, but a `print(os.environ)` is still yours to avoid.

### 5.2 What rotation does and does not do

`aegis rotate` re-wraps each file's data key under the new key and leaves the body untouched.

- **It contains a KEK compromise only for copies the attacker does not hold.** A backup, an
  object version, a replica or a cache made before rotation still opens with the old KEK. The DEK
  it yields also opens the current body, because rotation never changes the DEK. After a
  suspected KEK leak: rotate, then purge or re-seal every older copy. If old copies may already
  be in the attacker's hands, re-seal (new DEK) the files that matter.
- **It does not help after a DEK leak.** An attacker who extracted one file's data key keeps that
  file until it is re-sealed. Full re-keying means unsealing and re-sealing —
  `new_vault.seal(old_vault.unsealed(src, …), dst, …)` — which Aegis can do but does not call
  rotation.

## 6. The streaming trust boundary

A forward-only `unseal` authenticates every chunk before emitting it, but a file is only proven
*complete* when the call returns. A consumer acting on partial output may act on
truncated-but-authentic data.

This is inherent to streaming AEAD over a stream that cannot seek — the alternative is buffering
the entire plaintext, which defeats the purpose. Aegis' answer is to make the safe path the
convenient one:

- `unsealed()` over a **seekable** source authenticates the final chunk before returning any byte
  ([file-format.md § 6.3](file-format.md#63-random-access)). Truncation cannot reach your code;
  corruption in the middle still raises when that chunk is read.
- `unseal_to_path()` writes to a temporary file, `fsync`s, and `os.replace`s only after a clean
  return, then syncs the directory on POSIX. On failure, nothing survives.
- `unseal_bytes()` is all-or-nothing by construction.
- Streaming directly to an HTTP client from a non-seekable source means the client may receive a
  truncated body under a `200` status. If that matters, unseal from a seekable source or to a
  path first.

## 7. Secret hygiene in the library

- `repr()` of `Receipt`, `Vault`, every key source and both readers renders key material as
  `<redacted 32 bytes>`. This defends against the most common production leak, which is not
  cryptographic — it is logging.
- No exception message, log record or `str()` contains a key, a data key, a derived key, or
  plaintext. Enforced by a test.
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

**In scope:** anything that breaks a guarantee in § 2. That includes:
- recovering plaintext without the key;
- forging or mutating a file so that it decrypts;
- a file that opens under two keys;
- key material leaking into a log or a `repr()`;
- a nonce reuse;
- a parsing flaw reachable from untrusted input.

**Out of scope:** everything in § 3, plus vulnerabilities in `cryptography` or OpenSSL (report
those upstream) and findings that require an already-compromised host.

## 9. Supply chain

- One runtime dependency in the core: `cryptography`. The `[cli]` extra adds `click`. The Django
  adapter is planned for V2 ([dev/v2-django.md](dev/v2-django.md)).
- Dependencies are floored, not pinned, so security updates reach users without a release
  from us. CI pins for reproducibility.
- Releases are built and published from CI with **trusted publishing** (OIDC) — no
  long-lived PyPI token exists.
- Artifacts carry provenance attestations; tags are signed.
- No native code of our own; wheels are pure Python.

## 10. Audit status

**Not audited.** No third-party review has taken place. Before 1.0, § 4.1's public review is a
release blocker; that is a review, not an audit, and the README will say so in those words. If
you need an audited library today, `age` and Tink are the honest recommendations.

**One maintainer.** Aegis has a single maintainer, so changes to the cryptographic code are
merged without a second person's approval. They carry the author's written answers to the review
questions of [contributing.md § 7](contributing.md#7-reviewing). The construction and the format
are read by someone independent before the format freezes and before 1.0
([ADR-0038](decisions.md#adr-0038-one-maintainer-crypto-review-is-written-not-enforced-at-merge)).
