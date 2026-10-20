"""The package itself: its version and what `import aegis` costs."""

import subprocess
import sys
from importlib import metadata, resources

import pytest

import aegis


def test_version_matches_the_installed_distribution():
    assert getattr(aegis, "__version__", None) == metadata.version("aegis-voynan")


def test_import_does_not_load_importlib_metadata():
    # A fresh interpreter, so the modules this test process already holds do not count.
    code = (
        "import sys; before = set(sys.modules); import aegis; "
        "print('importlib.metadata' in set(sys.modules) - before)"
    )
    out = subprocess.run(  # noqa: S603 — fixed argv: this interpreter and a literal
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "False"


def test_unknown_attribute_raises_attribute_error():
    with pytest.raises(AttributeError):
        aegis.does_not_exist  # noqa: B018 — the access is the test


def test_package_ships_py_typed():
    assert resources.files("aegis").joinpath("py.typed").is_file()


def test_type_checkers_reject_unknown_attributes(tmp_path):
    # The lazy __getattr__ must not make every name type-check as `str` for users.
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import aegis\nversion: str = aegis.__version__\naegis.does_not_exist\n"
    )
    cache = f"--cache-dir={tmp_path / 'cache'}"
    out = subprocess.run(  # noqa: S603 — fixed argv: this interpreter, mypy, a temp file
        [sys.executable, "-m", "mypy", "--strict", cache, str(probe)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert "probe.py:3: error" in out.stdout
    assert "[attr-defined]" in out.stdout
    assert "probe.py:2:" not in out.stdout
