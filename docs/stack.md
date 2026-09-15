# Stack

Every dependency and tool, the version policy for each, and why it was chosen over the
alternatives. Versions named here are the floor or the pin **as of 2026-09-14**.

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
| Language | CPython | 3.10+ per current docs; **see § 3.1 (proposed change)** |
| Cryptography | `cryptography` | `>=44.0`, no ceiling |
| Build backend | Hatchling | pinned in `[build-system]` ([ADR-0022](decisions.md#adr-0022-hatchling-as-the-build-backend), proposed) |
| Project and environment tool | `uv` | `required-version`, pinned in CI ([ADR-0024](decisions.md#adr-0024-uv-for-development-and-ci)) |
| Distribution | PyPI `aegis-voynan`, pure-Python wheel + sdist | [ADR-0018](decisions.md#adr-0018-distribute-as-aegis-voynan-import-as-aegis) |
| CLI extra | `click` | `>=8.1` ([ADR-0021](decisions.md#adr-0021-the-cli-is-built-on-click), proposed) |
| Django extra | Django | `>=5.2` (current LTS) |
| Lint + format | `ruff` | locked in `uv.lock` |
| Types | `mypy --strict` | locked |
| Tests | `pytest`, `pytest-cov`, `hypothesis`, `pytest-django` | locked |
| Mutation testing | `mutmut` | locked |
| Benchmarks | `pytest-benchmark` | locked |
| Git hooks | `pre-commit` | locked |
| CI/CD | GitHub Actions, PyPI trusted publishing (OIDC) | actions pinned by commit SHA |
| Repository | [github.com/voynan/aegis](https://github.com/voynan/aegis) | — |

## 3. Runtime

### 3.1 Python

The documents currently say **3.10+ at 1.0, SPEC 0 style**, with a CI matrix of 3.10–3.13.
That no longer matches the calendar:

| Version | Released | End of life |
|---|---|---|
| 3.10 | 2021-10 | **2026-10-31** — six weeks from now |
| 3.11 | 2022-10 | 2027-10-31 |
| 3.12 | 2023-10 | 2028-10-31 |
| 3.13 | 2024-10 | 2029-10-31 |
| 3.14 | 2025-10 | 2030-10-31 — current, missing from the CI matrix |

- A 3.10 floor means shipping a security library whose minimum interpreter no longer gets
  security fixes on release day.
- Strict SPEC 0 (support versions released in the last three years) would put the floor at
  3.13 by 1.0, excluding Debian 12 (3.11) and many Django 5.2 LTS deployments.

**Proposal ([ADR-0023](decisions.md#adr-0023-python-floor-follows-cpythons-support-window),
proposed):** the floor is the oldest CPython still receiving security fixes when a release
ships — **3.11** for a 1.0 before 2027-10-31 — and the CI matrix is 3.11–3.14. Until it is
accepted, [product.md](product.md), [architecture.md](architecture.md) and
[tests.md](tests.md) keep 3.10–3.13.

CI installs interpreters with `uv python install`, so the matrix does not depend on what a
runner image ships. Free-threaded builds (`3.13t`, `3.14t`) are not in the 1.0 matrix.

### 3.2 `cryptography`

Used for exactly two primitives, and nothing else:

| Import | For |
|---|---|
| `cryptography.hazmat.primitives.ciphers.aead.AESGCM` | chunk encryption, DEK wrap |
| `cryptography.hazmat.primitives.kdf.hkdf.HKDF` | wrapping-key derivation |

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
| `hashlib` | SHA-256 for `kek_id` and the AAD hashes |
| `os` | `urandom` (DEK, salt, `nonce_prefix`), `replace` and `fsync` (`unseal_to_path`) |
| `base64` | strict KEK decoding (`b64decode(..., validate=True)`, [ADR-0015](decisions.md#adr-0015-keks-in-environment-variables-are-base64)) |
| `io`, `tempfile` | stream handling; the temporary file of `unseal_to_path`, in the destination directory |
| `dataclasses` | frozen `Header`, `CustodyBlock`, `Receipt` |
| `typing` | `Protocol` for `KeySource` |
| `logging` | the `aegis` logger with a `NullHandler` |
| `importlib.metadata` | `aegis.__version__`, resolved lazily so it costs nothing at import |

**Platform note.** `os.pwrite` does not exist on Windows, but the rotation design assumes it.
See [architecture.md § 16, Q8](architecture.md#16-open-questions).

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

### 4.2 `[django]` — Django

- **Floor `>=5.2`**, the current LTS (end of life 2028-04). 4.2 LTS already reached end of
  life in 2026-04.
- **Tested against** 5.2 LTS on the lowest supported Python and the latest release (6.1
  today) on the newest. Django 6.x requires Python 3.12+.
- Integration tests use `pytest-django`.

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
  run the frozen vectors.
- **`uv.lock` is committed.** It governs development and CI only; it is not published and
  does not constrain users.

```toml
[build-system]
requires = ["hatchling==1.32.0"]
build-backend = "hatchling.build"

[project]
name = "aegis-voynan"
version = "0.0.0"
requires-python = ">=3.10"          # 3.11 if ADR-0023 is accepted
license = "MIT"
dependencies = ["cryptography>=44.0"]

[project.optional-dependencies]      # published: what users can ask for
cli    = ["click>=8.1"]
django = ["django>=5.2"]

[dependency-groups]                  # not published: exact versions live in uv.lock
dev = [
  "ruff>=0.16.7", "mypy>=2.3.1",
  "pytest>=9.1.1", "pytest-cov>=7.1.0", "hypothesis>=6.168.0",
  "pytest-django>=4.14.0", "pytest-benchmark>=5.3.0",
  "mutmut>=3.8.0", "pre-commit>=4.6.2",
]

[project.scripts]
aegis = "aegis.cli.__main__:main"

[tool.hatch.build.targets.wheel]
packages = ["aegis"]

[tool.uv]
required-version = ">=0.12"
```

## 6. Development tooling

### 6.1 `uv`

| Task | Command |
|---|---|
| Create the environment with every extra and the `dev` group | `uv sync --all-extras` |
| Run anything in it | `uv run pytest`, `uv run mypy --strict aegis` |
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
`pip install -e ".[cli,django]" --group dev`. Without the lockfile you get the latest
compatible tools instead of the locked ones, so CI remains the reference.

### 6.2 Tools

| Tool | Locked at (2026-09-14) | Used for |
|---|---|---|
| `uv` | 0.12.13 | environments, lockfile, Python installs, `uv build` |
| `ruff` | 0.16.7 | lint and format — no style debate ([contributing.md § 5](contributing.md#5-code-style)) |
| `mypy` | 2.3.1 | `--strict` on `aegis/` |
| `pytest` | 9.1.1 | the suite |
| `pytest-cov` | 7.1.0 | per-file coverage gates ([tests.md § 8](tests.md#8-coverage)) |
| `hypothesis` | 6.168.0 | round-trip and adversarial properties |
| `pytest-django` | 4.14.0 | adapter integration tests |
| `pytest-benchmark` | 5.3.0 | the benchmark suite ([performance.md](performance.md)) |
| `mutmut` | 3.8.0 | mutation testing of `stream.py`, `format.py`, `context.py` |
| `pre-commit` | 4.6.2 | local hooks: `ruff check`, `ruff format`, `uv lock --check` |

- **Updates:** Dependabot opens PRs for `uv.lock` and for GitHub Actions.
- `mypy` runs in CI, not in `pre-commit`, to keep commits fast.

## 7. CI/CD

GitHub Actions, four workflows. Every job starts with `astral-sh/setup-uv` pinned to the
locked `uv` version, then `uv sync --locked`, which fails if `uv.lock` is stale.

| Workflow | Trigger | Runs |
|---|---|---|
| `ci.yml` | every PR and push to `main` | `ruff`, `mypy --strict`, the full suite on the matrix, the floor job (`--resolution lowest-direct`), per-file coverage gates, a guard that fails if `tests/vectors/` changed |
| `nightly.yml` | daily | high-`max_examples` Hypothesis, `mutmut` |
| `bench.yml` | weekly, release tags, manual | the benchmark suite on the reference runners ([performance.md § 5](performance.md#5-how-it-is-measured)) |
| `release.yml` | signed tag | `uv build` → provenance attestations → publish through trusted publishing |

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
| `pydantic`, `attrs` | `dataclasses` covers four frozen records. |
| `rich`, `colorama` | Plain CLI output; nothing to colour. |

## 9. Open items

- **ADR-0021** (`click`) and **ADR-0022** (Hatchling): proposed.
- **ADR-0023** (Python floor 3.11, matrix 3.11–3.14): proposed. Accepting it updates
  product.md § 6, architecture.md § 14 and tests.md § 9.
- **Q8** (rotation on Windows) and **Q9** (torn writes during rotation):
  [architecture.md § 16](architecture.md#16-open-questions).
- **Q17** (Hypothesis database — decides an `.gitignore` entry) and **Q18** (PyPI name
  reservation) block M0: [architecture.md § 16](architecture.md#16-open-questions).
- A documentation site (MkDocs, Sphinx) is not chosen. The docs stay Markdown in the
  repository until after 1.0.
