"""Pytest configuration for xC.

Two jobs, both applied before any test module is imported:

1. Apply the Pydantic v2 ``root_validator`` compatibility shim so that
   ``backend.app`` can be imported. See ``backend/_compat_pydantic.py``.
2. Skip legacy tests that target packages removed from this repo, rather than
   deleting them. ``collect_ignore`` is evaluated during discovery, before
   import, which is what makes it able to prevent collection errors; a
   ``pytest_collection_modifyitems`` hook runs too late to do this.

Remove an entry from either list once the underlying module is fixed.
"""

import backend._compat_pydantic  # noqa: F401  (must run before backend.app)

collect_ignore = [
    "tests/test_cli.py",
    "tests/test_contract.py",
    "tests/test_engine_assemble.py",
    "tests/test_engine_budget.py",
    "tests/test_engine_communities.py",
    "tests/test_engine_contrast.py",
    "tests/test_engine_fit.py",
    "tests/test_engine_resolve.py",
]
