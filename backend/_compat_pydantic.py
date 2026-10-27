"""Pydantic v2 compatibility shim.

``backend/app.py`` uses the bare ``@root_validator`` decorator (Pydantic v1
style) on ``ReportAnalysisInputs.distinct_entity_ids``. Under Pydantic v2 a
bare ``@root_validator`` raises ``PydanticUserError`` unless
``skip_on_failure=True`` is passed, so importing ``backend.app`` fails.

This module defaults that argument so the app can be imported and tested.
It is a TEST-SIDE workaround only: it does not fix a plain
``import backend.app`` outside of a process that imports this module first.

The real fix is to migrate ``backend/app.py`` to
``@model_validator(mode="after")`` and delete this file.
"""

from __future__ import annotations

import functools

import pydantic

_original_root_validator = pydantic.root_validator


@functools.wraps(_original_root_validator)
def root_validator(*args, **kwargs):
    """Drop-in ``pydantic.root_validator`` that defaults skip_on_failure."""
    kwargs.setdefault("skip_on_failure", True)
    return _original_root_validator(*args, **kwargs)


pydantic.root_validator = root_validator
