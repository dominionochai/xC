"""Pytest configuration for xC.

pytest aborts the whole session when any module fails to import, so legacy
tests that target packages removed from this repo are skipped here rather
than deleted. Remove an entry once the module is ported to backend.*.

`collect_ignore` is evaluated during discovery, before import, which is what
makes it able to prevent collection errors. A
`pytest_collection_modifyitems` hook cannot do this: it runs too late.
"""

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
