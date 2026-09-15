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
   If a test needs to patch `os.urandom` to reach `stream.py`, the architecture broke, not
   the test ([architecture.md § 4](architecture.md#4-the-purity-boundary-randomness-lives-at-the-edges)).
4. **Failure modes are asserted, not observed.** Every test that expects an error asserts
   the *specific* class. `pytest.raises(AegisError)` is too weak to be a test.
5. **Never assert on a message string.** Errors carry structured attributes for that.
6. **No test touches the network, the clock, or a real home directory.**

## 2. The layers

| # | Layer | Answers | Tool | Gate |
|---|---|---|---|---|
| 1 | Frozen vectors (KAT) | "Will today's file open in five years?" | `pytest` + JSON | blocking |
| 2 | Property round-trip | "Does it work for every input, especially at the boundaries?" | Hypothesis | blocking |
| 3 | Adversarial | "Can a tampered file ever produce plaintext?" | Hypothesis | blocking |
| 4 | Constant memory | "Is 'streaming' true, or marketing?" | `tracemalloc` | blocking |
| 5 | Rotation & dogfood | "Does rotation really not touch the body? Is the public API complete?" | `pytest` + AST | blocking |
| 6 | Unit | "Does each module do its one job?" | `pytest` | blocking |
| 7 | Integration | "Do Django and the CLI work end to end?" | `pytest-django`, subprocess | blocking |
| 8 | Benchmarks | "Did throughput regress?" | `pytest-benchmark` | **not** a PR gate |

Layers 1–5 are the interesting ones and get their own sections. Write layer 1 first — before
`vault.py` exists.

```
tests/
├── vectors/v1.json            # frozen. Read-only forever.
├── unit/                      # format, context, keys, errors
├── property/                  # round-trip, canonicalization
├── adversarial/               # the mutation property
├── invariants/                # memory ceiling, rotation body-identity, dogfood imports
└── integration/               # django, cli
benchmarks/                    # separate suite, separate command
```

## 3. Layer 1 — Frozen vectors (KAT)

A versioned JSON file pinning, for fixed inputs, the exact expected output byte for byte.

```json
{
  "format_version": 1,
  "generated": "2026-…",
  "note": "FROZEN. Regenerating this file is a format change. See docs/file-format.md §8.",
  "cases": [
    {
      "name": "kek-custody/empty-plaintext",
      "kek_b64": "…", "dek_hex": "…", "salt_hex": "…", "nonce_prefix_hex": "…",
      "context": [["user_id", "int", "42"], ["kind", "str", "invoice"]],
      "plaintext_hex": "",
      "expected_container_hex": "41454700 01 01 00 …"
    }
  ]
}
```

**Required cases**, each in both custody modes:

- empty plaintext (one chunk, zero-length — the rule that keeps a bare header invalid)
- 1 byte
- 65535, 65536, 65537 bytes (the chunk boundary in all three directions)
- exactly 2 × 65536 bytes (a full final chunk, no empty trailing chunk)
- a context exercising every type tag, including `bool` versus `int` and a key whose UTF-8
  sort order differs from its code-point order
- an empty context `{}` ([ADR-0020](decisions.md#adr-0020-context-is-required-but-may-be-empty))

Plus **negative vectors** — byte sequences that must be rejected, with the exact expected
exception: bad magic, `version=2`, `suite=2`, a reserved flag bit set, a non-zero custody
block in caller-held mode, a 93-byte file, a body of 15 bytes.

> **Open.** An all-zero custody block under KEK custody is missing from this list
> ([Q25](architecture.md#16-open-questions)), and the expected class for a short non-Aegis file
> depends on [Q20](architecture.md#16-open-questions).

**How they are generated.** Once, by a standalone script in `tests/vectors/generate.py`,
run by hand, with the output hand-checked against
[file-format.md](file-format.md) offset by offset by a second person. The script stays in
the repository as documentation of provenance and is **not** wired into CI. There is no
`--update-vectors` flag, deliberately.

**How they are consumed.** The test injects `dek`, `salt` and `nonce_prefix` through the
same seam the architecture already requires — no monkey-patching — seals, and compares the
full container to `expected_container_hex`. Then it unseals `expected_container_hex` and
compares to `plaintext_hex`. Both directions, every case.

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

Also property-tested:

- **Canonicalization** — key order does not affect the encoding; distinct dictionaries never
  collide (`{"a|b": "c"}` vs `{"a": "b|c"}`, `1` vs `"1"` vs `True`); every accepted value
  round-trips through the encoder; every rejected type raises `UsageError`.
- **Header** — `Header.from_bytes(h.to_bytes()) == h` for arbitrary valid headers, and
  `from_bytes` never raises anything outside `FormatError` for arbitrary 94-byte inputs.

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
| Flip any bit anywhere (header, ciphertext, tag) | GCM tag + header in AAD |
| Truncate at any offset | final-chunk marker → `TruncatedFile` |
| Append bytes | the extra data is not an authenticated chunk |
| Reorder two chunks | chunk counter in the nonce |
| Duplicate a chunk | chunk counter in the nonce |
| Drop a middle chunk | chunk counter in the nonce |
| Swap headers between two files | `nonce_prefix` in the chunk AAD |
| Transplant a body under a different header | same |
| Move a wrapped DEK into another header | wrap AAD binds it to magic/version/suite/flags/`kek_id` |
| Unseal with a different context | context hash in the chunk AAD |
| Unseal with a different KEK | `UnknownKek`, or unwrap failure |
| Set a reserved flag bit | strict header validation |
| Non-zero custody block in caller-held mode | strict header validation |
| Flip the custody flag bit | unwrap fails / `UsageError` — never plaintext |

The suite asserts *that it raises*, not *which* error, except where the design promises a
specific one (`TruncatedFile`, `UnknownKek`, `MalformedHeader`).

Hypothesis settings: a `.hypothesis` example database committed for the failing cases we
have found, `derandomize=False` in CI with a nightly high-`max_examples` run so that CI
stays fast but coverage keeps growing. Committing the database contradicts roadmap.md M0,
which ignores `.hypothesis/`; that is open as [Q17](architecture.md#16-open-questions).

## 5. Layer 4 — Constant memory as a tested invariant

```python
def test_seal_uses_constant_memory():
    src = SyntheticStream(512 * 1024 * 1024)   # generated, never touches disk
    tracemalloc.start()
    vault.seal(src, NullSink(), context={"k": "v"})
    _, peak = tracemalloc.get_traced_memory()
    assert peak < CEILING          # 1 MiB — performance.md P3
```

The source is a generator-backed stream so the test needs no disk and no fixture file. The
sink discards. The ceiling is a constant in the test file with a comment explaining how it
was chosen; raising it requires a reviewer to agree in the PR.

Run for `seal` and `unseal`, in both custody modes. Marked `slow`, always run in CI, and
this is what turns "streaming" in the README from marketing into a verifiable fact.

## 6. Layer 5 — Rotation and dogfood

**Rotation touches only the custody block.**

```python
def test_rotation_leaves_body_byte_identical():
    before = path.read_bytes()
    rotate(path, primary=KEK_V2, previous=[KEK_V1])
    after = path.read_bytes()
    assert after[87:] == before[87:]      # nonce_prefix + entire body untouched
    assert after[:7] == before[:7]        # magic, version, suite, flags untouched
    assert after[7:87] != before[7:87]    # kek_id, salt, wrapped_dek re-wrapped
    assert unseal(after, kek=KEK_V2) == plaintext
```

Direct proof of the design claim, and the test that would have caught the AAD/rotation
contradiction in `initial-spec.md` § 6 on day one
([ADR-0014](decisions.md#adr-0014-chunk-aad-covers-the-immutable-header-core-only)).

Also: rotating twice is idempotent in effect; rotating to the KEK already in use is a no-op
that does not rewrite the file; rotating with an unknown `kek_id` raises `UnknownKek` and
leaves the file untouched; a rotation whose process is killed leaves a file that still opens
with the old KEK. Behaviour under a **torn** write (power loss) is not yet specified; see
[Q8 and Q9](architecture.md#16-open-questions). Whatever Q9 decides gets a test that
simulates a half-written custody block.

**The dogfood test — the public API is complete.**

```python
def test_adapters_import_only_public_api():
    for module in walk("aegis/contrib", "aegis/cli"):
        for imported in ast_imports(module):
            assert imported in PUBLIC_API or not imported.startswith("aegis.")
```

If the Django adapter or the CLI needs a private import, that is not an implementation
detail — it is proof that the public API is incomplete. A structural test, not a
convention.

**No import cycles.** The same AST walk asserts the dependency direction declared in
[architecture.md § 2](architecture.md#2-module-map).

**Secrets never leak into text.**

```python
def test_repr_and_errors_never_contain_key_material():
    # every object that touches keys, and every error raised in a failure scenario
    assert SECRET.hex() not in repr(obj) and SECRET not in str(exc).encode()
```

## 7. Unit tests worth naming

- `format.py`: every rejection path (magic, version, suite, reserved bits, custody
  zero-ness, short read); every offset asserted against a literal, so a field cannot move
  silently.
- `context.py`: a table of (dict → expected hex) cases; every rejected type; `int` bounds
  at ±2⁶³; a lone surrogate in a key; `True` vs `1`; a 4 GiB length rejection (constructed,
  not allocated).
- `keys.py`: `EnvKey` with a missing variable, a wrong-length key, a bad encoding, a
  duplicate primary/previous, selection by `kek_id`, `UnknownKek` when absent;
  `CallerHeld` with a missing key, a short key, a key of the wrong type.
- `errors.py`: the hierarchy is asserted explicitly — `TruncatedFile` is an `UnsealFailed`
  is an `AegisError` — because a `except UnsealFailed` in user code depends on it.
- `vault.py`: `unseal_to_path` leaves no file behind on failure, leaves no temp file behind
  on success, and `fsync`s before renaming.

## 8. Coverage

| Target | Requirement |
|---|---|
| `stream.py`, `format.py` | **100 % branch coverage, non-negotiable.** CI fails below. |
| `context.py`, `keys.py`, `rotate.py` | 95 % lines |
| everything else | 90 % lines |

Enforced per-file, not as a project average — an average lets the risky module hide behind
the CLI's coverage. Coverage is a floor, not evidence: 100 % on `stream.py` means every
branch ran, not that every attack was tried. That is what layer 3 is for.

**Mutation testing** (`mutmut`) is run against `stream.py`, `format.py` and `context.py`
before 1.0 and then periodically — not on every PR. A surviving mutant is a missing test.

## 9. CI

| Axis | Values |
|---|---|
| Python | 3.10, 3.11, 3.12, 3.13 |
| OS | Linux, macOS, Windows (Windows matters: `os.replace`, `fsync`, line endings) |
| `cryptography` | oldest supported (`uv sync --resolution lowest-direct`) + newest (`uv.lock`) |
| Django | LTS + latest, in the adapter job only |

Every PR runs: `ruff`, `mypy --strict`, the full suite, the coverage gates. The nightly job
adds a high-`max_examples` Hypothesis run and mutation testing.

Benchmarks run on a schedule, publish a trend, and **never gate a PR** — a noisy runner
must not block a correct change. They do gate a release; objectives and gates are in
[performance.md](performance.md).

## 10. What a pull request must include

- A test that fails before the change and passes after it.
- For a bug in `stream.py`, `format.py` or `context.py`: a **property** or a **negative
  vector**, not only an example.
- No change to `tests/vectors/*.json`. If a change requires one, it is a format change and
  needs a version byte and its own discussion first.
- Coverage gates still met per-file.

## 11. What the suite does not do

- It does not prove the cryptography is correct. It proves this implementation matches a
  frozen specification and resists the attacks we enumerated.
- It does not replace review. The public review of `stream.py` before 1.0 is a release
  blocker ([security.md § 4.1](security.md#41-the-accepted-risk)).
- It does not test `cryptography` or OpenSSL. Their correctness is an assumption, stated in
  [security.md § 1](security.md#1-threat-model).
