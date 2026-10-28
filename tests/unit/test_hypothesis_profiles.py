"""The Hypothesis profiles of tests/conftest.py: `ci` by default, `nightly` by name."""

import importlib.util
from pathlib import Path

import pytest
from hypothesis import settings
from hypothesis.errors import InvalidArgument

CONFTEST = Path(__file__).resolve().parents[1] / "conftest.py"


@pytest.fixture(scope="module")
def conftest():
    spec = importlib.util.spec_from_file_location("aegis_tests_conftest", CONFTEST)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def restore_profile():
    # Loading a profile is global: put back the one the session runs under.
    name = settings.get_current_profile_name()
    yield
    settings.load_profile(name)


def test_ci_profile():
    p = settings.get_profile("ci")
    assert (p.derandomize, p.deadline, p.max_examples) == (False, None, 100)


def test_nightly_profile():
    p = settings.get_profile("nightly")
    assert (p.derandomize, p.deadline, p.max_examples) == (False, None, 10_000)


def test_ci_is_the_default(conftest, restore_profile):
    conftest.load_hypothesis_profile({})
    assert settings.get_current_profile_name() == "ci"


def test_named_profile_is_loaded(conftest, restore_profile):
    conftest.load_hypothesis_profile({"HYPOTHESIS_PROFILE": "nightly"})
    assert settings.get_current_profile_name() == "nightly"


def test_unknown_profile_raises(conftest, restore_profile):
    with pytest.raises(InvalidArgument):
        conftest.load_hypothesis_profile({"HYPOTHESIS_PROFILE": "nightyl"})
