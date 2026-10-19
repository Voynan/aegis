# Test-driven development is mandatory

Applies to **every change that creates or alters code** in this repository — `src/`, `tests/`,
`tools/`, `benchmarks/`, the CLI — including one-line fixes. A deadline shrinks the scope, never
the process. Documentation, `.github/` workflows, `pyproject.toml` metadata and `.claude/`
configuration are exempt; any code they call is not.

## The cycle

Run `superpowers:test-driven-development` on every task:

1. **Red.** Write the test first and run it. It must fail, and for the reason you expect: a
   failing assertion, or the specific exception the test names. An import error, a typo or a
   collection error is not a red — stub what the test needs until the failure is the assertion.
   A test that passes on the first run is wrong, or the behaviour already exists.
2. **Green.** Write the minimal production code that makes it pass, and nothing the test does not
   require.
3. **Refactor.** Clean up with the suite green, then run it again.

No production code without a test that failed first. A test written for behaviour that already
exists gets a sensitivity check: break the code on purpose, watch the test fail, restore it.

## What the tests must look like here

[docs/tests.md](../../docs/tests.md) is the strategy; the cycle fills it in and never replaces it.

- Assert the specific exception class — never `AegisError` alone, and never a message string.
- A change to `stream.py`, `envelope.py`, `format.py` or `context.py` adds a property or a
  negative vector, not only an example.
- `tests/vectors/*.json` is read-only. If a change makes a vector fail, the code is wrong.
- The per-file coverage gates and the constant-memory invariants keep holding.

## Evidence

- Keep the output of the failing run and of the passing run: a pull request quotes both
  ([docs/contributing.md § 4](../../docs/contributing.md#4-tests-a-pr-must-carry)).
- Before calling a task done, run `superpowers:verification-before-completion` and show, in the
  same message, the output of `uv run pytest`, `uv run ruff check .`, `uv run mypy` and
  `uv run python tools/coverage_gates.py`.
