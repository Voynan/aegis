"""tools/coverage_gates.py: the thresholds of tests.md § 8 on synthetic reports."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "coverage_gates.py"


@pytest.fixture(scope="module")
def gates():
    spec = importlib.util.spec_from_file_location("coverage_gates", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses looks its module up here
    spec.loader.exec_module(module)
    yield module
    del sys.modules[spec.name]


def lines(statements, covered, *, branches=None, missing_branches=0):
    """A coverage-json `summary`; branches=None omits branch data (no --cov-branch)."""
    summary = {
        "num_statements": statements,
        "covered_lines": covered,
        "missing_lines": statements - covered,
    }
    if branches is not None:
        summary |= {
            "num_branches": branches,
            "covered_branches": branches - missing_branches,
            "missing_branches": missing_branches,
        }
    return summary


def run(gates, tmp_path, capsys, *, on_disk, report):
    """Lay out root/src/aegis/<on_disk>, write `report` as coverage.json, run main()."""
    package = tmp_path / "root" / "src" / "aegis"
    package.mkdir(parents=True)
    for name in on_disk:
        (package / name).parent.mkdir(parents=True, exist_ok=True)
        (package / name).write_text("")
    path = tmp_path / "coverage.json"
    if report is not None:
        path.write_text(report if isinstance(report, str) else json.dumps(report))
    code = gates.main([str(path)], root=tmp_path / "root")
    failures = [
        line for line in capsys.readouterr().out.splitlines() if line.startswith("FAIL")
    ]
    return code, failures


def files(**summaries):
    """A coverage-json report whose keys are src/aegis/<name>.py."""
    return {
        "files": {
            f"src/aegis/{name}.py": {"summary": s} for name, s in summaries.items()
        }
    }


CASES = [
    # id, on disk, report, exit, the path a FAIL line must name
    pytest.param(
        ["stream.py"],
        files(stream=lines(10, 10, branches=4, missing_branches=1)),
        1,
        "src/aegis/stream.py",
        id="full-missing-branch",
    ),
    pytest.param(
        ["format.py"],
        files(format=lines(10, 9, branches=4)),
        1,
        "src/aegis/format.py",
        id="full-missing-line",
    ),
    pytest.param(
        ["envelope.py"],
        files(envelope=lines(10, 10)),
        1,
        "src/aegis/envelope.py",
        id="full-without-branch-data",
    ),
    pytest.param(
        ["stream.py"], files(stream=lines(10, 10, branches=4)), 0, None, id="full-ok"
    ),
    pytest.param(
        ["context.py"],
        files(context=lines(20, 18)),
        1,
        "src/aegis/context.py",
        id="95-below",
    ),
    pytest.param(["keys.py"], files(keys=lines(20, 19)), 0, None, id="95-boundary"),
    pytest.param(
        ["info.py"], files(info=lines(10, 8)), 1, "src/aegis/info.py", id="90-below"
    ),
    pytest.param(["vault.py"], files(vault=lines(10, 9)), 0, None, id="90-boundary"),
    pytest.param(
        ["cli/__main__.py"],
        {"files": {"src/aegis/cli/__main__.py": {"summary": lines(10, 8)}}},
        1,
        "src/aegis/cli/__main__.py",
        id="90-subpackage",
    ),
    pytest.param(
        ["__init__.py"],
        {"files": {"src/aegis/__init__.py": {"summary": lines(0, 0)}}},
        0,
        None,
        id="no-statements",
    ),
    pytest.param(
        ["__init__.py", "readers.py"],
        {"files": {"src/aegis/__init__.py": {"summary": lines(1, 1)}}},
        1,
        "src/aegis/readers.py",
        id="absent-from-report",
    ),
]


@pytest.mark.parametrize(("on_disk", "report", "exit_code", "failing"), CASES)
def test_rule(gates, tmp_path, capsys, on_disk, report, exit_code, failing):
    code, failures = run(gates, tmp_path, capsys, on_disk=on_disk, report=report)
    assert code == exit_code
    if failing is None:
        assert failures == []
    else:
        assert any(failing in line for line in failures), failures


def test_missing_report_fails(gates, tmp_path, capsys):
    code, failures = run(gates, tmp_path, capsys, on_disk=[], report=None)
    assert code == 1
    assert any("coverage.json" in line for line in failures), failures


def test_invalid_json_fails(gates, tmp_path, capsys):
    code, failures = run(gates, tmp_path, capsys, on_disk=[], report="{not json")
    assert code == 1
    assert any("coverage.json" in line for line in failures), failures


def test_report_without_aegis_files_fails(gates, tmp_path, capsys):
    code, failures = run(gates, tmp_path, capsys, on_disk=[], report={"files": {}})
    assert code == 1
    assert any("coverage.json" in line for line in failures), failures
