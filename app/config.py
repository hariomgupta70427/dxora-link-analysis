"""Configuration for the AI-Powered Website Link Analysis API.

All credentials come from environment variables only. Nothing secret is
hardcoded or committed. Copy ``.env.example`` to ``.env`` and fill it in.
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Load .env at import time so `uvicorn app.main:app` picks up keys
# without the shell having to export them. python-dotenv never prints
# values; a missing .env is fine (keys can come from real env vars).
load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _sanitize_no_proxy() -> None:
    """httpx 0.28.1 raises ``InvalidURL: Invalid port: ':1]'`` when
    constructing any client if ``no_proxy``/``NO_PROXY`` contains a
    bracketed IPv6 literal such as ``[::1]`` — which is exactly what
    this sandbox's default NO_PROXY contains. Strip bracketed entries
    at import time (before any httpx client is built); ``localhost``
    and ``127.0.0.1`` stay bypassed. Harmless anywhere else."""
    for var in ("no_proxy", "NO_PROXY"):
        value = os.environ.get(var)
        if not value:
            continue
        os.environ[var] = ",".join(e for e in value.split(",") if "[" not in e)


_sanitize_no_proxy()


@dataclass
class Settings:
    """All settings, read from the environment at import time."""

    # Test mode: when "1", the LLM service returns a deterministic mock
    # analysis built from the extracted content — no LLM call, no key
    # needed. Used by the test suite. Never returns invented competitors
    # or volumes; the mock is labelled as such in the response meta.
    test_mode: bool = field(default_factory=lambda: _env("TEST_MODE") == "1")

    # Primary LLM: NVIDIA hosted API (OpenAI-compatible chat completions).
    # Free prototyping tier key from https://build.nvidia.com.
    nvidia_api_key: str = field(default_factory=lambda: _env("NVIDIA_API_KEY"))
    nvidia_base_url: str = field(
        default_factory=lambda: _env(
            "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1/chat/completions"
        )
    )
    nvidia_model: str = field(
        default_factory=lambda: _env("NVIDIA_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")
    )

    # Fallback LLM: Google Gemini free tier (only used when set and the
    # primary call fails).
    gemini_api_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY"))
    gemini_model: str = field(
        default_factory=lambda: _env("GEMINI_MODEL", "gemini-2.5-flash")
    )

    # Website fetching limits.
    fetch_timeout_seconds: float = 20.0
    max_redirects: int = 5
    # Characters of cleaned page text sent to the LLM (keeps the prompt
    # small: ~3,000 tokens of content + prompt overhead).
    max_content_chars: int = 12000

    @property
    def llm_configured(self) -> bool:
        return bool(self.nvidia_api_key or self.gemini_api_key)


settings = Settings()
