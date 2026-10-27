"""Runtime settings; secrets are read exclusively from the process environment."""

from dataclasses import dataclass
import os

QLOO_BASE_URL = "https://hackathon.api.qloo.com"


@dataclass(frozen=True)
class Settings:
    qloo_api_key: str | None

    @classmethod
    def from_environment(cls) -> "Settings":
        """Load settings without dotenv files, checked-in defaults, or key fallbacks."""
        key = os.environ.get("QLOO_API_KEY", "").strip()
        return cls(qloo_api_key=key or None)


def get_settings() -> Settings:
    return Settings.from_environment()
