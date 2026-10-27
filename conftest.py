"""Pytest configuration for xC.

pytest aborts the whole session when any module fails to import, so legacy
tests that target packages removed from this repo are excluded here rather
than deleted. Remove an entry once the module is ported to backend.*.
"""

LEGACY_TEST_MODULES = {
    "tests/test_cli.py",
    "tests/test_contract.py",
    "tests/test_engine_assemble.py",
    "tests/test_engine_budget.py",
    "tests/test_engine_communities.py",
    "tests/test_engine_contrast.py",
    "tests/test_engine_fit.py",
    "tests/test_engine_resolve.py",
}


def pytest_collection_modifyitems(config, items):
    """Drop tests from modules that import packages no longer in the repo."""
    import os

    kept = []
    for item in items:
        rel = os.path.relpath(str(item.fspath), str(config.rootpath)).replace(os.sep, "/")
        if rel not in LEGACY_TEST_MODULES:
            kept.append(item)
    items[:] = kept
