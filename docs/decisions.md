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
| [0014](#adr-0014-chunk-aad-covers-the-immutable-header-core-only) | Chunk AAD covers the immutable header core only | accepted |
| [0015](#adr-0015-keks-in-environment-variables-are-base64) | KEKs in environment variables are base64 | accepted |
| [0016](#adr-0016-a-zero-length-plaintext-still-produces-one-chunk) | A zero-length plaintext still produces one chunk | accepted |
| [0017](#adr-0017-strict-header-validation-reserved-bits-and-custody-zeros) | Strict header validation | accepted |
| [0018](#adr-0018-distribute-as-aegis-voynan-import-as-aegis) | Distribute as `aegis-voynan`, import as `aegis` | accepted |
| [0019](#adr-0019-domain-separated-aad-hashes) | Domain-separated AAD hashes | accepted |
| [0020](#adr-0020-context-is-required-but-may-be-empty) | `context` is required but may be empty | accepted |
| [0021](#adr-0021-the-cli-is-built-on-click) | The CLI is built on `click` | **proposed** |
| [0022](#adr-0022-hatchling-as-the-build-backend) | Hatchling as the build backend | **proposed** |
| [0023](#adr-0023-python-floor-follows-cpythons-support-window) | Python floor follows CPython's support window | **proposed** |
| [0024](#adr-0024-uv-for-development-and-ci) | `uv` for development and CI | accepted |

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

**Status:** accepted (2026-09-14) — resolves a contradiction in `initial-spec.md`; the AAD
hashing below is amended by [ADR-0019](#adr-0019-domain-separated-aad-hashes) (labels added)

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

**Status:** accepted (2026-09-14) — fills a gap in `initial-spec.md`

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

**Status:** accepted (2026-09-14) — fills a gap in `initial-spec.md`

**Decision.** `number_of_chunks = max(1, ceil(len(plaintext) / 65536))`. An empty file is a
94-byte header followed by one chunk holding 0 bytes of ciphertext and a 16-byte tag.

**Why.** With zero chunks, an empty file would be a bare header — byte-identical to a file
truncated immediately after its header. "Header only" must not be a valid container, or
truncation resistance has a hole at the one place it is easiest to exploit.

## ADR-0017: Strict header validation (reserved bits and custody zeros)

**Status:** accepted (2026-09-14) — fills a gap in `initial-spec.md`

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
the AAD formula of [ADR-0014](#adr-0014-chunk-aad-covers-the-immutable-header-core-only)

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

**Status:** **proposed** — `initial-spec.md` left "`click` (or `typer`)" open

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

**Status:** **proposed** — the roadmap left "Hatchling or PDM backend" open

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

**Status:** **proposed** — would amend [product.md § 6](product.md#6-compatibility-promise)

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

**Status:** accepted (2026-09-14)

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

---

## Adding a decision

Open a PR that appends an ADR here and links it from the table. Keep the shape: **Context,
Decision, Why, Consequences**, and name the alternatives you rejected — the rejected options
are the part a future reader needs. An ADR is never edited after it is accepted; it is
superseded by a new one that says so.
