"""Small FastAPI backend for xC's Qloo-powered analysis slice."""

# --- Pydantic v2 compatibility -------------------------------------------
# ``backend/app.py`` still uses the bare ``@root_validator`` decorator, which
# Pydantic v2 rejects at import time unless ``skip_on_failure=True`` is passed.
# Until ``app.py`` is migrated to ``@model_validator(mode="after")``, default
# that argument here so ``backend.app`` imports cleanly for every caller.
#
# The bare form matters: ``@root_validator`` applied directly to a function
# passes that function as a positional argument, and Pydantic's original then
# re-invokes itself with no arguments - which bypasses any pass-through
# wrapper. So the positional case must be intercepted explicitly here.
import pydantic as _pydantic

_original_root_validator = _pydantic.root_validator

if not getattr(_original_root_validator, "_xc_compat", False):

    def _root_validator(*args, **kwargs):
        if args:
            # Bare ``@root_validator`` applied straight to a function.
            return _original_root_validator(skip_on_failure=True)(*args)
        if not kwargs.get("pre", False):
            kwargs.setdefault("skip_on_failure", True)
        return _original_root_validator(**kwargs)

    _root_validator._xc_compat = True
    _pydantic.root_validator = _root_validator
