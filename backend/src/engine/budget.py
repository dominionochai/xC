"""Immutable per-run call and result budget."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Budget:
    max_calls: int = 40
    max_items: int = 350

    def __post_init__(self) -> None:
        if self.max_calls < 0 or self.max_items < 0:
            raise ValueError("budget limits must be non-negative")

    @classmethod
    def default(cls) -> "Budget":
        return cls(40, 350)

    def exhausted(self, call_count: int) -> bool:
        return call_count >= self.max_calls
