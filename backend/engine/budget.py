"""Deterministic per-run budget accounting for the analysis engine.

The budget is deliberately local and dependency-free: callers charge work before
performing it, so a failed reservation never leaves a partially consumed budget.
"""
from __future__ import annotations

from dataclasses import dataclass


class BudgetExceeded(RuntimeError):
    """Raised when a requested operation would exceed the configured limit."""


@dataclass
class Budget:
    """Track integer work units against a fixed non-negative limit.

    ``used`` is public for straightforward diagnostics; callers should normally
    mutate it only through :meth:`charge` or :meth:`try_charge`.
    """

    limit: int
    used: int = 0
    name: str = "work"

    def __post_init__(self) -> None:
        if isinstance(self.limit, bool) or not isinstance(self.limit, int) or self.limit < 0:
            raise ValueError("limit must be a non-negative integer")
        if isinstance(self.used, bool) or not isinstance(self.used, int) or self.used < 0:
            raise ValueError("used must be a non-negative integer")
        if self.used > self.limit:
            raise ValueError("used cannot exceed limit")
        if not isinstance(self.name, str):
            raise TypeError("name must be a string")

    @property
    def remaining(self) -> int:
        """Number of work units still available."""
        return self.limit - self.used

    def charge(self, units: int = 1, *, reason: str | None = None) -> int:
        """Atomically consume ``units`` and return the new used count.

        Raises :class:`BudgetExceeded` without changing state when the request
        cannot be satisfied.
        """
        if isinstance(units, bool) or not isinstance(units, int) or units < 0:
            raise ValueError("units must be a non-negative integer")
        if units > self.remaining:
            detail = f" for {reason}" if reason else ""
            raise BudgetExceeded(
                f"{self.name} budget exceeded{detail}: requested {units}, "
                f"remaining {self.remaining}"
            )
        self.used += units
        return self.used

    def try_charge(self, units: int = 1) -> bool:
        """Consume units if possible, returning whether the charge succeeded."""
        if isinstance(units, bool) or not isinstance(units, int) or units < 0:
            raise ValueError("units must be a non-negative integer")
        if units > self.remaining:
            return False
        self.used += units
        return True

    def snapshot(self) -> dict[str, int | str]:
        """Return a JSON-safe diagnostic snapshot."""
        return {"name": self.name, "limit": self.limit, "used": self.used,
                "remaining": self.remaining}


# Explicit names make intent clear to consumers while preserving the concise API.
CallBudget = Budget
BudgetExceededError = BudgetExceeded
