"""W3 engine modules. Optional imports keep package use resilient to partial installs."""
from .budget import Budget

__all__ = ["Budget"]

for _name in ("resolve", "fit", "contrast", "communities", "simulation", "bridge", "locality", "tam", "ledger_glue", "assemble"):
    try:
        _module = __import__(f"{__name__}.{_name}", fromlist=[_name])
        globals()[_name] = _module
        __all__.append(_name)
    except Exception:
        pass
