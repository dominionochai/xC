"""Compatibility shim for code importing ``backend.services.presets``.

The real module is ``backend.src.services.presets``.
"""
import sys

from backend.src.services import presets as _real

sys.modules[__name__] = _real
