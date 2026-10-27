"""Small FastAPI backend for xC's Qloo-powered analysis slice."""

# --- Pydantic v2 compatibility ----------------------------------------------
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

# --- Validation errors must never echo the request body --------------------
# FastAPI's default ``RequestValidationError`` handler includes the offending
# input in each error dict. That reflects whatever the client submitted,
# including secrets such as a Qloo API key, back in the 422 response body and
# into any log that records responses. Strip ``input`` (and ``ctx``, which can
# hold submitted values) before the response is serialised.
#
# The handler is patched here, in the package initialiser, because
# ``backend/app.py`` builds its ``FastAPI`` instance at import time and copies
# the handler reference from this module when it does so.
import fastapi.exception_handlers as _fastapi_handlers

_original_request_validation_handler = (
    _fastapi_handlers.request_validation_exception_handler
)

if not getattr(_original_request_validation_handler, "_xc_redacted", False):

    async def _redacted_request_validation_handler(request, exc):
        response = await _original_request_validation_handler(request, exc)
        body = getattr(response, "body", None)
        if body:
            import json as _json

            try:
                payload = _json.loads(body)
            except (TypeError, ValueError):
                return response
            for error in payload.get("detail", []):
                if isinstance(error, dict):
                    error.pop("input", None)
                    error.pop("ctx", None)
            response.body = _json.dumps(payload).encode("utf-8")
            headers = getattr(response, "headers", None)
            if headers is not None:
                headers["content-length"] = str(len(response.body))
        return response

    _redacted_request_validation_handler._xc_redacted = True
    _fastapi_handlers.request_validation_exception_handler = (
        _redacted_request_validation_handler
    )
