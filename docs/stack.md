# Stack

Every dependency and tool, the version policy for each, and why it was chosen over the
alternatives. Floors are as of 2026-09-14; the versions locked in `uv.lock` are those of
**2026-10-19**, when M0 created it.

---

## 1. Principles

1. **One runtime dependency.** The core depends on `cryptography` and nothing else. A second
   one needs an ADR ([contributing.md § 2](contributing.md#2-before-you-open-a-pull-request)).
2. **Floors for runtime dependencies, a lockfile for development.** Users get security
   updates without a release from us; contributors and CI get byte-identical tool versions
   ([security.md § 9](security.md#9-supply-chain)).
3. **Pure Python.** No native code of our own. Speed comes from OpenSSL through
   `cryptography` ([performance.md](performance.md)).
4. **The standard library first.** A stdlib module beats a dependency, even a small one.
5. **CI runs what contributors run.** The same `uv` commands, locally and in CI.
6. **Users never need our tooling.** `pip install aegis-voynan` works without `uv`,
   Hatchling or anything else in this document except `cryptography`.

## 2. At a glance

| Layer | Choice | Version policy |
|---|---|---|
| Language | CPython | 3.11–3.14 ([ADR-0023](decisions.md#adr-0023-python-floor-follows-cpythons-support-window)) |
| Cryptography | `cryptography` | `>=44.0`, no ceiling |
| Build backend | Hatchling | pinned in `[build-system]` ([ADR-0022](decisions.md#adr-0022-hatchling-as-the-build-backend)) |
| Project and environment tool | `uv` | `required-version`, pinned in CI ([ADR-0024](decisions.md#adr-0024-uv-for-development-and-ci)) |
| Distribution | PyPI `aegis-voynan`, pure-Python wheel + sdist | [ADR-0018](decisions.md#adr-0018-distribute-as-aegis-voynan-import-as-aegis) |
| CLI extra | `click` | `>=8.1` ([ADR-0021](decisions.md#adr-0021-the-cli-is-built-on-click)) |
| Django | — | not a 1.0 dependency; the adapter is V2 ([ADR-0034](decisions.md#adr-0034-the-django-adapter-moves-to-v2)) |
| Lint + format | `ruff`, rules in § 6.3 | locked in `uv.lock` |
| Types | `mypy --strict` | locked |
| Supply-chain checks | `pip-audit` (dependencies), `zizmor` (workflows) | locked |
| Tests | `pytest`, `pytest-cov`, `hypothesis` | locked |
| Mutation testing | `mutmut` | locked |
| Benchmarks | `pytest-benchmark` | locked |
| Git hooks | `pre-commit` | locked |
| CI/CD | GitHub Actions, PyPI trusted publishing (OIDC) | actions pinned by commit SHA |
| Repository | [github.com/voynan/aegis](https://github.com/voynan/aegis) | — |

## 3. Runtime

### 3.1 Python

**Decision ([ADR-0023](decisions.md#adr-0023-python-floor-follows-cpythons-support-window),
accepted 2026-10-18):** each release supports every CPython that still receives security fixes
on its release date — **3.11 to 3.14** for a 1.0 before 2027-10-31. The CI matrix is 3.11–3.14.

| Version | Released | End of life |
|---|---|---|
| 3.10 | 2021-10 | **2026-10-31** — before any Aegis release; not supported |
| 3.11 | 2022-10 | 2027-10-31 |
| 3.12 | 2023-10 | 2028-10-31 |
| 3.13 | 2024-10 | 2029-10-31 |
| 3.14 | 2025-10 | 2030-10-31 |

- A 3.10 floor would have meant shipping a security library whose minimum interpreter no longer
  gets security fixes on release day.
- Strict SPEC 0 (versions released in the last three years) would put the floor at 3.13 by 1.0,
  excluding Debian 12 (3.11) and many deployments the target users run.

CI installs interpreters with `uv python install`, so the matrix does not depend on what a
runner image ships. Free-threaded builds (`3.13t`, `3.14t`) are not in the 1.0 matrix.

### 3.2 `cryptography`

Used for exactly two primitives, and nothing else:

| Import | For |
|---|---|
| `cryptography.hazmat.primitives.ciphers.aead.AESGCM` | chunk encryption, local DEK wrap |
| `cryptography.hazmat.primitives.kdf.hkdf.HKDF` | the per-file key schedule (body key, nonce prefix, commitment) and the wrap key |

`AESGCM.encrypt_into`/`decrypt_into` and `HKDF.extract` arrived in `cryptography` 47.0. They
would save one allocation per chunk and two HMACs per file. They are an optimization for a
later floor raise, not a 1.0 requirement; the code uses one path, the one the floor supports.

- **Floor `>=44.0`** (2024-11). `cryptography` maintains only its latest release, so a floor
  is a courtesy to applications that pin, not a support branch. 44.0 ships `abi3` wheels
  that install on every Python in the matrix.
- **Both ends are tested.** CI runs the locked (latest) resolution and a
  `uv sync --resolution lowest-direct` job that installs exactly the floors
  ([tests.md § 9](tests.md#9-ci)). A floor that is not tested is a guess.
- **Raised** in a minor Aegis release when `cryptography` fixes something that touches
  AES-GCM, HKDF or its bundled OpenSSL.
- **Never a ceiling.**
- Its wheels bundle OpenSSL, which provides the AES hardware acceleration the performance
  objectives assume ([performance.md § 4](performance.md#4-reference-hardware)).

### 3.3 Standard library

| Module | Used for |
|---|---|
| `hashlib` | SHA-256 for `kek_id`, the AAD hashes, the custody AAD and the rotation journal's checksum |
| `hmac` | `compare_digest` for the key commitment |
| `os` | `urandom` (DEK and salt, in `vault.py` only); `replace` and `fsync` (`unseal_to_path`); `pwrite` and `fsync` (rotation) |
| `base64` | strict KEK decoding (`b64decode(..., validate=True)`, [ADR-0015](decisions.md#adr-0015-keks-in-environment-variables-are-base64)) |
| `io`, `tempfile` | stream handling and the readers; the temporary file of `unseal_to_path`, in the destination directory |
| `dataclasses` | frozen `Header`, `Receipt`, `FileInfo`, `RotationResult` |
| `typing` | `Protocol` for `KeySource` |
| `logging` | the `aegis` logger with a `NullHandler` |
| `importlib.metadata` | `aegis.__version__`, resolved lazily so it costs nothing at import |

**Platform note.** `os.pwrite` does not exist on Windows; rotation falls back to one `seek` and
one `write`, then `fsync`
([ADR-0035](decisions.md#adr-0035-rotation-write-path-torn-write-journal-public-calls-recursive-runs)).

## 4. Optional extras

### 4.1 `[cli]` — `click`

- **Why `click`.** It has no runtime dependencies of its own. `typer` adds `rich`,
  `shellingham` and `annotated-doc`. The CLI is five commands with a fixed exit-code
  contract ([architecture.md § 12](architecture.md#12-the-cli)) and binary standard streams
  (`click.get_binary_stream`). Type-hint-driven parsing and rich output are not worth three
  more packages in a security tool's install.
- **Entry point:** `[project.scripts] aegis = "aegis.cli.__main__:main"`, plus
  `python -m aegis.cli`.
- **Isolation:** `import aegis` never imports `click` (a test checks `sys.modules`).

### 4.2 Django — not in 1.0

The `[django]` extra and `pytest-django` arrive with the adapter in V2
([ADR-0034](decisions.md#adr-0034-the-django-adapter-moves-to-v2)). The plan records the
version policy to start from: floor at the LTS current on the adapter's release date (5.2 LTS
today, end of life 2028-04), tested against that LTS on the lowest supported Python and the
latest release on the newest ([dev/v2-django.md](dev/v2-django.md)).

## 5. Packaging

- **`pyproject.toml` only** (PEP 621). No `setup.py`, no `setup.cfg`.
- **Hatchling** builds the artifacts, invoked by `uv build`. It is maintained by the PyPA,
  needs one line of configuration for this layout, and keeps the build independent of `uv`:
  `python -m build` produces the same wheel.
- **The distribution name differs from the package directory**, so Hatchling cannot
  auto-discover it. The wheel target names it explicitly.
- **Development dependencies are a dependency group (PEP 735), not an extra.** An extra is
  part of the published metadata: `pip install "aegis-voynan[dev]"` would install our
  linters into a user's environment. A group never leaves the repository.
- **Wheel** `py3-none-any`. **sdist** includes `tests/vectors/`, so downstream packagers can
  run the frozen vectors, and `tools/`, which the unit tests load. Its contents are an
  allowlist (`only-include`), not "whatever is not ignored": Hatchling reads only the root
  `.gitignore` and includes untracked files, so a local build could otherwise ship a stray
  file.
- **`uv.lock` is committed.** It governs development and CI only; it is not published and
  does not constrain users.

```toml
[build-system]
requires = ["hatchling==1.32.4"]
build-backend = "hatchling.build"

[project]
name = "aegis-voynan"
version = "0.0.0"
description = "A simple, secure and streaming-friendly file encryption library built on modern cryptography."
readme = "README.md"                 # the PyPI page
requires-python = ">=3.11"          # ADR-0023
license = "MIT"
authors = [{ name = "Kaio Vinícios" }]
keywords = ["encryption", "aes-gcm", "envelope-encryption", "streaming", "kms"]
classifiers = [ … ]                  # Planning; Python 3.11–3.14; Security :: Cryptography; Typed
                                     # no license classifier: `license` is an SPDX expression (PEP 639)
dependencies = ["cryptography>=44.0"]

[project.optional-dependencies]      # published: what users can ask for
cli = ["click>=8.1"]                 # [django] arrives with the V2 adapter (ADR-0034)

[dependency-groups]                  # not published: exact versions live in uv.lock
dev = [
  "ruff>=0.16.7", "mypy>=2.3.1",
  "pytest>=9.1.1", "pytest-cov>=7.1.0", "hypothesis>=6.168.0",
  "pytest-benchmark>=5.3.0",
  "mutmut>=3.8.0", "pre-commit>=4.6.2",
  "pip-audit>=2.9", "zizmor>=1.0",
]

[project.urls]                       # Homepage, Documentation, Issues, Security

[project.scripts]                    # M6, with aegis/cli/ — earlier, it would install a broken command
aegis = "aegis.cli.__main__:main"

[tool.hatch.build.targets.wheel]
packages = ["src/aegis"]             # installed as `aegis` (ADR-0025)

[tool.hatch.build.targets.sdist]     # an allowlist: a local build never ships untracked files
only-include = ["src", "tests", "tools", "docs", "LICENSE", "README.md", "SECURITY.md", "pyproject.toml"]

[tool.uv]
required-version = ">=0.12"
```

Tool configuration (`[tool.ruff]`, `[tool.mypy]`, `[tool.pytest]`, `[tool.coverage]`) lives
in the same file: § 6.3.

## 6. Development tooling

### 6.1 `uv`

| Task | Command |
|---|---|
| Create the environment with every extra and the `dev` group | `uv sync --all-extras` |
| Run anything in it | `uv run pytest`, `uv run mypy` |
| Test another Python | `uv sync --all-extras --python 3.13` |
| Test the dependency floors | `uv sync --all-extras --resolution lowest-direct` |
| Update one tool | `uv lock --upgrade-package ruff` |
| Build the wheel and sdist | `uv build` |

**What `uv` changes, and what it does not:**

| Changes | Does not change |
|---|---|
| Contributor setup: one command instead of `venv` + `pip` | How users install Aegis |
| Dev tools: exact versions in `uv.lock` instead of `==` pins | The runtime policy: floors, no ceilings |
| `[dev]` extra → `dev` dependency group | The build backend (Hatchling) |
| CI installs Python with `uv python install` | The publishing path (trusted publishing, attestations) |
| The floor job becomes `--resolution lowest-direct` | The test matrix itself |

**`pip` still works** for contributors who prefer it. pip 25.1+ reads dependency groups:
`pip install -e ".[cli]" --group dev`. Without the lockfile you get the latest
compatible tools instead of the locked ones, so CI remains the reference.

### 6.2 Tools

| Tool | Locked at (2026-10-19) | Used for |
|---|---|---|
| `uv` | 0.13.2 in CI (`setup-uv`); `required-version >= 0.12` | environments, lockfile, Python installs, `uv build` |
| `ruff` | 0.17.1 | lint and format — no style debate ([contributing.md § 5](contributing.md#5-code-style)) |
| `mypy` | 2.4.0 | `--strict` on `src/aegis/` |
| `pytest` | 9.1.1 | the suite |
| `pytest-cov` | 7.1.0 | per-file coverage gates ([tests.md § 8](tests.md#8-coverage)) |
| `hypothesis` | 6.170.4 | round-trip and adversarial properties |
| `pytest-benchmark` | 5.3.0 | the benchmark suite ([performance.md](performance.md)) |
| `mutmut` | 3.8.0 | mutation testing of `stream.py`, `envelope.py`, `format.py`, `context.py` |
| `pre-commit` | 4.7.0 | local hooks: `ruff check`, `ruff format`, `uv lock --check` |
| `pip-audit` | 2.10.1 | known vulnerabilities in the locked dependency tree |
| `zizmor` | 1.31.1 | security lint of `.github/workflows/` (injection, unpinned actions, token scope) |

- **Updates:** Dependabot opens PRs for `uv.lock` and for GitHub Actions.
- `mypy` runs in CI, not in `pre-commit`, to keep commits fast.
- **The `pre-commit` hooks are `repo: local`** and run `uv run ruff …`, so the hook uses the
  `ruff` in `uv.lock`. A `ruff-pre-commit` mirror would carry its own `rev:` and drift from
  what CI runs (§ 1, principle 5).

### 6.3 Tool configuration

Everything lives in `pyproject.toml`; there are no `ruff.toml`, `mypy.ini`, `pytest.ini` or
`.coveragerc` files.

#### `ruff`

`target-version` is not set: `ruff` reads it from `requires-python`, so `UP` rewrites code to
the floor's syntax and moves with it when ADR-0023 is decided. The line length is the default
(88), because the default is the choice nobody argues about.

```toml
[tool.ruff.format]
docstring-code-format = true           # examples in docstrings are formatted too
exclude = ["*.md"]                     # docs' code blocks are aligned by hand, for reading

[tool.ruff.lint]
select = [
  "E", "W", "F",   # pycodestyle, pyflakes
  "I",             # import order
  "UP",            # modern syntax for the requires-python floor
  "B",             # bugbear: likely bugs
  "BLE",           # blind except                      — contributing.md § 3, rule 3
  "S",             # bandit: `random`, `pickle`, `assert`, hardcoded secrets
  "T20",           # no `print` in the library
  "TID",           # banned APIs, below                — contributing.md § 3, rules 6-7
  "D",             # docstrings on the public API      — contributing.md § 5
  "C90",           # complexity ceiling                — "stream.py stays small"
  "N", "C4", "SIM", "PIE", "RET", "PERF", "PT", "PGH", "RUF",
]
ignore = [
  "W191", "D206", "D300",               # conflict with `ruff format`
  "D105", "D107",                       # dunder methods and __init__: the class docstring covers them
]

[tool.ruff.lint.pydocstyle]
convention = "google"                   # `Raises:` names the exception the caller should expect

[tool.ruff.lint.mccabe]
max-complexity = 10

[tool.ruff.lint.flake8-tidy-imports.banned-api]
"os.urandom".msg = "Randomness enters only in vault.py (architecture.md § 4, ADR-0026)."
"os.environ".msg = "The environment is read only in keys.py (architecture.md § 4)."
"os.getenv".msg  = "The environment is read only in keys.py (architecture.md § 4)."
"click".msg      = "`import aegis` must never import click (ADR-0021). Only aegis.cli may."

[tool.ruff.lint.per-file-ignores]
"src/aegis/keys.py"   = ["TID251"]      # the edges: the environment
"src/aegis/vault.py"  = ["TID251"]      # the edges: randomness
"src/aegis/cli/**"    = ["TID251"]
"tests/**"            = ["S101", "D", "TID251"]
"tools/**"            = ["T20"]         # scripts print their verdicts
```

- **Why these rule groups.** Each one either enforces a rule in
  [contributing.md](contributing.md) mechanically (`BLE`, `TID`, `D`, `C90`), catches a class
  of bug a crypto library cannot afford (`B`, `S`, `PGH`: no blanket `# type: ignore` or
  `# noqa`), or keeps the code modern and short (`UP`, `C4`, `SIM`, `RET`, `PERF`).
- **Deliberately not selected.** `ANN` (duplicates `mypy --strict`), `PTH` (would rewrite
  `os.replace` and `os.fsync`, which `unseal_to_path` needs as they are), `ERA` (flags the
  nonce-construction comments in `stream.py` as commented-out code), `PL` and `FBT` (noise
  without a matching project rule), `preview` rules (they change between `ruff` releases).
- **The banned-API list is a fast first line, not the proof.** The `sys.modules` test for
  `click` and the purity tests in [tests.md](tests.md) stay; `ruff` makes the same mistake
  fail in the editor instead of in CI.
- **Suppressions** carry the rule code and a reason: `# noqa: S311 — test-only shuffle`.
  `RUF100` fails on a `noqa` that no longer suppresses anything.

#### `mypy`

```toml
[tool.mypy]
files = ["src/aegis"]
strict = true
warn_unreachable = true
enable_error_code = ["ignore-without-code", "redundant-expr", "truthy-bool", "possibly-undefined"]
```

`truthy-bool` matters here: `if key:` on an object that is always truthy is exactly the kind
of check that silently passes on a missing KEK.

#### `pytest`

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = ["--import-mode=importlib", "--strict-markers", "--strict-config", "-ra"]
xfail_strict = true
filterwarnings = ["error"]              # a deprecation in `cryptography` fails the suite, not a user
markers = ["slow: the 512 MB memory invariants (tests.md)"]
```

#### `coverage`

```toml
[tool.coverage.run]
branch = true
source_pkgs = ["aegis"]                 # the package, wherever it is installed from
relative_files = true                   # data files from every matrix cell combine

[tool.coverage.paths]
source = ["src/aegis", "*/site-packages/aegis", "*\\site-packages\\aegis"]

[tool.coverage.report]
show_missing = true
skip_covered = true
exclude_also = ["if TYPE_CHECKING:", "^\\s*\\.\\.\\.$"]   # Protocol bodies
```

`coverage`'s `fail_under` is one number for the whole report, and `--include` with several
files averages them. The per-file gates of [tests.md § 8](tests.md#8-coverage) are therefore
applied by `tools/coverage_gates.py`: a stdlib-only script that reads `coverage json` and
checks each file against its threshold. CI runs it after the suite.

Coverage is measured on every matrix cell and combined before the gates run, because some
branches exist on one platform only: the `seek` + `write` fallback on Windows, the directory
`fsync` on POSIX. `relative_files` and `[tool.coverage.paths]` are what let the cells' data
files combine.

## 7. CI/CD

GitHub Actions, four workflows. Every job starts with `astral-sh/setup-uv` pinned to the
locked `uv` version, then `uv sync --locked`, which fails if `uv.lock` is stale.

| Workflow | Trigger | Runs |
|---|---|---|
| `ci.yml` | every PR and push to `main` | `ruff check --output-format=github`, `ruff format --check`, `mypy`, `zizmor`, the full suite on the matrix, the floor job (`--resolution lowest-direct`), per-file coverage gates, a guard that fails if `tests/vectors/` changed |
| `nightly.yml` | daily | high-`max_examples` Hypothesis, `mutmut`, `pip-audit` on the locked tree (a vulnerability appears without a code change) |
| `bench.yml` | weekly, release tags, manual | the benchmark suite on the reference runners ([performance.md § 5](performance.md#5-how-it-is-measured)) |
| `release.yml` | `v*` tag | tag check (annotated, signature verified by GitHub, equal to `v` + the `pyproject.toml` version) and `pip-audit` over the whole lock → `uv build`, and a check that the wheel holds only `aegis/` and its metadata → frozen vectors against the built wheel (from M4) → publish through trusted publishing, with attestations, behind the `pypi` environment's reviewer |

- Matrix: [tests.md § 9](tests.md#9-ci).
- Third-party actions are pinned by **commit SHA**, not by tag.
- No long-lived PyPI token exists. Publishing goes through `pypa/gh-action-pypi-publish` over
  OIDC, which also produces the PEP 740 attestations. It is kept rather than `uv publish`
  for that reason.

## 8. Deliberately not in the stack

| Not used | Why |
|---|---|
| `typer` | Three extra runtime packages for five commands (§ 4.1). |
| Poetry, PDM | `uv` covers environments, locking and Python installs on standard PEP 621 / PEP 735 metadata. |
| `uv_build` backend | Hatchling is independent of the workflow tool, so the build does not change if `uv` is ever replaced. |
| `tox` / `nox` | The matrix is a CI concern; `uv sync --python` covers local runs. |
| Rust, C, Cython extensions | Pure-Python promise; the hot path is already native inside OpenSSL. |
| PyNaCl, `pyrage`, Tink | [ADR-0001](decisions.md#adr-0001-build-the-cryptographic-core-on-cryptography-using-stream). |
| `anyio` / asyncio wrappers | [ADR-0007](decisions.md#adr-0007-no-async-api-in-10). |
| `pydantic`, `attrs` | `dataclasses` covers a handful of frozen records. |
| Django, `pytest-django` (in 1.0) | The adapter is V2 ([ADR-0034](decisions.md#adr-0034-the-django-adapter-moves-to-v2)). |
| `rich`, `colorama` | Plain CLI output; nothing to colour. |
| `black`, `isort`, `flake8`, `bandit`, `pyupgrade` | `ruff` implements all five (`ruff format`, `I`, `E`/`F`, `S`, `UP`) in one locked tool. |
| `pyright` | One type checker. Two would disagree on edge cases and double the suppressions. |

## 9. Open items

- **ADR-0021** (`click`), **ADR-0022** (Hatchling) and **ADR-0023** (Python 3.11–3.14):
  accepted on 2026-10-18.
- **Q8** and **Q9** (rotation on Windows, torn writes) are decided by
  [ADR-0035](decisions.md#adr-0035-rotation-write-path-torn-write-journal-public-calls-recursive-runs);
  **Q17** (`.hypothesis/` is ignored) and **Q18** (a `0.0.0` placeholder reserves the name) by
  [ADR-0037](decisions.md#adr-0037-smaller-resolutions). Nothing blocks M0.
- A documentation site (MkDocs, Sphinx) is not chosen. The docs stay Markdown in the
  repository until after 1.0.
