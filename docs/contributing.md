# Contributing

Aegis is a cryptography library, so the bar is different from an ordinary Python package:
a merged mistake is not a bug report, it is a CVE. The rules below exist to make that bar
explicit rather than intimidating.

Everything here applies to maintainers too.

---

## 1. Setup

```bash
git clone https://github.com/<org>/aegis && cd aegis
python -m venv .venv && source .venv/bin/activate     # 3.10+
pip install -e ".[dev,cli,django]"
pre-commit install

pytest                       # the full suite
pytest -m "not slow"         # skip the 512 MB memory invariants
ruff check . && ruff format --check .
mypy --strict aegis
pytest --cov=aegis --cov-branch --cov-report=term-missing
```

CI runs exactly these. If they pass locally on Linux and fail in CI, it is almost always
Windows: `os.replace`, `fsync` on a directory, or a file opened in text mode.

## 2. Before you open a pull request

- **Discuss format-touching changes first.** Anything that changes a byte on disk is a new
  format version, not a patch. Open an issue and expect it to become an
  [ADR](decisions.md).
- **One concern per PR.** A refactor and a behaviour change in the same diff cannot be
  reviewed for security.
- **No new dependency in the core.** The core has exactly one: `cryptography`. A PR adding
  a second needs to justify it as an ADR.

## 3. The rules that are not negotiable

1. **Do not invent cryptography.** Every primitive comes from `cryptography`. Every
   construction is published and cited. If a change requires a novel argument for why it is
   secure, it does not belong here.
2. **`tests/vectors/*.json` is read-only.** If your change makes a vector fail, your change
   is wrong. There is no `--update-vectors` flag and there will not be one
   ([file-format.md § 8](file-format.md#8-changing-this-format)).
3. **No blanket `except Exception`.** Catch what you can name.
4. **No secret in any string.** Not in a `repr`, a log record, an exception message, or a
   test failure message. There is a test for this; do not weaken it.
5. **`stream.py` stays small.** If your change makes it grow noticeably, something else
   must move out. It is the module a reviewer must be able to audit in one sitting.
6. **Randomness stays at the edges.** `format.py`, `context.py` and `stream.py` never call
   `os.urandom` and never touch the environment
   ([architecture.md § 4](architecture.md#4-the-purity-boundary-randomness-lives-at-the-edges)).
7. **The adapters import only the public API.** If `aegis.contrib.django` or `aegis.cli`
   needs a private name, the public API is incomplete — fix that instead.

## 4. Tests a PR must carry

- A test that fails before your change and passes after it. Paste both outputs in the PR
  description.
- For anything touching `stream.py`, `format.py` or `context.py`: a **property** or a
  **negative vector**, not only an example. Examples cover the case you thought of;
  properties cover the ones you did not.
- Coverage gates still met **per file**: 100 % branch on `stream.py` and `format.py`, 95 %
  on `context.py` / `keys.py` / `rotate.py`, 90 % elsewhere.
- Assert the specific exception class. `pytest.raises(AegisError)` is not a test.
- Never assert on a message string; errors carry structured attributes for that.

Full strategy: [tests.md](tests.md).

## 5. Code style

- `ruff` decides formatting and lint. There is no style debate.
- `mypy --strict` on `aegis/`. Public API fully annotated; `Protocol` for extension points.
- Names come from the domain: `seal`/`unseal`, `dek`, `kek`, `wrapped_dek`, `nonce_prefix`,
  `context`. Do not introduce a synonym for a term that already exists in
  [file-format.md](file-format.md).
- Comments explain **why**, not what. In `stream.py`, a comment explaining why a nonce is
  safe is worth more than the line it sits above.
- Docstrings on everything public, with the exception the caller should expect.

## 6. Documentation is part of the change

If your PR changes behaviour, it changes documentation in the same PR:

| You changed | Update |
|---|---|
| Anything on disk | [file-format.md](file-format.md) — and it needs a version byte |
| The public API | [usage.md](usage.md), the README, docstrings |
| Module boundaries | [architecture.md](architecture.md) |
| A security property, or an assumption | [security.md](security.md) |
| A load-bearing choice | a new ADR in [decisions.md](decisions.md) |

## 7. Reviewing

A reviewer of a crypto-touching PR is expected to answer, in writing:

1. Can a nonce repeat under any interleaving of these changes?
2. Is every byte written to disk either authenticated, or pinned to a constant?
3. What does this do on a truncated, reordered or transplanted input?
4. Can key material reach a string?
5. Is the failure path as well tested as the success path?

Anything touching `stream.py`, `format.py`, `keys.py` or the format needs **two**
approvals, one of which must be a maintainer. Everything else needs one.

## 8. Commits and PRs

- [Conventional Commits](https://www.conventionalcommits.org): `feat:`, `fix:`, `docs:`,
  `test:`, `refactor:`, `chore:`. A `!` or a `BREAKING CHANGE:` footer for anything that
  breaks the public API.
- Imperative subject, ≤ 72 characters. The body explains **why**.
- Reference the issue or ADR the change comes from.
- Rebase on `main`; keep history linear.

## 9. Releasing

1. Every gate green on every matrix cell, including the slow invariants.
2. Frozen vectors pass **against the built wheel**, not only the source tree.
3. CHANGELOG updated; version bumped per SemVer.
4. Signed tag; CI publishes via PyPI trusted publishing (OIDC). No human holds a token.
5. Verify `pip install aegis==<version>` on a clean machine and re-run the vectors.

Pre-1.0, M8's public review of `stream.py` is a release blocker
([roadmap.md](roadmap.md)).

## 10. Security issues

**Do not open a public issue.** Use GitHub's private advisory flow — see
[security.md § 8](security.md#8-reporting-a-vulnerability). Acknowledgement within 72 hours,
assessment within 7 days, coordinated disclosure within 90.

## 11. Conduct and licensing

Be direct about code and generous about people. Technical disagreement is expected; it gets
resolved with an argument or an ADR, not by seniority.

By contributing you agree that your contribution is licensed under the MIT license
([`LICENSE`](../LICENSE), [ADR-0009](decisions.md#adr-0009-mit-license)).
