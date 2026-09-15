# Performance objectives

What "fast enough" means for Aegis, how it is measured, and which numbers block a release.
The memory model is described in [architecture.md § 7](architecture.md#7-memory-and-performance-model);
this document turns it into targets.

---

## 1. Principles

1. **Aegis owns its overhead, not AES.** How fast AES-GCM runs belongs to OpenSSL and the
   CPU. What Aegis promises is not to waste it. Throughput objectives are therefore ratios
   against raw AES-GCM measured in the same run, plus a conservative absolute floor.
2. **Deterministic properties are tests, not benchmarks.** A memory ceiling or a count of
   bytes read does not depend on a noisy runner, so it is a blocking test on every PR.
3. **Noisy properties are benchmarks.** They never gate a PR
   ([tests.md § 9](tests.md#9-ci)), but they gate a release.
4. **Security beats speed.** No objective justifies a native extension, a nonce shortcut, or
   growing `stream.py` past what a reviewer can audit in one sitting. If an objective
   conflicts with a rule in [contributing.md § 3](contributing.md#3-the-rules-that-are-not-negotiable),
   the objective is revised.

## 2. Baseline (2026-09-14)

No Aegis code exists yet. The baseline measures a **model of the planned hot path**, built
from the same primitives: read one segment ahead, build the nonce, `AESGCM.encrypt`, write to
a discarding sink. The small-payload model runs the full per-file cost (three `os.urandom`
calls, HKDF, the DEK wrap, both labelled SHA-256 hashes, one chunk).

| Environment | |
|---|---|
| CPU | Apple M1 (4 performance + 4 efficiency cores), ARMv8 crypto extensions |
| OS | macOS, Darwin 25.6 |
| Python | CPython 3.14.7 |
| `cryptography` | 50.0.1 |

| Measurement | Result |
|---|---|
| Raw AES-256-GCM encrypt, 64 KiB chunks | 5 949 MiB/s |
| Raw AES-256-GCM decrypt, 64 KiB chunks | 6 078 MiB/s |
| Streaming loop model, `BytesIO` → null sink | 4 996 MiB/s (**84 %** of raw) |
| `seal_bytes` model, 1 KiB, KEK custody | p50 **11.4 µs**, p99 **16.7 µs** |
| Threads running whole seals: 1 / 2 / 4 | 5 600 / 10 291 / 14 814 MiB/s (**2.6×** at 4) |
| `tracemalloc` peak, streaming loop over 256 MiB | **192 KiB** |
| Importing the `cryptography` AEAD and HKDF modules | ≈ 9 ms |

What the baseline shows:

- The Python loop costs about 16 % against raw AES-GCM. That is the budget Aegis works in.
- The fixed per-file cost is in the tens of microseconds. Small payloads are dominated by
  the call overhead, not by cryptography.
- **`cryptography` releases the GIL during AES-GCM**, so `ThreadPoolExecutor` really scales,
  as [architecture.md § 8](architecture.md#8-concurrency) recommends. This was measured on
  50.0.1 only and must be re-verified against the version floor
  ([stack.md § 3.2](stack.md#32-cryptography)).
- The per-chunk buffers fit in a few hundred KiB.

## 3. Objectives

| ID | Objective | Target | Baseline | Kind |
|---|---|---|---|---|
| **P1** | Streaming efficiency: `seal` and `unseal` throughput relative to raw AES-GCM on 64 KiB segments, same machine, same run | **≥ 75 %** | 84 % | benchmark |
| **P2** | Absolute throughput: single `seal` / `unseal` call, in-memory source → null sink | **≥ 1 GiB/s** on the reference runners | 4.9 GiB/s | benchmark |
| **P3** | Constant memory: `tracemalloc` peak for `seal`, `unseal` and `unseal_to_path` of 512 MiB, both custody modes | **≤ 1 MiB** | 192 KiB | blocking test |
| **P4** | Size independence: peak at 512 MiB versus peak at 16 MiB | **≤ +64 KiB** | — | blocking test |
| **P5** | Small payloads: `seal_bytes` and `unseal_bytes` of 1 KiB, KEK custody | **p50 ≤ 50 µs, p99 ≤ 200 µs** | 11.4 / 16.7 µs | benchmark |
| **P6** | Size overhead | **exactly** `94 + 16 × max(1, ⌈n / 65536⌉)` bytes | — | property test |
| **P7** | Rotation I/O: per file, read exactly 94 bytes and write exactly 80; the body is never read | **exact** | — | blocking test |
| **P8** | Rotation CPU per file, excluding I/O | **≤ 1 ms** | — | benchmark |
| **P9** | `aegis inspect` on a seekable file reads exactly 94 bytes (sizes come from `stat`) and never decrypts | **exact** | — | blocking test |
| **P10** | Time to first byte: `unseal` emits the first plaintext after consuming at most `94 + 65552 + 1` bytes; `seal` writes the header before reading any plaintext | **exact** | — | blocking test |
| **P11** | Parallel scaling: 4 whole `seal` calls in `ThreadPoolExecutor(4)` on ≥ 4 physical cores, versus 1 | **≥ 2×** | 2.6× | benchmark |
| **P12** | Import isolation: `import aegis` loads neither `django`, `click` nor `aegis.cli` | **exact** | — | blocking test |
| **P13** | Import time: `import aegis`, including `cryptography` | **≤ 50 ms** on the reference runners | ≈ 9 ms for `cryptography` | benchmark |

Notes:

- **P1 and P2 together.** P1 catches overhead Aegis adds. P2 catches a runner or a
  `cryptography` build without hardware acceleration, which P1 alone would hide.
- **P3 and P4 together.** P3 bounds the peak. P4 catches slow accumulation, such as a growing
  list or a `b"".join`, that a generous ceiling could absorb. This makes concrete the
  ceiling [tests.md § 5](tests.md#5-layer-4--constant-memory-as-a-tested-invariant) asks for.
- `tracemalloc` sees only Python allocations. Memory allocated inside OpenSSL is not counted.
  Process RSS is too noisy to gate on.
- **P7, P9 and P10** are counted with a stream wrapper that records every `read` and `write`.
- P6 is already implied by [file-format.md § 4.1](file-format.md#41-framing); listing it here
  makes size accounting a named promise.

## 4. Reference hardware

| Runner | CPU class | Role |
|---|---|---|
| GitHub Actions `ubuntu-latest` | x86-64 with AES-NI and PCLMULQDQ | absolute targets (P2, P5, P8, P13) |
| GitHub Actions `macos-latest` | Apple Silicon, ARMv8 crypto extensions | absolute targets (P2, P5, P8, P13) |
| GitHub Actions `windows-latest` | x86-64 | correctness only; not benchmarked |

**CPUs without AES hardware acceleration** are outside the objectives. OpenSSL falls back to
constant-time software AES, which is far slower. The answer there is the post-1.0
XChaCha20-Poly1305 suite ([roadmap.md § Post-1.0](roadmap.md#post-10-backlog)), not tuning
the AES path.

## 5. How it is measured

```
benchmarks/
├── conftest.py              # synthetic sources, null sink, counting stream wrapper
├── bench_throughput.py      # P1, P2 — raw AES-GCM baseline first, then seal/unseal
├── bench_small.py           # P5
├── bench_rotate.py          # P8
├── bench_parallel.py        # P11
└── bench_import.py          # P13 — fresh interpreter per sample
```

- **Same-run baseline.** Every throughput benchmark measures raw AES-GCM over the same
  64 KiB segments in the same process immediately before Aegis. P1 is the ratio of the two,
  which cancels most runner noise.
- **Sizes:** a 16 MiB warm-up, then 512 MiB. Sources are pre-allocated or generator-backed,
  and the sink discards, so disk speed never enters the result.
- **Latency:** at least 20 000 iterations after warm-up with `perf_counter_ns`, reporting
  p50 and p99. Never the mean alone.
- **Import time:** at least 10 fresh interpreters, taking the median.
- **Output:** `pytest-benchmark` JSON, uploaded as a workflow artifact on every run, with
  a trend kept across releases.
- The blocking tests (P3, P4, P6, P7, P9, P10, P12) live in `tests/invariants/` and
  `tests/property/`, not in `benchmarks/`.

## 6. Gates

| Kind | Objectives | When | A miss… |
|---|---|---|---|
| Blocking test | P3, P4, P6, P7, P9, P10, P12 | every PR, every matrix cell | fails the PR |
| Benchmark | P1, P2, P5, P8, P11, P13 | weekly, on release tags, manually | opens an issue |
| Release check | all benchmarks | the release candidate, on both reference runners | **blocks the release** — 1.0 and every minor |

**Regression rule.** A P1 drop of more than 10 percentage points against the previous release
is investigated before release, even if still above target.

## 7. Non-goals

- **Beating `cryptography` or OpenSSL.** Aegis sits on top of them; raw AES-GCM is the
  ceiling.
- **Using several cores inside one call.** No internal threading
  ([ADR-0007](decisions.md#adr-0007-no-async-api-in-10)). Parallelism is whole calls in a pool.
- **Async throughput.** There is no async API.
- **Speed with slow I/O.** When a disk or a network is the bottleneck, Aegis only promises
  not to buffer (P3). End-to-end speed belongs to the application.
- **Tunable chunk size.** Fixed by the suite
  ([ADR-0010](decisions.md#adr-0010-64-kib-chunks)).
- **Free-threaded CPython.** Not benchmarked in 1.0.

## 8. Changing an objective

- **Tightening a target:** a PR that edits this document, with benchmark output from both
  reference runners.
- **Loosening a target:** the same, plus the reason in the PR description. Loosening P3 or P4
  also needs a reviewer's explicit agreement, as
  [tests.md § 5](tests.md#5-layer-4--constant-memory-as-a-tested-invariant) already requires.
- **Changing an exact objective** (P6, P7, P9, P10) is a format or architecture change and
  follows those documents' rules instead.
