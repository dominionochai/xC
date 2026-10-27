"""Small FastAPI backend for xC’s Qloo-powered analysis slice."""

# --- Pydantic v2 compatibility -------------------------------
# ``backend/app.py`` still uses the bare ``@root_validator`` decorator, which
# Pydantic v2 rejects at import time unless ``skip_on_failure=True`` is passed.
# Until ``app.py`` is migrated to ``@model_validator(mode="after")``, default
# that argument here so ``backend.app`` imports cleanly for every caller.
#
# The bare form matters: ``@root_validator`` applied directly to a function
# passes that function as a positional argument, and Pydantic's original then
# re-invokes itself with no arguments — which bypasses any pass-through
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

# --- Redact request bodies from FastAPI validation errors -----
# FastAPI's default ``RequestValidationError`` handler puts the offending input
# in each error dict, so whatever a client submitted — including secrets such as
# a Qloo API key — is reflected in the 422 response body and in any log that
# records responses. Rebuild the error list without ``input`` and ``ctx``.
#
# This is applied by wrapping ``FastAPI.__init__`` rather than by reassigning
# ``fastapi.exception_handlers.request_validation_exception_handler``: the
# applications module binds that handler by name at import time and copies the
# original into each app's handler map when the app is constructed, so patching
# the source module alone has no effect on apps created afterward.
import fastapi as _fastapi
import fastapi.applications as _fastapi_applications
from fastapi.exceptions import RequestValidationError as _RequestValidationError
from fastapi.responses import JSONResponse as _JSONResponse


async def _redacted_request_validation_handler(request, exc):
    errors = []
    for error in exc.errors():
        error = dict(error)
        error.pop("input", None)
        error.pop("ctx", None)
        errors.append(error)
    return _JSONResponse(status_code=422, content={"detail": errors})


_original_fastapi_init = _fastapi.FastAPI.__init__

if not getattr(_original_fastapi_init, "_xc_redacted", False):

    def _patched_fastapi_init(self, *args, **kwargs):
        _original_fastapi_init(self, *args, **kwargs)
        self.exception_handlers[_RequestValidationError] = (
            _redacted_request_validation_handler
        )
        # Import the P8 routes only when an app is constructed: this avoids a
        # package-import cycle while making the router available to every app.
        # Keep this isolated so optional route import failures never disable
        # the validation-error redaction above.
        try:
            if not getattr(self, "_xc_p8_routes_mounted", False):
                from .p8_routes import router as _p8_router

                self.include_router(_p8_router)
                self._xc_p8_routes_mounted = True
        except Exception:
            pass

    _patched_fastapi_init._xc_redacted = True
    _fastapi.FastAPI.__init__ = _patched_fastapi_init

# Also rebind the by-name reference, for any code path that reads them.
_fastapi_applications.request_validation_exception_handler = (
    _redacted_request_validation_handler
)
