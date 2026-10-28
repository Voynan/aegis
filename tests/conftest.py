"""Shared test configuration: the Hypothesis profiles `ci` and `nightly`."""

import os
from collections.abc import Mapping

from hypothesis import settings

# Not derandomized: every run explores new inputs (tests.md § 4.2). No deadline: shared
# runners are too noisy for a per-example time limit.
settings.register_profile("ci", derandomize=False, deadline=None)
settings.register_profile(
    "nightly", parent=settings.get_profile("ci"), max_examples=10_000
)


def load_hypothesis_profile(environ: Mapping[str, str]) -> None:
    # An unknown name raises InvalidArgument, so a typo cannot silently run the default.
    settings.load_profile(environ.get("HYPOTHESIS_PROFILE", "ci"))


load_hypothesis_profile(os.environ)
