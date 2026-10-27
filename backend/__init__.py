"""Small FastAPI backend for xC's Qloo-powered analysis slice."""

# --- Pydantic v2 compatibility -------------------------------------------
# ``backend/app.py`` still uses the bare ``@root_validator`` decorator, which
# Pydantic v2 rejects at import time unless ``skip_on_failure=True`` is passed.
# Until ``app.py`` is migrated to ``@model_validator(mode="after")``, default
# the argument here so ``backend.app`` imports cleanly for every caller.
import functools as _functools

import pydantic as _pydantic

_original_root_validator = _pydantic.root_validator

if not getattr(_original_root_validator, "_xc_compat", False):

    @_functools.wraps(_original_root_validator)
    def _root_validator(*args, **kwargs):
        kwargs.setdefault("skip_on_failure", True)
        return _original_root_validator(*args, **kwargs)

    _root_validator._xc_compat = True
    _pydantic.root_validator = _root_validator
