# Decision log

Every load-bearing decision, with its context, its consequences, and the alternatives that
were rejected. The purpose is to keep future contributors — including us in a year — from
relitigating settled questions, and to make the unsettled ones visible.

ADR-0001 to ADR-0012 come from the approved design spec ([initial-spec.md](initial-spec.md))
and are recorded here in their permanent form. ADR-0013 onward were raised while turning that
spec into these documents. ADR-0026 to ADR-0037 come from the design review of 2026-10-18,
which reshaped the header and the key schedule before the format freeze and decided every
open question of [architecture.md § 16](architecture.md#16-open-questions).

**Statuses:** `accepted` · `proposed` (needs confirmation) · `superseded` · `rejected`

| # | Decision | Status |
|---|---|---|
| [0001](#adr-0001-build-the-cryptographic-core-on-cryptography-using-stream) | Build the core on `cryptography`, using STREAM | accepted |
| [0002](#adr-0002-one-custody-seam-two-modes) | One custody seam, two modes | accepted — amended by 0026, 0028 |
| [0003](#adr-0003-streaming-first-and-synchronous) | Streaming-first and synchronous | accepted — amended by 0032 |
| [0004](#adr-0004-a-fixed-size-94-byte-header) | A fixed-size 94-byte header | superseded by 0028 |
| [0005](#adr-0005-context-is-hashed-into-the-aad-never-stored) | `context` is hashed into the AAD, never stored | accepted |
| [0006](#adr-0006-no-compression) | No compression | accepted |
| [0007](#adr-0007-no-async-api-in-10) | No async API in 1.0 | accepted |
| [0008](#adr-0008-collapse-indistinguishable-failures-into-one-error) | Collapse indistinguishable failures into one error | accepted — amended by 0027, 0030 |
| [0009](#adr-0009-mit-license) | MIT license | accepted |
| [0010](#adr-0010-64-kib-chunks) | 64 KiB chunks | accepted |
| [0011](#adr-0011-kek_id-is-derived-never-configured) | `kek_id` is derived, never configured | accepted — scoped to local KEKs by 0028 |
| [0012](#adr-0012-no-legacy-format-reader) | No legacy format reader | accepted |
| [0013](#adr-0013-freeze-the-format-at-milestone-m4) | Freeze the format at milestone M4 | accepted |
| [0014](#adr-0014-chunk-aad-covers-the-immutable-header-core-only) | Chunk AAD covers the immutable header core only | superseded by 0028 |
| [0015](#adr-0015-keks-in-environment-variables-are-base64) | KEKs in environment variables are base64 | accepted — extended by 0029 |
| [0016](#adr-0016-a-zero-length-plaintext-still-produces-one-chunk) | A zero-length plaintext still produces one chunk | accepted — reader rule added by 0030 |
| [0017](#adr-0017-strict-header-validation-reserved-bits-and-custody-zeros) | Strict header validation | superseded by 0028 |
| [0018](#adr-0018-distribute-as-aegis-voynan-import-as-aegis) | Distribute as `aegis-voynan`, import as `aegis` | accepted |
| [0019](#adr-0019-domain-separated-aad-hashes) | Domain-separated AAD hashes | accepted — header core redefined by 0028 |
| [0020](#adr-0020-context-is-required-but-may-be-empty) | `context` is required but may be empty | accepted |
| [0021](#adr-0021-the-cli-is-built-on-click) | The CLI is built on `click` | accepted |
| [0022](#adr-0022-hatchling-as-the-build-backend) | Hatchling as the build backend | accepted |
| [0023](#adr-0023-python-floor-follows-cpythons-support-window) | Python floor follows CPython's support window | accepted |
| [0024](#adr-0024-uv-for-development-and-ci) | `uv` for development and CI | accepted — floor job amended by 0040 |
| [0025](#adr-0025-the-package-lives-in-src) | The package lives in `src/` | accepted |
| [0026](#adr-0026-the-library-draws-every-data-key-key-sources-only-wrap-and-unwrap) | The library draws every data key; key sources only wrap and unwrap | accepted |
| [0027](#adr-0027-a-per-file-salt-drives-the-key-schedule-and-the-header-commits-to-the-key) | A per-file salt drives the key schedule, and the header commits to the key | accepted |
| [0028](#adr-0028-a-typed-bounded-custody-record-replaces-the-fixed-80-byte-block) | A typed, bounded custody record replaces the fixed 80-byte block | accepted |
| [0029](#adr-0029-local-key-sources-envkey-filekey-and-byteskey-with-an-entropy-floor) | Local key sources: `EnvKey`, `FileKey` and `BytesKey`, with an entropy floor | accepted |
| [0030](#adr-0030-how-a-reader-classifies-truncation-and-when-a-final-chunk-may-be-empty) | How a reader classifies truncation, and when a final chunk may be empty | accepted |
| [0031](#adr-0031-the-stream-io-contract-full-segments-full-writes-blocking-streams) | The stream I/O contract: full segments, full writes, blocking streams | accepted |
| [0032](#adr-0032-pull-style-readers-vaultsealed-and-vaultunsealed-seekable-when-the-source-is) | Pull-style readers: `Vault.sealed` and `Vault.unsealed`, seekable when the source is | accepted |
| [0033](#adr-0033-context-values-must-have-an-exactly-accepted-type) | Context values must have an exactly accepted type | accepted |
| [0034](#adr-0034-the-django-adapter-moves-to-v2) | The Django adapter moves to V2 | accepted |
| [0035](#adr-0035-rotation-write-path-torn-write-journal-public-calls-recursive-runs) | Rotation: write path, torn-write journal, public calls, recursive runs | accepted |
| [0036](#adr-0036-inspect-and-the-cli-contract) | `inspect` and the CLI contract | accepted |
| [0037](#adr-0037-smaller-resolutions) | Smaller resolutions | accepted |
| [0038](#adr-0038-one-maintainer-crypto-review-is-written-not-enforced-at-merge) | One maintainer: crypto review is written, not enforced at merge | accepted |
| [0039](#adr-0039-milestone-specs-and-plans-are-local-working-files) | Milestone specs and plans are local working files | accepted |
| [0040](#adr-0040-the-floor-job-installs-the-published-floors-not-the-lock) | The floor job installs the published floors, not the lock | accepted |

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

**Status:** accepted — amended by [ADR-0026](#adr-0026-the-library-draws-every-data-key-key-sources-only-wrap-and-unwrap)
(the seam becomes wrap/unwrap) and [ADR-0028](#adr-0028-a-typed-bounded-custody-record-replaces-the-fixed-80-byte-block)
(a third mode, external custody)

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

**Status:** accepted — amended by [ADR-0032](#adr-0032-pull-style-readers-vaultsealed-and-vaultunsealed-seekable-when-the-source-is)
(pull-style readers beside the push API)

**Context.** The defect that started this project was `.read()` on a whole file.

**Decision.** The primary API takes streams and processes them in 64 KiB segments with
constant memory. `seal_bytes`/`unseal_bytes` exist as sugar and are documented as O(n).

**Consequences.** The memory ceiling disappears, and "constant memory" becomes a tested
invariant rather than a claim ([tests.md § 5](tests.md#5-layer-4--constant-memory-as-a-tested-invariant)).
The price is the streaming trust boundary ([security.md § 6](security.md#6-the-streaming-trust-boundary)),
which is inherent to every streaming AEAD and is mitigated by `unseal_to_path`.

## ADR-0004: A fixed-size 94-byte header

**Status:** superseded by [ADR-0028](#adr-0028-a-typed-bounded-custody-record-replaces-the-fixed-80-byte-block)
(2026-10-18) — a fixed 73-byte core followed by a bounded, length-declared custody record

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

**Status:** accepted — amended by [ADR-0027](#adr-0027-a-per-file-salt-drives-the-key-schedule-and-the-header-commits-to-the-key)
(key commitment makes a wrong key distinguishable: `KeyMismatch`) and
[ADR-0030](#adr-0030-how-a-reader-classifies-truncation-and-when-a-final-chunk-may-be-empty)
(when `TruncatedFile` is provable)

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

**Status:** accepted — scoped by [ADR-0028](#adr-0028-a-typed-bounded-custody-record-replaces-the-fixed-80-byte-block):
it is the `key_id` of local-KEK custody; external key sources choose their own

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

**Status:** superseded by [ADR-0028](#adr-0028-a-typed-bounded-custody-record-replaces-the-fixed-80-byte-block)
(2026-10-18). The principle survives — the chunk AAD covers exactly the header bytes rotation
never touches — but those bytes are now the 73-byte core of ADR-0028. Originally: accepted
(2026-09-14), resolving a contradiction in `initial-spec.md`; the AAD hashing below was amended
by [ADR-0019](#adr-0019-domain-separated-aad-hashes) (labels added)

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

**Status:** accepted (2026-09-14) — fills a gap in `initial-spec.md`; extended by
[ADR-0029](#adr-0029-local-key-sources-envkey-filekey-and-byteskey-with-an-entropy-floor) to key
files and an entropy floor

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

**Status:** accepted (2026-09-14) — fills a gap in `initial-spec.md`;
[ADR-0030](#adr-0030-how-a-reader-classifies-truncation-and-when-a-final-chunk-may-be-empty) adds the
reader's half: an empty final chunk is valid only when it is the only chunk

**Decision.** `number_of_chunks = max(1, ceil(len(plaintext) / 65536))`. An empty file is a
94-byte header followed by one chunk holding 0 bytes of ciphertext and a 16-byte tag.

**Why.** With zero chunks, an empty file would be a bare header — byte-identical to a file
truncated immediately after its header. "Header only" must not be a valid container, or
truncation resistance has a hole at the one place it is easiest to exploit.

## ADR-0017: Strict header validation (reserved bits and custody zeros)

**Status:** superseded by [ADR-0028](#adr-0028-a-typed-bounded-custody-record-replaces-the-fixed-80-byte-block)
(2026-10-18): the `flags` byte became the `custody` byte, and strictness moved to its rules —
exact lengths, zero padding, no unknown values. Originally: accepted (2026-09-14), filling a gap
in `initial-spec.md`

**Decision.** Readers reject, with `MalformedHeader`: any non-zero reserved bit in `flags`;
a non-zero custody block when `flags` bit 0 indicates caller-held custody.

**Why.** Be strict in what you accept. Rejecting reserved bits keeps them genuinely
available for a future version instead of silently in use. Requiring zeros in the unused
custody block removes a 640-bit covert channel and makes the format canonical, which is what
lets a frozen vector pin the exact bytes of a whole container.

**Consequences.** Two negative vectors, and a mutation case in the adversarial suite.

## ADR-0018: Distribute as `aegis-voynan`, import as `aegis`

**Status:** accepted (2026-09-14) — resolves [Q6](architecture.md#16-open-questions);
erratum: a pending publisher does **not** reserve the name, see
[Q18](architecture.md#16-open-questions)

**Context.** The PyPI name `aegis` is taken by an unrelated project (an aiohttp
authentication library, last released in 2020). The project's branding is already built
around "Aegis".

**Decision.** Only the PyPI *distribution* name changes: `pip install aegis-voynan`.
Everything else stays `aegis` — the import package (`import aegis`), the CLI command, the
`AegisError` hierarchy, the `aegis.contrib.django` module, and every string inside the file
format (magic `AEG\x00`, the HKDF `info` and `kek_id` labels).

**Why.** The file format and the public API are what users depend on; the distribution name
only appears in `pip install` and in dependency lists. A split distribution/import name has
wide precedent (`pillow` → `PIL`, `beautifulsoup4` → `bs4`, `pyyaml` → `yaml`).

**Alternatives considered.**
- *Rename the whole project* (`strongroom`, `lacre`, …). Free in the format until M4, but
  discards the existing branding.
- *Also rename the import package* to avoid the collision below. Rejected: `import aegis` is
  the branding developers see in code.

**Consequences.**
- **Import collision.** The unrelated `aegis` distribution also installs a top-level
  `aegis/` package. Installing both in one environment makes them overwrite each other.
  Accepted as unlikely (different domain, unmaintained); documented in
  [usage.md § 1](usage.md#1-install).
- Install commands and extras read `aegis-voynan[django]`, `aegis-voynan[cli]`.
- The name must be registered on PyPI early (a placeholder release, or trusted publishing
  configured as a pending publisher) so it cannot be squatted before 1.0.

## ADR-0019: Domain-separated AAD hashes

**Status:** accepted (2026-09-14) — resolves [Q5](architecture.md#16-open-questions); amends
the AAD formula of [ADR-0014](#adr-0014-chunk-aad-covers-the-immutable-header-core-only). The
labels stand; the `header_core` they hash is the 73-byte core of
[ADR-0028](#adr-0028-a-typed-bounded-custody-record-replaces-the-fixed-80-byte-block)

**Context.** The chunk AAD was `SHA256(header_core) ‖ SHA256(canonical_context)`: two bare
hashes. Every other hash and KDF in the format already carries a label (`kek_id` uses
`b"aegis-kek-id\x00"`, the wrap HKDF uses `info=b"aegis-dek-wrap-v1"`). A bare
`SHA256(canonical_context)` is also byte-identical to a hash a consumer might compute of the
same bytes for an unrelated purpose (a cache key, a log field).

**Decision.**

```
aad = SHA256(b"aegis-hdr-v1\x00" ‖ header_core) ‖ SHA256(b"aegis-ctx-v1\x00" ‖ canonical_context)
```

Labels are ASCII, carry the format version, and end in `\x00` — the same convention as the
`kek_id` label — so no label is a prefix of another label followed by data. ADR-0014's
choice of *which* header bytes enter the AAD is unchanged; only the hashing is amended.

**Why.** Defence in depth, not a fix: no attack on the unlabelled form is known (the header
core starts with `AEG\x00`, which as a context length prefix would need a ~1 GiB key, and the
two hashes occupy fixed positions). The cost is ~13 bytes hashed once per file. Labels tie
every digest to one role and one format version, so a future v2 input can never be read as
a v1 input, and the construction is uniform for the M8 public review.

**Alternatives considered.**
- *Leave the hashes bare.* Free, but the one unlabelled derivation in the format, and
  impossible to change after M4 without a new format version.
- *Labels without the `\x00` terminator.* Works with fixed-length labels, but breaks the
  convention already set by `kek_id` for no gain.

**Consequences.** Must land before the vectors freeze at M4. `context.py` exposes the
labelled hash; the KAT vectors pin both labels.

## ADR-0020: `context` is required but may be empty

**Status:** accepted (2026-09-14) — resolves [Q3](architecture.md#16-open-questions)

**Context.** `initial-spec.md` § 5.2 says `context` is mandatory, but its § 5.1 example calls
`vault.seal(src, dst)` with none.

**Decision.** `context` is a required keyword argument of `seal`, `unseal`, `seal_bytes`,
`unseal_bytes` and `unseal_to_path`. `context={}` is legal and canonicalizes to the empty
byte string (so its hash is `SHA256(b"aegis-ctx-v1\x00")`). `context=None` raises
`UsageError`.

**Why.** Some payloads genuinely have no record to bind to. Making the caller type `{}`
keeps that choice deliberate and visible in code review, instead of an omission.

**Alternatives considered.**
- *Forbid empty contexts.* Pushes callers to invent a meaningless constant, which binds to
  nothing and hides the decision.
- *Make `context` optional, defaulting to `{}`.* Turns the library's central safety feature
  into something a developer can forget.

**Consequences.** A frozen vector with an empty context; a unit test that `None` and a
missing argument both fail.

## ADR-0021: The CLI is built on `click`

**Status:** accepted (2026-10-18) — `initial-spec.md` left "`click` (or `typer`)" open

**Decision.** The `[cli]` extra depends on `click>=8.1`, and nothing else.

**Why.** `click` has no runtime dependencies. `typer` adds `rich`, `shellingham` and
`annotated-doc`. The CLI has five commands, an exit-code contract and binary standard
streams; explicit `click` code expresses all three directly. Fewer packages in the install
of a security tool is a supply-chain property.

**Alternatives considered.** *`typer`* — nicer declarations, three more dependencies.
*`argparse`* — zero dependencies, but binary-stream handling, help formatting and testing
through `CliRunner` would be rebuilt by hand.

**Consequences.** `import aegis` must never import `click`
([performance.md](performance.md) P12). Details: [stack.md § 4.1](stack.md#41-cli--click).

## ADR-0022: Hatchling as the build backend

**Status:** accepted (2026-10-18) — the roadmap left "Hatchling or PDM backend" open

**Decision.** `pyproject.toml` (PEP 621) with Hatchling, and no `setup.py`. The wheel target
names the `aegis` package explicitly, because the distribution name `aegis-voynan` does not
match the directory.

**Why.** Maintained by the PyPA, one line of configuration for this layout, and it does not
imply a workflow tool: `uv build` and `python -m build` produce the same wheel
([ADR-0024](#adr-0024-uv-for-development-and-ci)).

**Alternatives considered.** *PDM backend* — equally capable, but it pulls the project toward
PDM conventions. *setuptools* — works, with more configuration surface and legacy options to
avoid.

**Consequences.** [stack.md § 5](stack.md#5-packaging) holds the reference `pyproject.toml`.

## ADR-0023: Python floor follows CPython's support window

**Status:** accepted (2026-10-18) — amends [product.md § 6](product.md#6-compatibility-promise);
resolves [Q44](architecture.md#16-open-questions)

**Context.** The documents promise "3.10+ at 1.0, SPEC 0 style". CPython 3.10 reaches end of
life on 2026-10-31, before any Aegis release. Strict SPEC 0 would put the floor at 3.13 by
1.0, excluding Debian 12 (3.11) and many Django 5.2 LTS deployments. 3.14 is missing from
the CI matrix.

**Decision.** Each release supports every CPython version that still receives security fixes
on its release date: **3.11–3.14** for a 1.0 before 2027-10-31. Dropping a version stays a
minor release, announced one release ahead.

**Why.** A security library should not advertise an interpreter that no longer gets security
fixes. CPython's own window is predictable and published, and it is wider than SPEC 0 for
the backend deployments Aegis targets.

**Alternatives considered.** *Keep 3.10* — end-of-life on release day. *Strict SPEC 0* —
drops still-supported interpreters that the target users run.

**Consequences.** On acceptance: `requires-python = ">=3.11"`; product.md § 6,
architecture.md § 14 and tests.md § 9 move to 3.11–3.14.

## ADR-0024: `uv` for development and CI

**Status:** accepted (2026-09-14) — floor job amended by [ADR-0040](#adr-0040-the-floor-job-installs-the-published-floors-not-the-lock)

**Context.** The documents described `venv` + `pip` for contributors, development tools
pinned with `==` inside a `[dev]` extra, and a CI job for the oldest supported
`cryptography` without saying how to install it.

**Decision.**
- `uv` manages contributor environments and CI: `uv sync --all-extras`, `uv run …`.
- `uv.lock` is committed. CI runs `uv sync --locked`.
- Development tools move from the `[dev]` extra to a PEP 735 `dev` dependency group, with
  floors in `pyproject.toml` and exact versions in the lockfile.
- The dependency-floor job is `uv sync --resolution lowest-direct`.
- CI installs interpreters with `uv python install`.
- Unchanged: Hatchling stays the build backend (`uv build` invokes it), and publishing stays
  `pypa/gh-action-pypi-publish` with trusted publishing and attestations.

**Why.**
- A lockfile gives contributors and CI the same tool versions, which a set of `==` pins in an
  extra did not cover transitively.
- An extra is published metadata. `pip install "aegis-voynan[dev]"` would have installed our
  linters into a user's environment; a dependency group never leaves the repository.
- `--resolution lowest-direct` turns "we test the floor" from a promise into one flag.
- Users are unaffected: the published wheel has no trace of `uv`.

**Alternatives considered.**
- *`venv` + `pip`, `==` pins* — no lockfile, no transitive reproducibility, no built-in
  lowest-resolution run.
- *Poetry / PDM* — equivalent locking, non-standard or tool-specific metadata history, and
  no Python installation management.
- *`uv_build` as backend* — couples the build to the workflow tool for no gain on a
  pure-Python package.

**Consequences.** `contributing.md` § 1, `roadmap.md` M0 and `tests.md` § 9 describe the `uv`
commands. pip 25.1+ remains a working, unlocked alternative (`--group dev`).

## ADR-0025: The package lives in `src/`

**Status:** accepted (2026-09-22)

**Context.** The documents placed the package at the repository root, as `aegis/`.
[contributing.md § 9](contributing.md#9-releasing) requires the frozen vectors to pass
against the built wheel, not only the source tree, and performance P12 and P13 measure what
`import aegis` loads and costs.

**Decision.**
- The package lives in `src/aegis/`.
- Configuration that takes a path names `src/aegis`: Hatchling's `packages`, `mypy`'s `files`,
  `ruff`'s per-file ignores, `CODEOWNERS`.
- pytest runs with `--import-mode=importlib`.
- Prose keeps naming library files relative to the package (`aegis/__init__.py`, `stream.py`).

**Why.**
- With the package at the root, anything that puts the working directory on `sys.path`
  (`python -m pytest`, a REPL, a script) imports the source tree instead of the installed
  package. A wheel missing a file (`py.typed`, a sub-package) then still passes its tests.
  Under `src/`, the package is importable only once installed: editable in development, the
  built wheel in the release job.
- P12 and P13 then measure the import a user performs, not one that happens to find a
  checkout.
- It is the layout `uv init --lib` generates and the one pytest's documentation recommends.

**Alternatives considered.**
- *Flat layout (`aegis/` at the root)*: one directory fewer, and `python -m aegis.cli` runs
  from a checkout without installing. But the guarantee above would depend on how each
  contributor happens to invoke pytest.
- *Modules directly in `src/`, without `aegis/`*: `src/` is the directory on `sys.path`, not a
  package, so the directory inside it is the import name. The modules would install as
  top-level `errors`, `format`, `stream`, `keys`, and `import aegis` would not exist.
  Renaming `src/` to `aegis/` at build time (Hatchling's `sources`) fixes only the wheel:
  `mypy`, pytest, coverage and editors would still see a top-level `stream` module instead of
  `aegis.stream`.

**Consequences.**
- Nothing changes day to day: `uv sync` installs the project in editable mode.
- `importlib` mode lets two layers share a test basename (`tests/unit/test_format.py`,
  `tests/property/test_format.py`). Test modules cannot import one another, so shared helpers
  live in `conftest.py`.
- Paths change in [structure.md](structure.md), architecture.md § 2.1 and
  [stack.md §§ 5, 6](stack.md#5-packaging).

## ADR-0026: The library draws every data key; key sources only wrap and unwrap

**Status:** accepted (2026-10-18) — resolves [Q27](architecture.md#16-open-questions) and
[Q12](architecture.md#16-open-questions); amends [ADR-0002](#adr-0002-one-custody-seam-two-modes)

**Context.** The custody seam was `provision() -> (dek, CustodyBlock)` and
`recover(block, caller_key) -> dek`: the key source chose the data key. Nonce uniqueness rested
on that key being new for every file, with only a 56-bit random nonce prefix behind it. A
third-party source that caches data keys — a common way to save KMS calls and money — would
reuse a DEK across files. With *n* files under one DEK, the chance of a nonce collision is about
n²/2⁵⁷: one in 144 000 at a million files, against the 2⁻³² that NIST SP 800-38D sets for random
nonces. In GCM a collision leaks the XOR of two plaintexts and the authentication key.
Separately, `CustodyBlock` was a dataclass no outside code could import, so the "two functions"
extension story did not type-check (Q12).

**Decision.**
- `vault.py` draws the DEK with `os.urandom(32)` for every seal. No key source, bundled or
  third-party, generates or chooses one.
- External custody goes through a `KeySource` protocol over plain bytes:
  ```python
  class KeySource(Protocol):
      key_id: bytes    # 16 bytes, not all zero: the key wrap() uses now
      capacity: int    # the largest payload wrap() returns; fixed for the source
      def wrap(self, dek: bytes, aad: bytes) -> bytes: ...
      def unwrap(self, key_id: bytes, payload: bytes, aad: bytes) -> bytes: ...
  ```
  `unwrap` raises `UnknownKek` for a key id it does not manage and `KeyMismatch` for a payload
  that does not authenticate (a KMS "invalid ciphertext" answer); operational errors (network,
  permissions) propagate unchanged. The library checks every DEK it gets back — 32 bytes, and
  the header's key commitment ([ADR-0027](#adr-0027-a-per-file-salt-drives-the-key-schedule-and-the-header-commits-to-the-key)).
- Local-KEK custody (`EnvKey`, `FileKey`, `BytesKey`, [ADR-0029](#adr-0029-local-key-sources-envkey-filekey-and-byteskey-with-an-entropy-floor))
  is implemented by the library itself, so its wrap is specified byte for byte in
  [file-format.md](file-format.md). `CallerHeld()` stays a marker for caller custody.
- `aegis` exports `KeySource`. There is no `CustodyBlock`: the protocol needs no import from us at
  runtime, which is what [architecture.md § 11](architecture.md#11-typing) promised.

**Why.** Freshness by construction instead of by convention: the property the nonce argument
needs is enforced in the one module that draws randomness. Wrap/unwrap is also the shape of
every KMS API (Encrypt/Decrypt, wrapKey/unwrapKey), so an adapter is a thin translation and never
sees the body's keys, nonces or AAD.

**Alternatives considered.**
- *Keep `provision()` and document "return a fresh key".* A rule third parties must remember is
  not a guarantee.
- *Rely on ADR-0027 alone.* A per-file salt makes a repeated DEK harmless for nonces, but a source
  that chooses the DEK can still pin or leak it. Both measures are cheap; both are taken.

**Consequences.** `keys.py` no longer draws randomness; `os.urandom` appears in `vault.py` only.
A KMS adapter is two methods and two attributes. Q12 is resolved by removing the type it was
about.

## ADR-0027: A per-file salt drives the key schedule, and the header commits to the key

**Status:** accepted (2026-10-18) — resolves [Q32](architecture.md#16-open-questions) and the
format half of [Q27](architecture.md#16-open-questions); amends
[ADR-0008](#adr-0008-collapse-indistinguishable-failures-into-one-error); the header layout is in
[ADR-0028](#adr-0028-a-typed-bounded-custody-record-replaces-the-fixed-80-byte-block)

**Context.** The body was encrypted directly under the DEK, with a random 7-byte nonce prefix
stored in the header. Two weaknesses followed. Nonce uniqueness depended entirely on DEK
freshness (Q27). And AES-GCM is not key-committing: one ciphertext can be built to decrypt
validly under two keys (Albertini et al., *How to Abuse and Fix Authenticated Encryption Without
Key Commitment*, USENIX Security 2022). Established formats derive a per-file key from a random
salt instead:
- age: `HKDF-SHA-256(file key, 16-byte nonce, "payload")`.
- Tink's AES-GCM-HKDF streaming: `HKDF(key, salt, associated data)`.
- The AWS Encryption SDK's committing suites: a 256-bit random message ID as HKDF salt, plus a
  32-byte key commitment stored in the header.

**Decision.**
```
salt         = 32 random bytes per file                                         (header)
body_key     = HKDF-SHA256(ikm=DEK, salt=salt, info="aegis-body-key-v1",     L=32)
nonce_prefix = HKDF-SHA256(ikm=DEK, salt=salt, info="aegis-nonce-prefix-v1", L=7)
commitment   = HKDF-SHA256(ikm=DEK, salt=salt, info="aegis-commitment-v1",   L=32)  (header)
```
- Readers recompute `commitment` and compare it, in constant time, before decrypting a single
  chunk. A mismatch raises the new `KeyMismatch`, a subclass of `UnsealFailed`.
- The chunk nonce keeps its layout (`nonce_prefix ‖ counter ‖ last_flag`); the prefix is derived,
  no longer stored.
- The local DEK wrap derives its key from the same salt:
  `HKDF-SHA256(ikm=KEK, salt=salt, info="aegis-dek-wrap-v1")`.

**Why.**
- *Nonces.* A repeated DEK still yields a different body key and prefix in every file, so nonce
  uniqueness rests on a 256-bit salt (birthday bound 2¹²⁸), not on anyone's diligence.
- *Commitment.* Two DEKs with the same commitment would need an HMAC-SHA256 collision. The body
  key comes from the same extract, and the chunk AAD covers the commitment, so a header pins
  exactly one key.
- *Errors.* With the key verified up front, a wrong key becomes distinguishable from a wrong
  context. ADR-0008's rule — a class of its own only for what is genuinely distinguishable — now
  gives `KeyMismatch` a class, and a failing chunk no longer lists "wrong key" among its causes.
- *Multi-key hardening.* The derived prefix is secret and different in every file, the way TLS
  1.3 randomizes per-connection nonces.
- *Cost.* Three HKDF derivations and one comparison per file, in microseconds; nothing per chunk.

**Alternatives considered.**
- *A dedicated committing AEAD construction.* New to this project; the KDF commitment is the
  deployed, reviewed pattern.
- *Keep a stored random prefix as well, as Tink does.* Redundant once the key is unique per file.
- *Commit through a header MAC, as age does.* Equivalent strength, but needs a second key and a
  MAC over bytes that rotation rewrites.

**Consequences.** The header gains a 32-byte salt and a 32-byte commitment and loses the 7-byte
nonce prefix (ADR-0028). One new error class. The frozen vectors pin the three derived values.

## ADR-0028: A typed, bounded custody record replaces the fixed 80-byte block

**Status:** accepted (2026-10-18) — resolves [Q29](architecture.md#16-open-questions) and
[Q25](architecture.md#16-open-questions); supersedes [ADR-0004](#adr-0004-a-fixed-size-94-byte-header),
[ADR-0014](#adr-0014-chunk-aad-covers-the-immutable-header-core-only) (its header core) and
[ADR-0017](#adr-0017-strict-header-validation-reserved-bits-and-custody-zeros)

**Context.** The header was a fixed 94 bytes, with an 80-byte custody block (`kek_id` 16, `salt`
16, `wrapped_dek` 48) whose meaning was the local-KEK wrap. Forty-eight bytes hold a 32-byte key
and its tag and nothing else:
- any AES-GCM wrap with a random IV needs at least 60 bytes;
- a KMS wrap also carries key and version identifiers;
- an RSA wrap from an HSM or Azure Key Vault is 256–512 bytes.

Nothing in the header said which kind of custody a file used. "Implement `KeySource` over your
KMS" ([product.md § 5](product.md#5-how-it-compares)) could only be done by re-implementing Aegis'
own wrap around the KMS.

**Decision.** The header is a fixed 73-byte core followed by a custody record whose length the
core declares:
```
core (immutable; inside every chunk's AAD)
  magic 4 · version 1 · suite 1 · custody 1 · salt 32 · commitment 32 · custody_len 2
custody record (custody_len bytes; rewritten by rotation)
  key_id 16 · payload_len 2 · payload · zero padding
```
- `custody` is `0x00` caller-held (no record, `custody_len = 0`), `0x01` local KEK
  (`custody_len = 66`, `payload_len = 48`), or `0x02` external (`19 ≤ custody_len ≤ 4096`, payload
  opaque to the format, padding zero).
- The record is bound to the core. Local wraps use `SHA256("aegis-custody-v1\x00" ‖ core) ‖
  key_id` as AAD; external sources receive the same digest and should bind it.
- Readers reject with `MalformedHeader` an unknown custody byte, a `custody_len` or `payload_len`
  outside these rules, non-zero padding, and an all-zero `key_id`.

**Why.**
- *KMS fits.* Any wrap up to 4 KiB, identifiers included, fits without a format change, so an
  `aegis-kms-aws` package becomes possible after 1.0.
- *Rotation stays in place.* `custody_len` is in the immutable core and a source's capacity is
  fixed, so re-wrapping writes the same number of bytes at the same offset.
- *Strictness survives.* The length is authenticated, padding must be zero, and every field has
  exactly one valid encoding. Allocation is bounded at 4 096 bytes and checked before reading.
- *Size.* Caller-held files shrink to a 73-byte header; local-KEK headers grow to 139 bytes.

**Alternatives considered.**
- *A fixed custody area of 256 or 640 bytes.* The simplest parse, but 170–570 wasted bytes in
  every local-KEK file, and still too small for some wraps.
- *A TLV header.* Flexible, with an unbounded parser surface — what ADR-0004 rightly refused.
- *Drop the KMS promise from 1.0.* Honest, but the strongest custody option would then need a
  format v2.
- *Detached custody, with the record stored in a database row.* Useful for the Django adapter
  and expressible later on top of the caller-held layout; see [dev/v2-django.md](dev/v2-django.md).

**Consequences.**
- Moving a file to another custody kind, or to a source with a different capacity, changes the
  core and needs a re-seal. Rotation within a kind stays in place.
- `inspect` reads the core, then the record.
- The negative vectors gain one case per rule, which closes Q25.

## ADR-0029: Local key sources: `EnvKey`, `FileKey` and `BytesKey`, with an entropy floor

**Status:** accepted (2026-10-18) — resolves [Q28](architecture.md#16-open-questions),
[Q33](architecture.md#16-open-questions) and [Q37](architecture.md#16-open-questions); extends
[ADR-0015](#adr-0015-keks-in-environment-variables-are-base64)

**Context.**
- *`EnvKey` was the only bundled source.*
  - The environment is inherited by every child process: `subprocess` passes it on unless
    `env=` is given. Apps that store files are the ones that run ImageMagick, ffmpeg or a virus
    scanner.
  - It is readable through `/proc/<pid>/environ` by anything that can read the process's files,
    so a path-traversal bug yields the KEK without code execution. proc(5) documents that this
    file holds the *initial* environment, so deleting the variable at runtime does not remove it.
- *security.md recommended "a secret manager"*, whose SDK hands the application bytes, not an
  environment variable.
- *usage.md told caller-held users to "derive a key with Argon2id and pass it as the caller
  key".* That was impossible, since `seal` generates the caller key. Had it been possible, one
  derived key would have encrypted every file directly.

**Decision.**
- Three local-KEK sources, with one signature and one behaviour:
  ```python
  EnvKey("AEGIS_MASTER_KEY")                 # base64 in an environment variable
  FileKey("/run/secrets/aegis_master_key")   # base64 in a file: Docker, Kubernetes, systemd secrets
  BytesKey(kek)                              # 32 bytes from a secret manager, a KDF or a test
  # each also takes primary=…, previous=[…] for rotation
  ```
- `FileKey` reads strict base64 ([ADR-0015](#adr-0015-keks-in-environment-variables-are-base64))
  and tolerates one trailing `\n` or `\r\n`. All three read their keys once, at construction.
- Every KEK is checked at construction: 32 bytes, no duplicates, and an entropy floor. A KEK is
  rejected if every byte is printable ASCII or if fewer than 16 byte values are distinct. A key
  from a CSPRNG trips this with probability below 2 × 10⁻¹⁴; a base64-encoded passphrase trips it
  every time. The failure is a `ConfigurationError` that shows how to generate a key.
- A password-derived key is a **KEK**: `BytesKey(argon2id(password, salt))` wraps a fresh DEK per
  file. A caller key is never reused as a DEK.

**Why.**
- *Files over environment.* A mounted secret is not inherited by child processes and is not
  copied into crash reports or orchestrator manifests. It is the documented secret channel of
  Docker, Kubernetes and systemd.
- *Bytes for everything else.* Secret-manager SDKs and test fixtures produce bytes. Making them
  write a base64 environment variable first would be a regression in both safety and ease.
- *The entropy floor* catches, at startup, the one mistake a length check cannot.

**Alternatives considered.**
- *Scrub the variable from `os.environ` after reading.* It stops inheritance but not
  `/proc/<pid>/environ`, and it breaks re-exec (autoreloaders) and re-construction.
- *One class with `from_env`/`from_file` constructors.* Equivalent, and it renames a documented
  API for no gain.

**Consequences.** Three public names instead of one. [security.md § 5](security.md#5-key-management)
ranks them: external custody first, then `FileKey` or `BytesKey`, then `EnvKey`. The CLI gains
`--key-file` ([ADR-0036](#adr-0036-inspect-and-the-cli-contract)).

## ADR-0030: How a reader classifies truncation, and when a final chunk may be empty

**Status:** accepted (2026-10-18) — resolves [Q30](architecture.md#16-open-questions) and
[Q31](architecture.md#16-open-questions); amends [ADR-0008](#adr-0008-collapse-indistinguishable-failures-into-one-error)
and [ADR-0016](#adr-0016-a-zero-length-plaintext-still-produces-one-chunk)

**Context.**
- *The closing rule never ran.* The unsealing loop decrypted the final block only with
  `last=True`, so its rule — "a stream that ends after a chunk marked last=False raises
  TruncatedFile" — was unreachable.
- *Docs promised more than the spec delivered.* As specified, `TruncatedFile` came out only for a
  bare header or a 1–15-byte remainder. A cut at a chunk boundary or inside a chunk raised
  `UnsealFailed`, while tests.md and security.md promised `TruncatedFile` at any offset.
- *Two encodings of one plaintext.* The writer never emits an empty final chunk after a full
  one, but the reader accepted it.

**Decision.** A reader classifies the end of the body as follows:

| Final block | Outcome |
|---|---|
| none — the body is empty | `TruncatedFile` |
| 1–15 bytes | `TruncatedFile` — no chunk is shorter than 16 bytes |
| 65 552 bytes that fail as final but authenticate as non-final | `TruncatedFile` — cut at a chunk boundary; that chunk is not emitted |
| anything else that fails | `UnsealFailed` — a cut inside a chunk is indistinguishable from corruption |
| a final chunk with 0 plaintext bytes at counter > 0 | `UnsealFailed` — non-canonical |

A final chunk may be empty only when the whole plaintext is empty. This is age's rule ("MUST NOT
be empty unless the whole payload is empty").

**Why.** Every `TruncatedFile` above is something the reader proves, not guesses. The retry costs
one extra GCM operation, only on a failing file, and gives an attacker one extra forgery attempt
at 2⁻¹²⁸. Calling a cut inside a chunk `TruncatedFile` would be exactly the guess ADR-0008
forbids. Tink's specification gives the same warning: do not let users confuse end of file with a
decryption error.

**Consequences.** Seekable readers apply the same table to the last chunk when they open
([ADR-0032](#adr-0032-pull-style-readers-vaultsealed-and-vaultunsealed-seekable-when-the-source-is)).
The negative vectors gain a boundary truncation and an empty trailing chunk. The adversarial
suite expects `TruncatedFile` only where this table promises it, and `UnsealFailed` or
`TruncatedFile` elsewhere.

## ADR-0031: The stream I/O contract: full segments, full writes, blocking streams

**Status:** accepted (2026-10-18) — resolves [Q36](architecture.md#16-open-questions)

**Context.** Sealing said "for each 65536-byte segment", and the API accepts sockets, pipes and
raw streams. Python's `io` documentation says:
- `RawIOBase.read` returns fewer bytes than asked whenever the system call does, and `None` when
  the stream is non-blocking;
- for `BufferedIOBase.read`, "less than size bytes being returned does not imply that EOF is
  imminent";
- `RawIOBase.write` may write fewer bytes than it is given.

An implementation that treats each `read()` result as a segment writes short non-final chunks.
The reader expects 65 552-byte chunks, so such a file never opens again — and every test used
`BytesIO`, which never reads short.

**Decision.**
- Segment boundaries are byte counts. A writer fills every segment to exactly 65 536 bytes,
  looping over short reads; only end of stream ends a segment early.
- Every write loops until all bytes are accepted.
- The following raise `UsageError`: `None` from `read` or `write` (a non-blocking stream), a
  `read` that returns more bytes than asked, and a non-`bytes` result (a text stream).
- The property tests seal from a source that returns random short reads, single bytes included,
  into a sink that accepts partial writes, and compare the result with a `BytesIO` run.

**Consequences.** A few lines in `stream.py`'s I/O helpers and one property test. Silently
producing unreadable files is ruled out by construction.

## ADR-0032: Pull-style readers: `Vault.sealed` and `Vault.unsealed`, seekable when the source is

**Status:** accepted (2026-10-18) — resolves [Q38](architecture.md#16-open-questions) and
[Q40](architecture.md#16-open-questions); amends [ADR-0003](#adr-0003-streaming-first-and-synchronous)

**Context.**
- *Push-only API, pull-based consumers.* `seal(src, dst)` writes into a stream the caller owns,
  but most consumers pull: Django's `Storage.save` and `FileResponse`, boto3's `upload_fileobj`,
  Starlette's `StreamingResponse`.
- *Bridging was costly.* Joining push to pull takes a thread and a pipe, or a temporary copy, and
  the dogfood rule keeps adapters out of `stream.py`'s iterators.
- *No random access.* The format already allows it — fixed chunk size, nonce computable from the
  index — but nothing exposed it. HTTP Range requests, media seeking and libraries that seek
  (`zipfile`, Pillow, PDF readers) had to decrypt whole files first.

**Decision.**
```python
reader = vault.sealed(src, context=…)              # read() returns the sealed container
receipt = reader.receipt                            # once the reader has been read to the end

reader = vault.unsealed(src, context=…, key=None)   # read() returns plaintext
reader.size                                         # authenticated size if src is seekable, else None
```
- Both are binary `io.RawIOBase` readers with `read`, `readinto`, `chunks(size=65536)` and `close`.
  Each holds at most one segment, is not thread-safe, and owns its source: closing the reader
  closes the source, as `io` wrappers do.
- `chunks()` yields up to 64 KiB at a time and closes the reader when it is exhausted or
  abandoned, so it can go straight into a streaming response.
- Readers have no `name` attribute. Frameworks derive `Content-Length` from a file's name, and the
  ciphertext's size would be wrong.
- `unsealed` parses the header, recovers the key and checks the commitment when called, so
  `UnknownKek`, `KeyMismatch` and format errors surface before the first read.
- When `src` is seekable, `unsealed` locates and authenticates the **final chunk at open**
  ([ADR-0030](#adr-0030-how-a-reader-classifies-truncation-and-when-a-final-chunk-may-be-empty)'s
  table). Its `size` is then authenticated, and truncation is detected before any byte is
  returned. The reader supports `seek` and `tell`, and a read decrypts only the chunks it covers.
- When `src` is not seekable, the reader is forward-only and keeps the streaming trust boundary of
  [security.md § 6](security.md#6-the-streaming-trust-boundary).

**Why.** A file-like object is the interface most of Python accepts, and an iterator is one call
away (`chunks()`). Seekable sources lose the trust boundary entirely, for the price of one extra
chunk at open. Tink's specification allows random access on the same principle: never confuse
end of file with a decryption error.

**Alternatives considered.**
- *Iterators only.* Easy to stream into HTTP, awkward for every API that wants `read()`.
- *An async API.* [ADR-0007](#adr-0007-no-async-api-in-10) holds: an async server can hand one
  chunk read at a time to a thread ([usage.md § 10](usage.md#10-django-and-other-web-frameworks)),
  and the Django adapter will ship that bridge ([dev/v2-django.md](dev/v2-django.md)).

**Consequences.** A new module, `readers.py`, on top of `stream.py`'s chunk primitives, which take
an explicit index and `last` flag. The memory invariants (P3) and a random-access property test
cover both readers.

## ADR-0033: Context values must have an exactly accepted type

**Status:** accepted (2026-10-18) — resolves [Q45](architecture.md#16-open-questions)

**Context.** The canonical encoding accepts `str`, `bytes`, `int`, `bool` and `None`, and rejects
`Enum`. But `IntEnum` and `IntFlag` are `int`s, and `StrEnum` and Django's `SafeString` are `str`s,
so an `isinstance` check would accept them silently — and a subclass can change how it encodes.
Moving from `isinstance` to exact checks after 1.0 would turn working contexts into errors.

**Decision.**
- Keys must be exactly `str`. Values must be exactly `str`, `bytes`, `int`, `bool` or `None`,
  checked with `type(v) is …`, `bool` before `int`.
- Subclasses, `bytearray` and `memoryview` raise `UsageError`, naming the type and the conversion
  to write (`int(v)`, `str(v)`, `bytes(v)`).
- The context itself may be any `Mapping`.

**Why.** The encoding is a cryptographic input that must reproduce for years. It should depend on
values, not on class hierarchies. "The library never guesses"
([file-format.md § 5](file-format.md#5-canonical-serialization-of-context)) applies to types as
much as to floats.

**Consequences.** One rule in `context.py`, and a table of rejected subclasses in the unit tests.

## ADR-0034: The Django adapter moves to V2

**Status:** accepted (2026-10-18) — moves [Q4, Q16, Q39, Q41 and Q42](architecture.md#16-open-questions)
to [dev/v2-django.md](dev/v2-django.md)

**Context.** The adapter carried two open questions: Q4 (unsaved instances) and Q16 (how the
field gets its vault). The review of 2026-10-18 added structural ones:
- bridging Django's pull-based storage and responses (Q38, now solved in the core);
- ASGI materialising synchronous iterators (Q39) — Django's documentation says such an iterator
  "must be fully-consumed, which defeats the purpose";
- a default context that binds only to the owner (Q41);
- storage names, `FieldFile.url`, an authorized decrypting view, and migrating existing plaintext
  files (Q42).

Each needs design, tests against several Django versions and storage backends, and a security
review of its own.

**Decision.** 1.0 ships no `aegis.contrib.django` and no `[django]` extra. Milestone M7 leaves the
1.0 path. The adapter is planned in [dev/v2-django.md](dev/v2-django.md), which records the decisions
already taken and the questions still open. 1.0 documents how to use the core from Django with
the public readers ([usage.md § 10](usage.md#10-django-and-other-web-frameworks)).

**Why.** The core's guarantees do not depend on the adapter, and the adapter depends on core APIs
— readers, seekable decryption, `inspect` — that only exist from M3. Building it after 1.0 lets it
dogfood a frozen, reviewed core instead of steering it.

**Consequences.** A smaller 1.0: no Django in the CI matrix, the stack or the dependency surface.
"V2" names a product phase, not a format version. The adapter is additive, so under SemVer it can
ship as a 1.x minor release.

## ADR-0035: Rotation: write path, torn-write journal, public calls, recursive runs

**Status:** accepted (2026-10-18) — resolves [Q8, Q9, Q11, Q15 and Q43](architecture.md#16-open-questions)

**Context.** Rotation was specified as one 80-byte `pwrite` per file. That left five gaps:
- `pwrite` does not exist on Windows (Q8).
- A power loss mid-write could leave a half-old, half-new custody block that opens under neither
  key (Q9).
- No public call existed for the CLI to dogfood (Q11).
- Recursive runs over mixed directories were undefined (Q15).
- Throughput was advertised per terabyte (Q43).

**Decision.**
- **Calls.**
  - `vault.rotate(path) -> RotationResult` rewrites a local file in place.
  - `vault.rewrap(src, dst) -> RotationResult` streams a container to a new destination with the
    custody record re-wrapped and the body copied byte for byte, never decrypted. This is the
    rotation path for object stores, which cannot overwrite part of an object.
  - `RotationResult` carries `outcome` (`rotated`, `already_current`, `skipped_caller_held`) and
    `recovered` (a leftover journal was applied first).
- **Write path (Q8).** `os.pwrite` where it exists. Elsewhere, open `r+b`, seek to offset 73 and
  issue one write. `fsync` in both cases.
- **Torn writes (Q9, option 3).**
  1. Before overwriting, write a journal `<file>.aegis-rotate` = `"aegis-rotate-v1\x00" ‖
     u16be(custody_len) ‖ old record ‖ SHA-256 of the preceding bytes`. Create it exclusively and
     `fsync` it and, on POSIX, its directory.
  2. Write the new record, `fsync` the file, delete the journal.
  3. Every rotation first looks for a leftover journal:
     - a bad checksum means the file was never touched, so the journal is deleted;
     - otherwise the record that opens under a configured key and passes the commitment check is
       kept, whether it is the one on disk or the journaled one, and restored if needed.
- **Checks before writing.** Rotation recovers the DEK and verifies the commitment first.
  `UnknownKek` and `KeyMismatch` leave the file untouched. A source whose capacity no longer
  matches the file's `custody_len` gets `UsageError`: re-seal instead.
- **Recursive runs (Q15).**
  - Caller-held files, non-Aegis files and, from the CLI, external-custody files each get one
    report line and do not fail the run.
  - Per-file errors are reported and the run continues; a summary ends the output.
  - The exit code is 0 when nothing failed, otherwise the first failure's code; `--fail-fast`
    stops at that failure.
- **Claims (Q43).** Rotation cost is per file — a few `fsync`s each — not per terabyte. The "10 TB
  in minutes" lines are withdrawn.

**Why.** Option 3 keeps the format strict — no second, possibly torn record that readers would
have to tolerate — and costs nothing outside rotation. `rewrap` gives object stores the same
"never re-encrypt the body" property without pretending objects can be edited in place.

**Alternatives considered.** Option 1 (document and accept) moves the risk to users. Option 2
(rewrite whole files) is `rewrap`, kept for object stores, where it is the only choice. Option 4
(two custody records in the format) would make readers accept a record that does not
authenticate.

**Consequences.**
- P7 counts the I/O on the target file and names the journal separately.
- A reader that races the record write may fail once and succeed on retry;
  [usage.md § 8](usage.md#8-rotating-your-master-key) says so.

## ADR-0036: `inspect` and the CLI contract

**Status:** accepted (2026-10-18) — resolves [Q10, Q13, Q14 and Q24](architecture.md#16-open-questions)

**Context.** The CLI had no public call behind `aegis inspect` (Q10). It also had no way to
receive keys without exposing them on argv or a standard stream (Q13), could express only `str`
and `int` contexts (Q14), and printed size-derived numbers as if they were authenticated (Q24).

**Decision.**
- **`aegis.inspect(src) -> FileInfo` (Q10, Q24).**
  - Fields: `version`, `suite`, `custody`, `key_id` (or `None`), `header_size`, and the
    size-derived `container_size`, `chunks`, `plaintext_size` and `size_consistent`.
  - It never takes a key and never decrypts. A seekable source is measured; a non-seekable one is
    read to its end without decryption.
  - Derived numbers are labelled unauthenticated wherever they are shown. An impossible size — a
    body of 0–15 bytes, or a remainder of 1–15 bytes — sets `size_consistent=False`.
- **Keys (Q13).**
  - `--key-env NAME` (default `AEGIS_MASTER_KEY`) or `--key-file PATH` selects the primary KEK;
    `--previous-env NAME` and `--previous-file PATH` may repeat.
  - Caller-held: `seal --caller-held --key-out PATH`, where the file is created exclusively with
    mode `0600` on POSIX, and `unseal --key-in PATH`.
  - Key bytes never appear on argv or on a standard stream.
- **Context (Q14).** `--context k=v` (`str`), `--context-int k=v`, `--context-hex k=HEX`
  (`bytes`), `--context-bool k=true|false` and `--context-null k` cover every type the library
  accepts.
- **External custody.** The CLI cannot hold a `KeySource`. It inspects such files, and `rotate`
  reports them as skipped.

**Consequences.** [architecture.md § 12](architecture.md#12-the-cli) and
[usage.md § 9](usage.md#9-cli) carry the full contract. Exit codes are unchanged; `KeyMismatch`
exits 1 like every `UnsealFailed`.

## ADR-0037: Smaller resolutions

**Status:** accepted (2026-10-18) — resolves [Q7, Q17–Q23, Q26 and Q46](architecture.md#16-open-questions)

| Q | Decision |
|---|---|
| Q7 | `Receipt.key_id` ships in 1.0: the 16-byte id of the key that wrapped the DEK, `None` when caller-held. |
| Q17 | `.hypothesis/` is git-ignored. Every failure Hypothesis finds is pinned as an explicit `@example(...)` on the property it broke. |
| Q18 | M0 configures the pending trusted publisher and immediately publishes a `0.0.0` placeholder through `release.yml`; that is what reserves the name, and it proves the publishing path. |
| Q19 | Review of [file-format.md](file-format.md) is requested now — after this revision, before M2. Review of `stream.py` and `envelope.py` is requested when M2 closes. "Format review feedback triaged" gates M4; M8 stays the final pass. |
| Q20 | Header errors follow the bytes that actually arrive. An empty stream or a magic mismatch is `NotAnAegisFile`; a matching prefix that ends early is `MalformedHeader`. Version and suite are checked as soon as their bytes exist, before the rest of the header is required. |
| Q21 | `unseal_to_path` writes a temporary file in the destination directory (mode `0600`), `fsync`s it, `os.replace`s it, then `fsync`s the directory on POSIX. Windows cannot sync a directory; there, the rename is as durable as the filesystem makes it, and the documentation says so. |
| Q22 | `MAX_CHUNKS = 2**32` lives in `stream.py` and is checked before each nonce in both directions. The writer raises `UsageError` (input larger than 256 TiB); the reader raises `UnsealFailed`. Tests lower it through a parameter. |
| Q23 | Every unseal entry point canonicalizes `context` and checks the call's custody arguments before reading a byte. |
| Q26 | Custody mismatches raise before any decryption. `UsageError`: a caller-held file opened by a server-custody vault, a server-custody file opened by `CallerHeld()`, `key=` passed to a server-custody vault, `CallerHeld()` without `key=`. `UnknownKek`, with `file_custody` set: a local-KEK file opened through a `KeySource`, or the reverse. |
| Q46 | `seal_bytes` on a `CallerHeld()` vault raises `UsageError`: it returns only the blob, so the key would be lost. Caller-held sealing goes through `seal` or `sealed`, whose `Receipt` carries the key. |

## ADR-0038: One maintainer: crypto review is written, not enforced at merge

**Status:** accepted (2026-10-19) — replaces the two-approval rule of
[contributing.md § 7](contributing.md#7-reviewing) for as long as the project has one maintainer

**Context.** [contributing.md § 7](contributing.md#7-reviewing) required two approvals, one from a
maintainer, on every change to `stream.py`, `envelope.py`, `format.py`, `keys.py`, `readers.py`,
`rotate.py` or the format. M0 was to enforce this with `CODEOWNERS` and a ruleset. GitHub counts
an approval only from someone with write access, and never counts the author's own. A pull
request by the maintainer would therefore need two other people with write access. Aegis is a
solo project. An academic advisor validates its direction but does not review pull requests.
Enforced as written, the rule would block every crypto change from M1 on.

**Decision.** While Aegis has one maintainer:

- The `main` ruleset requires a pull request, the `ci-ok` status check, linear history, and no
  force pushes or deletion. It requires **no approvals**.
- A pull request that touches a crypto path carries, in its description, the author's written
  answers to the six questions of [contributing.md § 7](contributing.md#7-reviewing).
- The independent reads that milestones already require stay required, done by someone other
  than the author and named in the pull request. These are the M2 line-by-line read of
  `stream.py` and `envelope.py` against `file-format.md`, and the M4 hand-check of the vectors.
  The reader is a public reviewer recruited through Q19, or anyone else willing to do it.
- The public review of [security.md § 4.1](security.md#41-the-accepted-risk) (Q19, and the M8
  final pass) remains a release blocker. It is the project's second pair of eyes.
- `CODEOWNERS` is still committed, naming the maintainer on the crypto paths. When a second
  person with write access joins, the ruleset gains required approvals and code-owner review on
  those paths, and a new ADR supersedes this one.
- [security.md § 10](security.md#10-audit-status) says, in plain words, that crypto changes are
  merged without a second approval.

**Why.** A required review that can never be satisfied is not a control. It gets bypassed, and a
bypass that becomes routine hides the one that matters. Written answers to fixed questions force
the author to check what a reviewer would check. Independent reads at the points where the format
and the construction are fixed put a second person where a mistake would be permanent. Saying so
in `security.md` keeps the guarantee honest.

**Consequences.** A crypto bug can reach `main` with only its author having read it. The
frozen vectors, the adversarial suite, the 100 % branch gates and the pre-freeze public review
are what catch it before a release. M2 and M4 cannot close until someone other than the author
has done their read.

**Rejected.**
- *Keep two approvals.* This needs two other people with write access, and the project has none.
- *Count the author as one of two.* This needs one other person with write access, and there is
  none either.
- *Require approvals and bypass them as admin.* This turns the rule into a formality that is
  broken on every crypto pull request.
- *Give write access to a reviewer who does not review.* This would satisfy the check without
  doing the review.

## ADR-0039: Milestone specs and plans are local working files

**Status:** accepted (2026-10-19) — reverses the "committed" part of the workflow rules of
2026-10-18

**Context.** The workflow rules of 2026-10-18 had each milestone's spec go to `docs/dev/specs/`
and its plans to `docs/dev/plans/`, committed with the work they describe. The first spec and
plan, for M0, showed what they are in practice. They are working scaffolding for the
superpowers skills: step-by-step commands, pinned SHAs, checklists ticked during execution,
drafts revised in conversation. They are not documentation a contributor or user reads.

**Decision.** Specs go to `docs/dev/superpowers/specs/YYYY-MM-DD-mN-<topic>-design.md` and plans
to `docs/dev/superpowers/plans/YYYY-MM-DD-mN-<k>-<topic>.md`. `docs/dev/superpowers/` is
git-ignored, like `docs/dev/notes.md` and `docs/dev/diary/`. The gates do not change: a spec and
its plans are still written with superpowers and approved by the author before any code.

**Why.** Everything a spec decides that outlives its milestone already has to reach the
normative documents. A new or changed decision becomes an ADR, and every affected document is
edited in the same change. Committing the spec as well would keep a second, non-normative copy
of those decisions that drifts from the documents. The plans' value ends when their milestone
closes.

**Consequences.**
- The repository's history shows the decisions (ADRs, document edits) and the evidence (the
  failing and passing outputs quoted in each pull request), not the working drafts.
- A spec decision that never reaches an ADR or a document is lost when the local files are.
  Closing a milestone therefore includes checking that every decision of its spec has landed.
- No committed document links to a spec or a plan.

**Rejected.** *Commit them in `docs/dev/specs/` and `docs/dev/plans/`* (the previous rule):
non-normative duplicates of the documents. *Keep them outside the repository:* the superpowers
skills and the rules expect a stable path inside it.

## ADR-0040: The floor job installs the published floors, not the lock

**Status:** accepted (2026-10-26) — amends the floor-job line of
[ADR-0024](#adr-0024-uv-for-development-and-ci)

**Context.** ADR-0024 made the dependency-floor job `uv sync --resolution lowest-direct`. `uv`
resolves one lock for the project and every dependency group together, so a requirement of a
development tool constrains the runtime dependencies inside it. While M0's CI was being built
(2026-10-26), `mutmut 3.8.0` was found to require `click>=8.4.2`. `uv sync --resolution
lowest-direct` therefore installed `click 8.4.2`, while the published metadata promises
`click>=8.1`. The job would have tested a floor that users are not given, and passed.

**Decision.**
- A `test` dependency group holds only what the suite itself runs: `pytest`, `hypothesis` and
  `mypy`. The `dev` group includes it (`{ include-group = "test" }`), so `uv sync` is unchanged.
- The floor job runs `uv venv`, then
  `uv pip install --resolution lowest-direct -e ".[cli]" --group test`, and prints the
  `cryptography` and `click` versions it got before running the suite. `uv pip install`
  resolves only the requirements it is given, as a user's `pip install "aegis-voynan[cli]"`
  does, with the lock out of the picture.
- Every other CI job still runs `uv sync --locked`.

**Why.** Verified in a scratch copy on 2026-10-26: `uv sync --resolution lowest-direct` gave
`cryptography 44.0.0` and `click 8.4.2`. The `uv pip` form gave `cryptography 44.0.0`,
`click 8.1.0`, `pytest 9.1.1`, `hypothesis 6.168.0` and `mypy 2.3.1`, and passed. A floor
test whose result depends on which linters we happen to use is not a floor test.

**Consequences.**
- The test tools also run at their declared floors in that job. A floor that breaks the suite
  is raised in `pyproject.toml`, like any other.
- A new tool the suite needs at run time joins `test`, not just `dev`. Otherwise the floor job
  fails, and that failure is what reminds us.

**Rejected.** *Keep `uv sync --resolution lowest-direct`:* it measures the lock, not the
metadata. *Raise the `click` floor to 8.4.2:* it would impose a linter's requirement on users.
*`[tool.uv] conflicts` between the CLI extra and `mutmut`:* it forks the lock to work around a
problem that `uv pip` does not have. *Hard-code the floors in the workflow:* they would drift
from `pyproject.toml`.

---

## Adding a decision

Open a PR that appends an ADR here and links it from the table. Keep the shape: **Context,
Decision, Why, Consequences**, and name the alternatives you rejected — the rejected options
are the part a future reader needs. An ADR is never edited after it is accepted; it is
superseded by a new one that says so.
