# Repository structure

Where every file and directory lives, which document owns it, and where a new one goes.
This is the only complete tree of the repository. Other documents describe what happens
*inside* a directory; when they draw a tree, it must match this one.

---

## 1. Principles

1. **The library lives in `src/aegis/`, and the wheel is that directory and nothing else.**
   Under `src/`, the package is importable only once installed, so every test runs against
   the installed package ([ADR-0025](decisions.md#adr-0025-the-package-lives-in-src)). Tests,
   benchmarks, tools and documentation never reach a user's `site-packages`
   ([stack.md § 5](stack.md#5-packaging)).
2. **The package is flat.** Ten single-responsibility modules at one level
   ([architecture.md § 2](architecture.md#2-module-map)). The only sub-package in 1.0 is the
   CLI, behind its extra; the Django adapter joins it in V2
   ([dev/v2-django.md](dev/v2-django.md)).
3. **Tests are grouped by layer, not by module.** Each layer answers one question and has
   its own gate ([tests.md § 2](tests.md#2-the-layers)), so `pytest tests/adversarial` runs
   one whole argument for trusting the code.
4. **One configuration file.** Tool settings are `[tool.*]` tables in `pyproject.toml`
   ([stack.md § 6.3](stack.md#63-tool-configuration)). A separate file exists only where the
   tool cannot read `pyproject.toml`.
5. **Every directory has one owning document.** A change to what a directory contains
   updates that document in the same PR ([contributing.md § 6](contributing.md#6-documentation-is-part-of-the-change)).

## 2. The tree

Paths marked *(M*n*)* are created at that milestone ([roadmap.md](roadmap.md)). Nothing
else exists before it is needed.

```
.
├── src/
│   └── aegis/                     # the library; the only directory in the wheel (M0)
│       ├── __init__.py            # the public API; lazy __version__
│       ├── py.typed
│       ├── errors.py              # M1
│       ├── format.py              # M1
│       ├── context.py             # M1
│       ├── envelope.py            # M2
│       ├── stream.py              # M2
│       ├── keys.py                # M3
│       ├── readers.py             # M3
│       ├── info.py                # M3
│       ├── vault.py               # M3
│       ├── rotate.py              # M5
│       └── cli/                   # extra [cli] (M6)
│           ├── __init__.py
│           └── __main__.py        # the `aegis` entry point and `python -m aegis.cli`
├── tests/
│   ├── conftest.py                # shared fixtures; Hypothesis profiles `ci` and `nightly`
│   ├── vectors/
│   │   ├── v1.json                # FROZEN at M4; read-only forever
│   │   └── generate.py            # run by hand once, at M4; never run by CI
│   ├── unit/
│   ├── property/
│   ├── adversarial/
│   ├── invariants/                # memory ceiling, rotation body identity, dogfood imports
│   └── integration/               # the CLI
├── benchmarks/                    # pytest-benchmark suite; never a PR gate
├── tools/
│   └── coverage_gates.py          # per-file coverage thresholds (M0)
├── docs/
│   ├── README.md                  # reading order and open questions
│   ├── *.md                       # one document per question
│   ├── initial-spec.md            # historical record; never updated
│   └── dev/                       # plans and working notes; not normative
│       ├── v1-todo.md             # the working checklist for 1.0
│       ├── v2-django.md           # the plan for the Django adapter, after 1.0
│       ├── superpowers/           # milestone specs and plans (from M0); git-ignored
│       │   ├── specs/             # one approved spec per milestone
│       │   └── plans/             # one or more approved plans per milestone
│       ├── notes.md               # personal notes; git-ignored
│       └── diary/                 # personal diary, one file per day; git-ignored
├── .github/
│   ├── workflows/                 # ci.yml, nightly.yml, bench.yml, release.yml (M0)
│   ├── dependabot.yml             # uv and github-actions (M0)
│   └── CODEOWNERS                 # the crypto paths of contributing.md § 7 (M0)
├── .claude/
│   ├── settings.json              # requires the superpowers plugin
│   ├── rules/                     # always-loaded rules: test-first, spec and plan per milestone
│   └── skills/                    # project skills: git-commit, diary
├── pyproject.toml                 # metadata, extras, dev group, tool configuration (M0)
├── uv.lock                        # committed; development and CI only (M0)
├── .pre-commit-config.yaml        # M0
├── .gitignore                     # § 5
├── README.md                      # threat-model paragraph first
├── SECURITY.md                    # points at security.md § 8 (M0)
├── CHANGELOG.md                   # starts at 1.0.0 (M9)
└── LICENSE                        # MIT
```

## 3. Owners

| Path | Owning document | In the wheel |
|---|---|---|
| `src/aegis/` | [architecture.md § 2](architecture.md#2-module-map) | yes |
| `src/aegis/cli/` | [architecture.md § 12](architecture.md#12-the-cli) | yes, needs `[cli]` to import |
| `src/aegis/contrib/django/` (V2) | [dev/v2-django.md](dev/v2-django.md) | not in 1.0 |
| `tests/` | [tests.md](tests.md) | no |
| `tests/vectors/` | [file-format.md § 8](file-format.md#8-changing-this-format), [tests.md § 3](tests.md#3-layer-1--frozen-vectors-kat) | no; in the sdist |
| `benchmarks/` | [performance.md § 5](performance.md#5-how-it-is-measured) | no |
| `tools/`, `.github/`, `pyproject.toml`, `uv.lock`, `.pre-commit-config.yaml` | [stack.md](stack.md) | no |
| `docs/` | [docs/README.md](README.md) | no |
| `docs/dev/` — the plans | [docs/README.md](README.md#plans) | no |
| `.claude/` | [contributing.md § 2](contributing.md#2-before-you-open-a-pull-request), the rules themselves | no |
| `SECURITY.md` | [security.md § 8](security.md#8-reporting-a-vulnerability) | no |
| `CHANGELOG.md` | [contributing.md § 9](contributing.md#9-releasing) | no |

The wheel is built from `packages = ["src/aegis"]` and installs as `aegis`. The sdist is the
tracked tree, which is how `tests/vectors/` reaches downstream packagers
([stack.md § 5](stack.md#5-packaging)).

## 4. Where a new file goes

| You are adding | It goes in | Also update |
|---|---|---|
| A library module | `src/aegis/`, at the top level | architecture.md § 2 — the module map and its layer |
| Code only an extra needs | `src/aegis/cli/`, or `src/aegis/contrib/<framework>/` from V2 | stack.md § 4 |
| A test | `tests/<layer>/test_<subject>.py` | tests.md, if it is a new kind of test |
| A frozen vector | nowhere after M4: a new vector is a new format version | file-format.md § 8 |
| A benchmark | `benchmarks/bench_<subject>.py` | performance.md § 5, with its objective |
| A script CI or a contributor runs | `tools/`, standard library only, run with `uv run python tools/…` | stack.md § 7 |
| A workflow | `.github/workflows/`, actions pinned by commit SHA | stack.md § 7 |
| Settings for a tool | a `[tool.*]` table in `pyproject.toml` | stack.md § 6.3 |
| A design document | `docs/<topic>.md` | the reading order in docs/README.md |
| A decision | a new ADR in `docs/decisions.md`, never a new file | the ADR table |
| A plan or a checklist | `docs/dev/<name>.md` — committed, not normative | the plans table in docs/README.md |
| A milestone spec | `docs/dev/superpowers/specs/YYYY-MM-DD-mN-<topic>-design.md` — git-ignored | the milestone in docs/dev/v1-todo.md |
| A milestone plan | `docs/dev/superpowers/plans/YYYY-MM-DD-mN-<k>-<topic>.md` — git-ignored | the milestone in docs/dev/v1-todo.md |
| A rule for every session | `.claude/rules/<topic>.md` | contributing.md, if people follow it too |
| Personal notes | `docs/dev/notes.md`, or `docs/dev/diary/DD-MM-YYYY.md` through the `diary` skill — git-ignored | — |

- **`src/aegis/` imports nothing from outside itself.** `tests/`, `benchmarks/` and `tools/`
  import the library, never the reverse.
- **A new top-level directory, or a new sub-package in `src/aegis/`,** changes this document and
  needs a reason in the PR description; one that changes the layering needs an ADR.
- **Naming files in prose.** Documents name library files relative to the package —
  `aegis/stream.py`, or just `stream.py`. Anything a tool reads as a path (`pyproject.toml`,
  `CODEOWNERS`, a test that walks the tree) uses the full `src/aegis/…`.

## 5. Never committed

Generated locally or in CI, and listed in `.gitignore`:

| Path | Produced by |
|---|---|
| `.venv/` | `uv sync` |
| `__pycache__/`, `*.py[cod]` | CPython |
| `build/`, `dist/`, `*.egg-info/` | `uv build` |
| `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/` | the tools |
| `.coverage`, `.coverage.*`, `coverage.json`, `htmlcov/` | `coverage`, `tools/coverage_gates.py` |
| `.benchmarks/` | `pytest-benchmark` |
| `mutants/` | `mutmut` |
| `.hypothesis/` | Hypothesis — failures are pinned as `@example(...)` instead ([ADR-0037](decisions.md#adr-0037-smaller-resolutions), Q17) |
| `docs/dev/notes.md`, `docs/dev/diary/` | personal notes — `v1-todo.md` and `v2-django.md` beside them are committed |
| `docs/dev/superpowers/` | the milestone specs and plans, written with superpowers ([ADR-0039](decisions.md#adr-0039-milestone-specs-and-plans-are-local-working-files)) |

The committed `.gitignore` is still a Ruby template, with the two `docs/dev/` entries at its
top. Replacing the template with this list is an M0 task
([roadmap.md § M0](roadmap.md#m0--repository-scaffolding)).
