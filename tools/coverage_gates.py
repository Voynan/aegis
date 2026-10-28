"""Per-file coverage gates: docs/tests.md § 8, applied to a `coverage json` report.

`coverage` fails on one number for the whole report, which lets a risky module hide
behind the others. This script checks each file of `src/aegis/` on its own:

- `stream.py`, `envelope.py`, `format.py`: no missing line and no missing branch;
- `context.py`, `keys.py`, `readers.py`, `rotate.py`: at least 95 % of lines;
- every other file: at least 90 % of lines.

A file on disk that the report does not measure fails, and so does a report that is
missing, is not JSON, or measured nothing.

Usage: `uv run python tools/coverage_gates.py [coverage.json]`.
"""

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = "src/aegis"

FULL = frozenset(
    {"src/aegis/stream.py", "src/aegis/envelope.py", "src/aegis/format.py"}
)
LINES_95 = frozenset(
    {
        "src/aegis/context.py",
        "src/aegis/keys.py",
        "src/aegis/readers.py",
        "src/aegis/rotate.py",
    }
)
LINES_DEFAULT = 90.0


def main(argv: Sequence[str] | None = None, *, root: Path = ROOT) -> int:
    """Check the report; return 0 when every file meets its threshold, 1 otherwise.

    Args:
        argv: at most one path, the `coverage json` report; `coverage.json` by default.
        root: the repository whose `src/aegis/` is checked.

    Returns:
        The exit code.
    """
    report_path = Path(argv[0]) if argv else Path("coverage.json")
    measured = load_report(report_path)
    if measured is None:
        return 1
    on_disk = {p.relative_to(root).as_posix() for p in (root / PACKAGE).rglob("*.py")}
    results = [
        check(path, measured.get(path)) for path in sorted(on_disk | set(measured))
    ]
    for ok, line in results:
        print(f"{'ok  ' if ok else 'FAIL'} {line}")
    return 0 if all(ok for ok, _ in results) else 1


def load_report(path: Path) -> dict[str, Mapping[str, Any]] | None:
    """Return the summaries of the files under `src/aegis/`, or None, saying why."""
    try:
        files = json.loads(path.read_text(encoding="utf-8"))["files"]
    except FileNotFoundError:
        reason = "not found"
    except (ValueError, KeyError, TypeError):
        reason = "not a coverage json report"
    else:
        measured = {
            name: entry["summary"]
            for name, entry in files.items()
            if name.startswith(f"{PACKAGE}/")
        }
        if measured:
            return measured
        reason = f"measured no file under {PACKAGE}/"
    print(f"FAIL {path}  {reason}")
    return None


def check(path: str, summary: Mapping[str, Any] | None) -> tuple[bool, str]:
    """Apply the threshold of `path` to its summary; return the verdict and a line."""
    if summary is None:
        return False, f"{path}  not in the report"
    if path in FULL:
        return check_full(path, summary)
    required = 95.0 if path in LINES_95 else LINES_DEFAULT
    statements = summary["num_statements"]
    percent = 100.0 if statements == 0 else summary["covered_lines"] * 100 / statements
    return percent >= required, f"{path}  {percent:.1f}% lines  (needs {required:.0f}%)"


def check_full(path: str, summary: Mapping[str, Any]) -> tuple[bool, str]:
    """No missing line and no missing branch; a report without branch data fails."""
    if "missing_branches" not in summary:
        return False, f"{path}  no branch data  (needs 100% branch: --cov-branch)"
    lines, branches = summary["missing_lines"], summary["missing_branches"]
    line = f"{path}  {lines} missing lines, {branches} missing branches  (needs none)"
    return lines == 0 and branches == 0, line


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
