# Testing strategy

In a cryptography library the suite is not there to catch regressions. **It is the argument
that the code deserves trust.** A reviewer who cannot audit our AES will read our tests, so
the tests are written to be read.

---

## 1. Principles

1. **Test the invariant, not the implementation.** "No mutation ever yields plaintext" is
   one property covering hundreds of attacks; a hundred hand-written mutation tests cover
   only the hundred we thought of.
2. **The frozen vectors are the compatibility promise.** If a code change makes them fail,
   the code is wrong. They are never regenerated to match new behaviour — regenerating them
   *is* a format change ([file-format.md § 8](file-format.md#8-changing-this-format)).
3. **Randomness lives at the edges**, so the risky code is testable as a pure function.
   If a test needs to patch `os.urandom` to reach `envelope.py` or `stream.py`, the
   architecture broke, not the test
   ([architecture.md § 4](architecture.md#4-the-purity-boundary-randomness-lives-at-the-edges)).
4. **Failure modes are asserted, not observed.** Every test that expects an error asserts
   the *specific* class. `pytest.raises(AegisError)` is too weak to be a test.
5. **Never assert on a message string.** Errors carry structured attributes for that.
6. **No test touches the network, the clock, or a real home directory.**

## 2. The layers

| # | Layer | Answers | Tool | Gate |
|---|---|---|---|---|
| 1 | Frozen vectors (KAT) | "Will today's file open in five years?" | `pytest` + JSON | blocking |
| 2 | Property round-trip | "Does it work for every input, every stream shape, every read pattern?" | Hypothesis | blocking |
| 3 | Adversarial | "Can a tampered file ever produce plaintext?" | Hypothesis | blocking |
| 4 | Constant memory | "Is 'streaming' true, or marketing?" | `tracemalloc` | blocking |
| 5 | Rotation & dogfood | "Does rotation really not touch the body? Is the public API complete?" | `pytest` + AST | blocking |
| 6 | Unit | "Does each module do its one job?" | `pytest` | blocking |
| 7 | Integration | "Does the CLI work end to end?" | subprocess | blocking |
| 8 | Benchmarks | "Did throughput regress?" | `pytest-benchmark` | **not** a PR gate |

Layers 1–5 are the interesting ones and get their own sections. Write layer 1 first — before
`vault.py` exists.

```
tests/
├── vectors/v1.json            # frozen. Read-only forever.
├── unit/                      # format, context, envelope, keys, errors
├── property/                  # round-trip, short reads, readers, canonicalization
├── adversarial/               # the mutation property
├── invariants/                # memory ceiling, rotation body-identity, dogfood imports
└── integration/               # the CLI
benchmarks/                    # separate suite, separate command
```

The Django adapter's tests arrive with the adapter in V2 ([dev/v2-django.md](dev/v2-django.md)).

## 3. Layer 1 — Frozen vectors (KAT)

A versioned JSON file pinning, for fixed inputs, the exact expected output byte for byte.

```json
{
  "format_version": 1,
  "generated": "2026-…",
  "note": "FROZEN. Regenerating this file is a format change. See docs/file-format.md §8.",
  "cases": [
    {
      "name": "local-kek/empty-plaintext",
      "kek_b64": "…", "dek_hex": "…", "salt_hex": "…",
      "body_key_hex": "…", "nonce_prefix_hex": "…", "commitment_hex": "…",
      "context": [["user_id", "int", "42"], ["kind", "str", "invoice"]],
      "plaintext_hex": "",
      "expected_container_hex": "41454700 01 01 01 …"
    }
  ]
}
```

**Required cases**, each in **all three custody modes**: caller-held, local KEK, and external.
External uses a deterministic test key source whose capacity is larger than its payload, so the
zero padding is pinned too.

- empty plaintext (one chunk, zero-length — the rule that keeps a bare header invalid)
- 1 byte
- 65535, 65536, 65537 bytes (the chunk boundary in all three directions)
- exactly 2 × 65536 bytes (a full final chunk, no empty trailing chunk)
- a context exercising every type tag, including `bool` versus `int` and a key whose UTF-8
  sort order differs from its code-point order
- an empty context `{}` ([ADR-0020](decisions.md#adr-0020-context-is-required-but-may-be-empty))

Every case pins the derived `body_key`, `nonce_prefix` and `commitment` as well as the container,
so a key-schedule bug cannot hide behind a matching round-trip.

Plus **negative vectors** — byte sequences that must be rejected, each with the exact expected
exception:

| Input | Exception |
|---|---|
| an empty file | `NotAnAegisFile` |
| `41 45` (a matching magic prefix, then nothing) | `MalformedHeader` |
| bad magic | `NotAnAegisFile` |
| `version = 2` | `UnsupportedVersion` |
| `suite = 2` | `UnsupportedVersion` |
| `custody = 0x03` | `MalformedHeader` |
| caller-held with `custody_len ≠ 0` | `MalformedHeader` |
| local KEK with `custody_len ≠ 66`, or with `payload_len ≠ 48` | `MalformedHeader` |
| external with `custody_len` of 18 or 4 097 | `MalformedHeader` |
| external with `payload_len = 0`, or larger than `custody_len − 18` | `MalformedHeader` |
| non-zero padding in the custody record | `MalformedHeader` |
| an all-zero `key_id` (the header a writer builds before filling in the wrap) | `MalformedHeader` |
| a core cut short at 72 bytes; a custody record cut short | `MalformedHeader` |
| a complete header with no body | `TruncatedFile` |
| a body of 15 bytes | `TruncatedFile` |
| a two-chunk file cut right after its first chunk | `TruncatedFile` |
| a flipped commitment byte | `KeyMismatch` |
| a caller-held file opened with another key | `KeyMismatch` |
| a full final chunk re-encoded as a non-final chunk plus an empty final chunk | `UnsealFailed` |

**How they are generated.** Once, by a standalone script in `tests/vectors/generate.py`, run by
hand, with the output hand-checked against [file-format.md](file-format.md) offset by offset by a
second person. The script also builds the deliberately non-canonical case above, which no
conforming writer can produce. It stays in the repository as documentation of provenance and is
**not** wired into CI. There is no `--update-vectors` flag, deliberately.

**How they are consumed.** The test injects `dek` and `salt` through the pure seam in `vault.py`
that the architecture already requires — no monkey-patching — seals, and compares the full
container to `expected_container_hex`. Then it unseals `expected_container_hex` and compares to
`plaintext_hex`. Both directions, every case.

## 4. Layer 2 & 3 — Property-based testing

### 4.1 Round-trip

```python
@given(plaintext=st.binary(max_size=200_000), context=contexts())
def test_roundtrip(plaintext, context):
    assert unseal(seal(plaintext, context), context) == plaintext
```

Hypothesis will not find the chunk boundary on its own — 65536 is a needle in a 200 KB
haystack — so the sizes are supplied explicitly:

```python
BOUNDARIES = [0, 1, 15, 16, 17, 65535, 65536, 65537, 131071, 131072, 131073]
```

Framing bugs live at exactly those numbers.

**Stream shapes** ([ADR-0031](decisions.md#adr-0031-the-stream-io-contract-full-segments-full-writes-blocking-streams)).
Every test above uses `BytesIO`, which never returns a short read. Real sources do:

```python
@given(plaintext=st.binary(max_size=200_000), reads=st.lists(st.integers(1, 70_000), min_size=1))
def test_short_reads_and_partial_writes_change_nothing(plaintext, reads):
    trickle = TrickleStream(plaintext, read_sizes=reads)   # short reads, single bytes included
    sink = PartialWriteSink()                              # accepts part of each write
    seal_with(trickle, sink, dek=DEK, salt=SALT)
    assert sink.getvalue() == seal_with(BytesIO(plaintext), BytesIO(), dek=DEK, salt=SALT)
```

**Readers** ([ADR-0032](decisions.md#adr-0032-pull-style-readers-vaultsealed-and-vaultunsealed-seekable-when-the-source-is)):

- `vault.sealed()` produces the same bytes as `vault.seal()` for the same `dek` and `salt`.
- Reading `vault.unsealed()` to the end returns the plaintext, through `read`, `readinto` and
  `chunks()` alike.
- **Random access:** for arbitrary `(offset, length)` pairs, `reader.seek(offset);
  reader.read(length)` equals `plaintext[offset:offset + length]`, and `reader.size` equals
  `len(plaintext)`.

Also property-tested:

- **Canonicalization** — key order does not affect the encoding; distinct dictionaries never
  collide (`{"a|b": "c"}` vs `{"a": "b|c"}`, `1` vs `"1"` vs `True`); every accepted value
  round-trips through the encoder; every rejected type, subclasses included, raises
  `UsageError`.
- **Header** — `Header.from_bytes(h.to_bytes()) == h` for arbitrary valid headers in every
  custody mode, and `from_bytes` never raises anything outside `FormatError` for arbitrary inputs
  up to 73 + 4 096 bytes.

### 4.2 The adversarial suite

One property, applied to arbitrary mutations of a sealed file:

> **No mutation of the blob ever yields plaintext. It either raises, or produces nothing.**

```python
@given(blob=sealed_files(), mutation=mutations())
def test_no_mutation_yields_plaintext(blob, mutation):
    with pytest.raises(AegisError):
        unseal(mutation(blob))
    # and: the destination stream received no byte that is not a prefix of the plaintext
```

Instantiated mutations, each of which is a real attack that a named line of the design
blocks:

| Mutation | Blocked by |
|---|---|
| Flip any bit anywhere (header, ciphertext, tag) | GCM tags, the key commitment, strict parsing |
| Truncate at any offset | final-chunk flag → `TruncatedFile` where § 6.2 proves it, `UnsealFailed` inside a chunk |
| Append bytes | the extra data is not an authenticated chunk |
| Reorder two chunks | chunk counter in the nonce |
| Duplicate a chunk | chunk counter in the nonce |
| Drop a middle chunk | chunk counter in the nonce |
| Swap headers between two files | the body key and the core come from the header → `UnsealFailed` on chunk 0 |
| Transplant a body under a different header | same |
| Move a custody record into another header | custody AAD and commitment → `KeyMismatch` |
| Unseal with a different context | context hash in the chunk AAD → `UnsealFailed` |
| Unseal with a different KEK | `UnknownKek` |
| Unseal a caller-held file with a different key | commitment → `KeyMismatch` |
| Change the custody byte | `MalformedHeader`, `UsageError` or `UnknownKek` — never plaintext |
| Change `custody_len`, `payload_len` or padding | strict parsing → `MalformedHeader`, or a failed unwrap |
| Open a truncated file through a seekable reader | final chunk checked at open → raises before any byte |

The suite asserts *that it raises*, not *which* error, except where the design promises a
specific one: `TruncatedFile` where [file-format.md § 6.2](file-format.md#62-unsealing) proves
it, `UnknownKek`, `KeyMismatch`, `MalformedHeader`.

Hypothesis settings: `derandomize=False` in CI, with a nightly high-`max_examples` run, so that
CI stays fast but coverage keeps growing. The example database (`.hypothesis/`) is git-ignored;
every failure Hypothesis finds is pinned as an explicit `@example(...)` on the property it broke,
where a reviewer can read it ([ADR-0037](decisions.md#adr-0037-smaller-resolutions), Q17).

## 5. Layer 4 — Constant memory as a tested invariant

```python
def test_seal_uses_constant_memory():
    src = SyntheticStream(512 * 1024 * 1024)   # generated, never touches disk
    tracemalloc.start()
    vault.seal(src, NullSink(), context={"k": "v"})
    _, peak = tracemalloc.get_traced_memory()
    assert peak < CEILING          # 1 MiB — performance.md P3
```

The source is a generator-backed stream, so the test needs no disk and no fixture file. The sink
discards. The ceiling is a constant in the test file with a comment explaining how it was
chosen; raising it requires a reviewer to agree in the PR.

Run for `seal`, `unseal`, `unseal_to_path`, `sealed` and `unsealed` — forward-only and seekable —
in every custody mode. Marked `slow`, always run in CI, and this is what turns "streaming" in the
README from marketing into a verifiable fact.

## 6. Layer 5 — Rotation and dogfood

**Rotation touches only the custody record.**

```python
def test_rotation_leaves_body_byte_identical():
    before = path.read_bytes()
    record = slice(73, 73 + CUSTODY_LEN)                  # 66 bytes for a local KEK
    vault_v2.rotate(path)                                 # primary=KEK_V2, previous=[KEK_V1]
    after = path.read_bytes()
    assert after[:73] == before[:73]                      # the core: salt, commitment, lengths
    assert after[record.stop:] == before[record.stop:]    # the entire body
    assert after[record] != before[record]                # key_id and wrapped DEK re-wrapped
    assert unseal(after, vault=vault_v2) == plaintext
```

Direct proof of the design claim, and the test that would have caught the AAD/rotation
contradiction in `initial-spec.md` § 6 on day one
([ADR-0014](decisions.md#adr-0014-chunk-aad-covers-the-immutable-header-core-only)).

Also, for `vault.rotate`:
- rotating twice is idempotent in effect;
- rotating to the key already in use is a no-op that writes nothing;
- an unknown `key_id` raises `UnknownKek`, and a commitment mismatch raises `KeyMismatch`; both
  leave the file byte-identical;
- a process killed mid-rotation leaves a file that still opens;
- **a torn write** — a custody record half old, half new, with its journal on disk — is
  recovered on the next rotation
  ([ADR-0035](decisions.md#adr-0035-rotation-write-path-torn-write-journal-public-calls-recursive-runs)),
  and a journal with a bad checksum is discarded without touching the file.

For `vault.rewrap`, the destination's body is byte-identical to the source's, and the
destination opens with the new key.

**The dogfood test — the public API is complete.**

```python
def test_adapters_import_only_public_api():
    for module in walk("src/aegis/cli"):
        for imported in ast_imports(module):
            assert imported in PUBLIC_API or not imported.startswith("aegis.")
```

If the CLI needs a private import, that is not an implementation detail — it is proof that the
public API is incomplete. A structural test, not a convention. The same test will walk
`src/aegis/contrib/django` when the V2 adapter lands. A fake KMS key source in the test suite —
importing nothing but the public API — proves the `KeySource` protocol is complete, in the same
spirit.

**No import cycles, and randomness in one place.** The same AST walk asserts the dependency
direction declared in [architecture.md § 2](architecture.md#2-module-map), that `format.py`,
`context.py`, `envelope.py` and `stream.py` never import `os`, `random` or `secrets`, and that
`os.urandom` appears in `vault.py` only.

**Secrets never leak into text.**

```python
def test_repr_and_errors_never_contain_key_material():
    # every object that touches keys, both readers, and every error raised in a failure scenario
    assert SECRET.hex() not in repr(obj) and SECRET not in str(exc).encode()
```

## 7. Unit tests worth naming

- `format.py`: every rejection path of [file-format.md § 2](file-format.md#2-header) — magic,
  version, suite, custody byte, `custody_len` per mode, `payload_len`, padding, zero `key_id`,
  every short read — and the order in which they fire (Q20). Every offset asserted against a
  literal, so a field cannot move silently.
- `context.py`: a table of (dict → expected hex) cases; every rejected type, including `IntEnum`,
  `StrEnum`, a `str` subclass, `bytearray` and `memoryview`; `int` bounds at ±2⁶³; a lone surrogate
  in a key; `True` vs `1`; a 4 GiB length rejection (constructed, not allocated).
- `envelope.py`: the key schedule and the local wrap against the vectors' derived values; a
  commitment mismatch; `kek_id`.
- `keys.py`: for each of `EnvKey`, `FileKey` and `BytesKey` — a missing variable or file, a bad
  encoding, a wrong length, a duplicate primary/previous, a printable-ASCII key, a key with fewer
  than 16 distinct byte values, selection by `key_id`. `FileKey` with one trailing `\n` or `\r\n`
  (accepted) and with two (rejected). `CallerHeld` with a missing key, a short key, a key of the
  wrong type.
- `stream.py`: the I/O contract — `None` from `read` or `write`, a `read` that returns more than
  asked, a text stream — each raising `UsageError`; `MAX_CHUNKS` lowered through its parameter,
  in both directions (Q22).
- `errors.py`: the hierarchy is asserted explicitly — `KeyMismatch` and `TruncatedFile` are
  `UnsealFailed`s, which are `AegisError`s — because an `except UnsealFailed` in user code depends
  on it.
- `vault.py`:
  - `unseal_to_path` leaves no file behind on failure and no temporary file on success; it
    `fsync`s before renaming, syncs the directory on POSIX, and creates the file with mode `0600`;
  - every custody mismatch of Q26 raises its specified class before reading a byte;
  - `seal_bytes` on `CallerHeld()` raises `UsageError` (Q46).

## 8. Coverage

| Target | Requirement |
|---|---|
| `stream.py`, `envelope.py`, `format.py` | **100 % branch coverage, non-negotiable.** CI fails below. |
| `context.py`, `keys.py`, `readers.py`, `rotate.py` | 95 % lines |
| everything else | 90 % lines |

Enforced per-file, not as a project average — an average lets the risky module hide behind
the CLI's coverage. `coverage` alone cannot do that, so `tools/coverage_gates.py` applies
this table ([stack.md § 6.3](stack.md#63-tool-configuration)). Coverage is a floor, not
evidence: 100 % on `stream.py` means every branch ran, not that every attack was tried. That
is what layer 3 is for.

**Mutation testing** (`mutmut`) is run against `stream.py`, `envelope.py`, `format.py` and
`context.py` before 1.0 and then periodically — not on every PR. A surviving mutant is a missing
test.

## 9. CI

| Axis | Values |
|---|---|
| Python | 3.11, 3.12, 3.13, 3.14 ([ADR-0023](decisions.md#adr-0023-python-floor-follows-cpythons-support-window)) |
| OS | Linux, macOS, Windows (Windows matters: `os.replace`, `fsync`, no `pwrite`, line endings) |
| `cryptography` | oldest supported (`uv pip install --resolution lowest-direct`, [ADR-0040](decisions.md#adr-0040-the-floor-job-installs-the-published-floors-not-the-lock)) + newest (`uv.lock`) |

Every PR runs: `ruff`, `mypy --strict`, `zizmor`, the full suite, the coverage gates. The
nightly job adds a high-`max_examples` Hypothesis run and mutation testing.

Benchmarks run on a schedule, publish a trend, and **never gate a PR** — a noisy runner
must not block a correct change. They do gate a release; objectives and gates are in
[performance.md](performance.md).

## 10. What a pull request must include

- A test that fails before the change and passes after it.
- For a bug in `stream.py`, `envelope.py`, `format.py` or `context.py`: a **property** or a
  **negative vector**, not only an example.
- No change to `tests/vectors/*.json`. If a change requires one, it is a format change and
  needs a version byte and its own discussion first.
- Coverage gates still met per-file.

## 11. What the suite does not do

- It does not prove the cryptography is correct. It proves this implementation matches a
  frozen specification and resists the attacks we enumerated.
- It does not replace review. The public review of `stream.py`, `envelope.py` and the format
  before 1.0 is a release blocker ([security.md § 4.1](security.md#41-the-accepted-risk)).
- It does not test `cryptography` or OpenSSL. Their correctness is an assumption, stated in
  [security.md § 1](security.md#1-threat-model).
