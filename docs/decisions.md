# Decision log

Every load-bearing decision, with its context, its consequences, and the alternatives that
were rejected. The purpose is to keep future contributors — including us in a year — from
relitigating settled questions, and to make the unsettled ones visible.

ADR-0001 to ADR-0012 come from the approved design spec ([initial-spec.md](initial-spec.md))
and are recorded here in their permanent form. ADR-0013 onward were raised while turning that
spec into these documents.

**Statuses:** `accepted` · `proposed` (needs confirmation) · `superseded` · `rejected`

| # | Decision | Status |
|---|---|---|
| [0001](#adr-0001-build-the-cryptographic-core-on-cryptography-using-stream) | Build the core on `cryptography`, using STREAM | accepted |
| [0002](#adr-0002-one-custody-seam-two-modes) | One custody seam, two modes | accepted |
| [0003](#adr-0003-streaming-first-and-synchronous) | Streaming-first and synchronous | accepted |
| [0004](#adr-0004-a-fixed-size-94-byte-header) | A fixed-size 94-byte header | accepted |
| [0005](#adr-0005-context-is-hashed-into-the-aad-never-stored) | `context` is hashed into the AAD, never stored | accepted |
| [0006](#adr-0006-no-compression) | No compression | accepted |
| [0007](#adr-0007-no-async-api-in-10) | No async API in 1.0 | accepted |
| [0008](#adr-0008-collapse-indistinguishable-failures-into-one-error) | Collapse indistinguishable failures into one error | accepted |
| [0009](#adr-0009-mit-license) | MIT license | accepted |
| [0010](#adr-0010-64-kib-chunks) | 64 KiB chunks | accepted |
| [0011](#adr-0011-kek_id-is-derived-never-configured) | `kek_id` is derived, never configured | accepted |
| [0012](#adr-0012-no-legacy-format-reader) | No legacy format reader | accepted |
| [0013](#adr-0013-freeze-the-format-at-milestone-m4) | Freeze the format at milestone M4 | accepted |
| [0014](#adr-0014-chunk-aad-covers-the-immutable-header-core-only) | Chunk AAD covers the immutable header core only | **proposed** |
| [0015](#adr-0015-keks-in-environment-variables-are-base64) | KEKs in environment variables are base64 | **proposed** |
| [0016](#adr-0016-a-zero-length-plaintext-still-produces-one-chunk) | A zero-length plaintext still produces one chunk | **proposed** |
| [0017](#adr-0017-strict-header-validation-reserved-bits-and-custody-zeros) | Strict header validation | **proposed** |

---

## ADR-0001: Build the cryptographic core on `cryptography`, using STREAM

**Status:** accepted

**Context.** Three viable shapes existed: a thin shell over `age`/pyrage, Google Tink's
`StreamingAEAD`, or our own composition of standard primitives.

**Decision.** Our own file format and chunk framing, built on `cryptography`'s AES-GCM and
HKDF, using the published STREAM construction for segmentation.

**Why not `age`/pyrage.** The best security story available — zero original cryptography,
and interoperability with the `age` CLI for free. But its X25519 identity model distorts
the ergonomics exactly at key custody, which is the heart of this library, and it rules out
a custom AAD, which is how `context` binding works. It also adds a native wheel.

**Why not Tink.** Audited, with keysets and rotation built in. But it imports Tink's
conceptual weight — keysets, templates, primitives — against our primary requirement, which
is simplicity. The product would become "an easier way to use Tink", and that is a
different product.

**Consequences.** We invent no cryptography, but **the chunk framing is our code**. A
subtle bug there is our bug, and it is the largest risk in the project. Mitigated by frozen
vectors, the adversarial suite, 100 % coverage on `stream.py`, and a public review before
1.0 ([security.md § 4.1](security.md#41-the-accepted-risk)).

## ADR-0002: One custody seam, two modes

**Status:** accepted

**Context.** Two products want this library: an ordinary backend where the server must read
user files, and a product where the user holds the key and the server cannot. Serving both
usually means two libraries, or one library with two code paths.

**Decision.** One `KeySource` protocol with two methods. `EnvKey` wraps the data key into
the header; `CallerHeld` returns it in the `Receipt` and persists nothing. The `key=`
argument in the `Vault` constructor is the only difference between the modes.

**Consequences.** The core has one path. Third-party KMS support is two functions and no
changes to us — which is also why bundled providers are out of scope. The Django adapter
supports KEK custody only, and says so at system-check time.

## ADR-0003: Streaming-first and synchronous

**Status:** accepted

**Context.** The defect that started this project was `.read()` on a whole file.

**Decision.** The primary API takes streams and processes them in 64 KiB segments with
constant memory. `seal_bytes`/`unseal_bytes` exist as sugar and are documented as O(n).

**Consequences.** The memory ceiling disappears, and "constant memory" becomes a tested
invariant rather than a claim ([tests.md § 5](tests.md#5-layer-4--constant-memory-as-a-tested-invariant)).
The price is the streaming trust boundary ([security.md § 6](security.md#6-the-streaming-trust-boundary)),
which is inherent to every streaming AEAD and is mitigated by `unseal_to_path`.

## ADR-0004: A fixed-size 94-byte header

**Status:** accepted

**Decision.** No length fields, no TLV, no optional sections. Every file starts with the
same 94 bytes in the same order.

**Consequences.** Rotation becomes an in-place 80-byte write, so a 10 TB bucket rotates in
minutes. Parsing has no allocation-driven attack surface. `aegis inspect` is a single read.
The cost is no extensibility inside v1 — which is the point: extension means a new version
byte ([file-format.md § 8](file-format.md#8-changing-this-format)).

## ADR-0005: `context` is hashed into the AAD, never stored

**Status:** accepted

**Decision.** The canonical encoding of `context` is hashed; only the hash enters the AAD.
The context itself is never written to the file.

**Consequences.** The blob leaks no `user_id` to whoever obtains the bucket. In exchange,
when the context does not match, the library cannot report what it expected — security
beating ergonomics, knowingly. And the caller must keep the context reproducible for the
life of the blob, which makes "bind only to immutable fields" a documented rule rather than
advice ([usage.md § 4.1](usage.md#41-three-rules)).

## ADR-0006: No compression

**Status:** accepted

**Decision.** Aegis never compresses. Callers who want it compress before sealing.

**Why.** Compressing before encrypting leaks plaintext through ciphertext length — the
CRIME/BREACH class of attack. A library cannot know whether the caller's data and threat
model make that acceptable, and a default that is sometimes a vulnerability is not a
default.

## ADR-0007: No async API in 1.0

**Status:** accepted

**Decision.** Synchronous only.

**Why.** Encryption is CPU-bound; `async` buys nothing on its own. Adding it would double
the public surface and the test matrix for no throughput gain. Callers who need parallelism
run whole `seal` calls in a thread or process pool.

**Revisit if.** Someone demonstrates a real workload where an async file object cannot be
bridged with `asyncio.to_thread` at acceptable cost.

## ADR-0008: Collapse indistinguishable failures into one error

**Status:** accepted

**Context.** AES-GCM raises the same `InvalidTag` for a wrong key, a wrong context and a
flipped bit. A friendlier-looking API would expose `WrongKeyError` and `WrongContextError`.

**Decision.** One `UnsealFailed`, whose message names all three possibilities. Only failures
that are *genuinely* distinguishable get their own class: `UnknownKek` (decided by
comparing `kek_id`, before any decryption) and `TruncatedFile` (decided by our own
final-chunk marker).

**Why.** Guessing which of the three it was would send the developer to debug the wrong
thing. Being honest about not knowing is more useful than being specific and wrong.

## ADR-0009: MIT license

**Status:** accepted — supersedes the Apache-2.0 recommendation in `initial-spec.md` § 13

**Context.** `initial-spec.md` recommended Apache-2.0 for its explicit patent grant, with MIT
as the simplicity alternative. The repository ships MIT.

**Decision.** MIT, as already committed in [`LICENSE`](../LICENSE).

**Consequences.** Maximum adoption friction removed; no explicit patent grant. Acceptable
for a library composing published, unencumbered primitives. Changing it later requires the
consent of every contributor, so it is settled now rather than at 1.0.

## ADR-0010: 64 KiB chunks

**Status:** accepted

**Decision.** 65536 bytes of plaintext per chunk, fixed by the suite byte, not configurable.

**Why this size.** Overhead is 16/65536 = 0.024 %, negligible. Memory per operation stays
in the tens of kilobytes. The 32-bit counter yields a 256 TiB per-file ceiling, far beyond
any real file. Smaller chunks raise overhead and syscall count; larger ones raise the memory
floor for no gain.

**Why not configurable.** A configurable chunk size is a knob whose only effect is to let
users choose worse values and to multiply the test matrix. A future need is a new suite
byte.

## ADR-0011: `kek_id` is derived, never configured

**Status:** accepted

**Decision.** `kek_id = SHA256(b"aegis-kek-id\x00" ‖ kek)[:16]`.

**Consequences.** The "I configured the wrong key id" class of error cannot exist. Rotation
is self-describing: a reader finds the right KEK by fingerprint, or fails with `UnknownKek`
before touching the AEAD. The price is 16 bytes of cleartext metadata revealing *which* key
sealed the file — accepted in exchange for cheap rotation.

## ADR-0012: No legacy format reader

**Status:** accepted

**Decision.** Aegis reads Aegis files. There is no importer for any other library's format
and no reader for a pre-1.0 shape.

**Why.** There is no production user data to preserve. Every byte of compatibility code is
attack surface and a permanent maintenance obligation.

## ADR-0013: Freeze the format at milestone M4

**Status:** accepted

**Decision.** The frozen vectors are generated once, at M4, after `format`, `context` and
`stream` are complete and reviewed, and before the CLI, the Django adapter or any public
release. After that point the format is immutable and `tests/vectors/v1.json` is read-only
forever.

**Consequences.** Everything that changes bytes — [Q5](architecture.md#16-open-questions)
on domain separation, the package name in the HKDF `info` string
([Q6](architecture.md#16-open-questions)), the context encoding — must be settled **before**
M4. Afterwards each is a new format version. There is deliberately no `--update-vectors`
flag ([tests.md § 3](tests.md#3-layer-1--frozen-vectors-kat)).

## ADR-0014: Chunk AAD covers the immutable header core only

**Status:** **proposed** — resolves a contradiction in `initial-spec.md`; needs confirmation
before M2

**Context.** `initial-spec.md` § 6 specifies `aad = sha256(header) ‖ sha256(canonical_context)`
over the whole 94-byte header, *and* § 6.1 specifies rotation as rewriting `kek_id`, `salt` and
`wrapped_dek` in that header without touching file contents. These are mutually exclusive:
changing any header byte changes `sha256(header)`, which invalidates the tag of **every chunk
in the file**. As specified, the first rotation would destroy every file.

**Decision.** The chunk AAD covers only the header bytes that rotation never touches:

```
header_core = header[0:7] ‖ header[87:94]     # magic, version, suite, flags, nonce_prefix
aad         = SHA256(header_core) ‖ SHA256(canonical_context)
```

**Why this is safe.** The custody block stays fully authenticated by other means: `kek_id` and
`flags` are in the DEK-wrap AAD, `salt` is an HKDF input so a wrong salt yields a wrong
wrapping key, and `wrapped_dek` carries its own GCM tag. Every header byte is therefore either
inside an AAD, an input to a KDF, covered by a tag, or required to be zero ([file-format.md §
4.4](file-format.md#44-every-header-byte-is-authenticated)). All the properties claimed in
`initial-spec.md` § 6.1 survive, including cross-file header transplantation failing —
`nonce_prefix` is in the core.

**Alternatives considered.**
- *Keep the whole-header AAD and drop rotation.* Rotation is a headline feature and the
  reason for the fixed-size header; dropping it costs more than it saves.
- *Keep the whole-header AAD and make rotation rewrite the body.* Turns a minutes-long
  operation on a 10 TB bucket into a multi-day re-encryption. Defeats the design.
- *Exclude `flags` from the core too*, preserving the `initial-spec.md` § 6.1 "convert
  caller-held to KEK custody by rewriting the header" bonus. Rejected: that conversion is
  not a 1.0 feature, and leaving a byte outside every AAD to enable it is a worse trade
  than losing it.

**Consequences.** The "fixed-size bonus" in `initial-spec.md` § 6.1 is withdrawn. Rotation
writes 80 bytes (offsets 7–86), not 94. The rotation test asserts `after[0:7] == before[0:7]`
and `after[87:] == before[87:]`.

## ADR-0015: KEKs in environment variables are base64

**Status:** **proposed** — fills a gap in `initial-spec.md`; needs confirmation before M3

**Context.** `initial-spec.md` § 8 requires `EnvKey` to validate that each KEK is "exactly 32
bytes", but an environment variable holds text. The encoding was never specified, and it is
the first thing every user encounters.

**Decision.** Strict standard base64 with padding — 44 characters for 32 bytes. Anything
else raises `ConfigurationError` at construction, with a message showing exactly how to
generate a valid key. Add an `aegis keygen` command so the developer never has to invent
the incantation.

**Why not also accept hex.** 44-character base64 and 64-character hex are distinguishable,
so accepting both is unambiguous — but two ways to write a key means two ways to write it
in a runbook, two ways to make a typo, and a documentation branch on the very first page.
One canonical form.

**Why not raw bytes with a `latin-1` round-trip.** Environment variables are not
binary-safe across platforms and shells. Not worth the class of bug.

## ADR-0016: A zero-length plaintext still produces one chunk

**Status:** **proposed** — fills a gap in `initial-spec.md`

**Decision.** `number_of_chunks = max(1, ceil(len(plaintext) / 65536))`. An empty file is a
94-byte header followed by one chunk holding 0 bytes of ciphertext and a 16-byte tag.

**Why.** With zero chunks, an empty file would be a bare header — byte-identical to a file
truncated immediately after its header. "Header only" must not be a valid container, or
truncation resistance has a hole at the one place it is easiest to exploit.

## ADR-0017: Strict header validation (reserved bits and custody zeros)

**Status:** **proposed** — fills a gap in `initial-spec.md`

**Decision.** Readers reject, with `MalformedHeader`: any non-zero reserved bit in `flags`;
a non-zero custody block when `flags` bit 0 indicates caller-held custody.

**Why.** Be strict in what you accept. Rejecting reserved bits keeps them genuinely
available for a future version instead of silently in use. Requiring zeros in the unused
custody block removes a 640-bit covert channel and makes the format canonical, which is what
lets a frozen vector pin the exact bytes of a whole container.

**Consequences.** Two negative vectors, and a mutation case in the adversarial suite.

---

## Adding a decision

Open a PR that appends an ADR here and links it from the table. Keep the shape: **Context,
Decision, Why, Consequences**, and name the alternatives you rejected — the rejected options
are the part a future reader needs. An ADR is never edited after it is accepted; it is
superseded by a new one that says so.
