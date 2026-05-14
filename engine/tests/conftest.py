"""Pytest collection root for the engine test suite.

This conftest.py is auto-discovered by pytest. Two responsibilities:

1. Put the ``tests/`` directory on ``sys.path`` so that test modules
   located under ``tests/<domain>/`` (e.g. ``tests/production/test_prereqs.py``)
   can do ``from turnkey_fixtures import grant_turnkey_self_materials``
   the same way they did when the suite was flat under ``tests/``.

2. (Future) Shared fixtures live in ``tests/turnkey_fixtures.py`` for
   historical reasons; new shared fixtures should be added either here
   (pytest auto-applies them) or in domain-specific ``conftest.py``
   files inside ``tests/<domain>/``.
"""

from __future__ import annotations

import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
