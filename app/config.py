"""Runtime settings, read once from environment variables.

Secrets (ANTHROPIC_API_KEY) are only ever read from the environment. In Azure
they come from a Container Apps secret; locally from a git-ignored .env file.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv() -> None:
    env = Path(__file__).resolve().parent.parent / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    model: str = field(default_factory=lambda: os.getenv("MODEL", "claude-opus-5-5"))
    effort: str = field(default_factory=lambda: os.getenv("EFFORT", "low"))
    fallbacks: str = field(default_factory=lambda: os.getenv("FALLBACKS", "default"))
    provider: str = field(
        default_factory=lambda: os.getenv(
            "LLM_PROVIDER", "anthropic" if os.getenv("ANTHROPIC_API_KEY") else "fake"
        )
    )
    access_code: str = field(default_factory=lambda: os.getenv("ACCESS_CODE", ""))
    session_token_budget: int = field(
        default_factory=lambda: int(os.getenv("SESSION_TOKEN_BUDGET", "400000"))
    )
    daily_token_budget: int = field(
        default_factory=lambda: int(os.getenv("DAILY_TOKEN_BUDGET", "5000000"))
    )
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", "./podsim.db"))


# Models that accept the server-side refusal fallback parameter.
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-2", "claude-fable-5-1"}


def get_settings() -> Settings:
    return Settings()
