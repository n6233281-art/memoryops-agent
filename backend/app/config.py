"""Application configuration for MemoryOps.

Every secret is read from the environment (or ``backend/.env``). Nothing is
hard-coded, so the same code runs against a local Hindsight server, Hindsight
Cloud, or any other deployment without changes.

Environment variables
---------------------
GROQ_API_KEY        API key for Groq (LLM reasoning).
GROQ_MODEL          Groq model id, e.g. ``openai/gpt-oss-120b``.
HINDSIGHT_API_KEY   API key for Hindsight by Vectorize (``hsk_...``).
HINDSIGHT_URL       Base URL of the Hindsight API.
                    ``HINDSIGHT_API_URL`` is accepted as an alias because that
                    is the name used by the official Hindsight CLI/SDK.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# backend/app/config.py -> backend/ -> project root
BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent

DEFAULT_DATA_FILE = PROJECT_ROOT / "data" / "incidents.json"

#: Primary location, as documented in the README and backend/.env.example.
DEFAULT_ENV_FILE = BACKEND_DIR / ".env"
#: Convenience fallback so a root-level .env also works.
PROJECT_ROOT_ENV_FILE = PROJECT_ROOT / ".env"
#: Tracked template. It must never contain real values.
ENV_EXAMPLE_FILE = BACKEND_DIR / ".env.example"

#: Highest priority first: the backend file wins over the project-root fallback.
ENV_FILE_CANDIDATES: tuple[Path, ...] = (DEFAULT_ENV_FILE, PROJECT_ROOT_ENV_FILE)

#: Variables needed for the memory layer to work.
MEMORY_ENV_KEYS = ("HINDSIGHT_API_KEY", "HINDSIGHT_URL")
#: Variables needed for LLM reasoning to work.
LLM_ENV_KEYS = ("GROQ_API_KEY", "GROQ_MODEL")
#: The actual credentials. Only these count as "someone put secrets here" — the
#: other keys are non-secret defaults that legitimately live in .env.example.
SECRET_ENV_KEYS = ("GROQ_API_KEY", "HINDSIGHT_API_KEY")

#: Public Hindsight Cloud endpoint (self-hosted installs usually use
#: ``http://localhost:8888``). Override with HINDSIGHT_URL.
DEFAULT_HINDSIGHT_URL = "https://api.hindsight.vectorize.io"

#: Groq production model used by default. See https://console.groq.com/docs/models
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"


def _sniff_encoding(path: Path) -> str:
    """Pick a text encoding for a .env file.

    Handles the BOMs and the UTF-16 output Windows PowerShell produces — both make
    ``python-dotenv`` parse keys that match nothing (e.g. ``G\\x00R\\x00O\\x00Q``).
    """
    try:
        raw = path.read_bytes()
    except OSError:
        return "utf-8"

    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    # UTF-16 without a BOM is mostly NUL bytes for ASCII content.
    if raw and raw.count(b"\x00") > len(raw) * 0.1:
        return "utf-16"
    return "utf-8"


def _load_one_env_file(path: Path, override: bool) -> dict[str, object]:
    """Merge one .env file into ``os.environ`` and return a value-free report."""
    encoding = _sniff_encoding(path)
    try:
        values = dotenv_values(path, encoding=encoding)
    except Exception as exc:  # pragma: no cover - unreadable file
        logger.warning("Could not parse %s (%s)", path, exc)
        return {"path": str(path), "encoding": encoding, "keys": [], "error": str(exc)}

    keys: list[str] = []
    for key, value in values.items():
        if not key or value is None:
            continue
        keys.append(key)
        if override or key not in os.environ:
            os.environ[key] = value

    return {"path": str(path), "encoding": encoding, "keys": sorted(keys)}


def load_env_files(override: bool = False) -> list[dict[str, object]]:
    """Load every candidate ``.env`` file into ``os.environ``.

    Runs on import so settings work however the app is started
    (``uvicorn app.main:app`` from ``backend/``, a script, or pytest).

    With ``override=False`` a real environment variable always beats a file value,
    and the higher-priority file is loaded first so it wins.
    """
    report: list[dict[str, object]] = []
    seen: set[str] = set()
    for path in ENV_FILE_CANDIDATES:
        try:
            resolved = str(path.resolve()).lower()
        except OSError:  # pragma: no cover - defensive
            continue
        if resolved in seen or not path.is_file():
            continue
        seen.add(resolved)
        report.append(_load_one_env_file(path, override=override))
    return report


#: Populated at import time, before any Settings() is constructed.
ENV_LOAD_REPORT: list[dict[str, object]] = load_env_files()


def env_example_is_populated() -> bool:
    """True when the tracked *.env.example* holds real-looking credentials.

    Only the two secret keys count — ``GROQ_MODEL`` and ``HINDSIGHT_URL`` legitimately
    hold non-secret defaults in the template.
    """
    if not ENV_EXAMPLE_FILE.is_file():
        return False
    try:
        values = dotenv_values(ENV_EXAMPLE_FILE, encoding=_sniff_encoding(ENV_EXAMPLE_FILE))
    except Exception:  # pragma: no cover - unreadable file
        return False
    return any((values.get(key) or "").strip() for key in SECRET_ENV_KEYS)


def _display_path(path: Path) -> str:
    """Path relative to the project root when possible, for readable reports."""
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except (ValueError, OSError):
        return str(path)


class Settings(BaseSettings):
    """Runtime settings loaded from the environment."""

    model_config = SettingsConfigDict(
        # Belt and braces: .env files are also merged into os.environ at import
        # time (with encoding detection) by load_env_files(). Real environment
        # variables outrank both mechanisms.
        env_file=[str(path) for path in ENV_FILE_CANDIDATES],
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "MemoryOps"
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    # --- Groq (LLM) -----------------------------------------------------
    groq_api_key: str = Field(default="", validation_alias="GROQ_API_KEY")
    groq_model: str = Field(default=DEFAULT_GROQ_MODEL, validation_alias="GROQ_MODEL")
    groq_timeout_seconds: float = Field(default=60.0, validation_alias="GROQ_TIMEOUT_SECONDS")
    groq_temperature: float = Field(default=0.2, validation_alias="GROQ_TEMPERATURE")
    groq_max_tokens: int = Field(default=2048, validation_alias="GROQ_MAX_TOKENS")

    # --- Hindsight by Vectorize (memory) --------------------------------
    hindsight_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("HINDSIGHT_API_KEY", "HINDSIGHT_KEY"),
    )
    hindsight_url: str = Field(
        default=DEFAULT_HINDSIGHT_URL,
        validation_alias=AliasChoices("HINDSIGHT_URL", "HINDSIGHT_API_URL"),
    )
    hindsight_bank_id: str = Field(
        default="memoryops-incidents",
        validation_alias="HINDSIGHT_BANK_ID",
    )
    hindsight_timeout_seconds: float = Field(
        default=45.0, validation_alias="HINDSIGHT_TIMEOUT_SECONDS"
    )
    hindsight_recall_limit: int = Field(default=5, validation_alias="HINDSIGHT_RECALL_LIMIT")

    # --- Demo / storage -------------------------------------------------
    data_file: Path = Field(default=DEFAULT_DATA_FILE, validation_alias="DATA_FILE")
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173",
        validation_alias="CORS_ORIGINS",
    )
    synthetic_demo_data: bool = Field(default=True, validation_alias="SYNTHETIC_DEMO_DATA")

    # --- Derived helpers -------------------------------------------------
    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def hindsight_configured(self) -> bool:
        """True when both a URL and an API key are present."""
        return bool(self.hindsight_url.strip() and self.hindsight_api_key.strip())

    @property
    def groq_configured(self) -> bool:
        return bool(self.groq_api_key.strip() and self.groq_model.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()


def reset_settings_cache() -> None:
    """Clear the settings cache (used by tests)."""
    get_settings.cache_clear()


def config_report() -> dict[str, object]:
    """Describe the loaded configuration **without exposing any secret value**.

    Safe to log and safe to print. Keys are reported by name, length and a
    boolean "populated" flag only.
    """
    settings = get_settings()

    env_files = []
    for entry in ENV_LOAD_REPORT:
        env_files.append(
            {
                "path": _display_path(Path(str(entry.get("path")))),
                "encoding": entry.get("encoding"),
                "keys_loaded": entry.get("keys", []),
                "error": entry.get("error"),
            }
        )

    missing = []
    checked = []
    roles = {DEFAULT_ENV_FILE: "primary", PROJECT_ROOT_ENV_FILE: "optional fallback"}
    for path in ENV_FILE_CANDIDATES:
        exists = path.is_file()
        checked.append(
            {
                "path": _display_path(path),
                "role": roles.get(path, "candidate"),
                "exists": exists,
            }
        )
        if not exists:
            missing.append(_display_path(path))

    return {
        "env_files_loaded": env_files,
        "env_files_checked": checked,
        "env_files_absent": missing,
        "env_example_populated": env_example_is_populated(),
        "groq_configured": settings.groq_configured,
        "groq_model": settings.groq_model,
        "groq_api_key_present": bool(settings.groq_api_key.strip()),
        "groq_api_key_length": len(settings.groq_api_key),
        "hindsight_configured": settings.hindsight_configured,
        "hindsight_url": settings.hindsight_url,
        "hindsight_bank_id": settings.hindsight_bank_id,
        "hindsight_api_key_present": bool(settings.hindsight_api_key.strip()),
        "hindsight_api_key_length": len(settings.hindsight_api_key),
        "data_file": str(settings.data_file),
    }


def configuration_warnings() -> list[str]:
    """Actionable, secret-free warnings about a broken configuration."""
    settings = get_settings()
    warnings: list[str] = []

    if not any(path.is_file() for path in ENV_FILE_CANDIDATES):
        warnings.append(
            "No .env file found at "
            + " or ".join(_display_path(path) for path in ENV_FILE_CANDIDATES)
            + ". Create it with: Copy-Item backend/.env.example backend/.env"
        )
    elif env_example_is_populated() and not (
        settings.groq_configured and settings.hindsight_configured
    ):
        warnings.append(
            f"{_display_path(ENV_EXAMPLE_FILE)} holds real credentials, but it is NOT "
            "loaded (only .env is) and it is tracked by git. Move the values into "
            "backend/.env and blank the template."
        )

    missing_llm = [key for key in LLM_ENV_KEYS if not (os.environ.get(key) or "").strip()]
    missing_memory = [
        key for key in MEMORY_ENV_KEYS if not (os.environ.get(key) or "").strip()
    ]

    if missing_llm:
        warnings.append(
            "Missing LLM configuration: "
            + ", ".join(missing_llm)
            + " — the agent will use its deterministic runbook instead of Groq."
        )
    if missing_memory:
        warnings.append(
            "Missing memory configuration: "
            + ", ".join(missing_memory)
            + " — Hindsight memory is unavailable and no memories can be stored or recalled."
        )
    return warnings


def log_configuration() -> list[str]:
    """Log the configuration and return the warnings. Never logs secret values."""
    settings = get_settings()
    report = config_report()

    for entry in report["env_files_loaded"]:
        logger.info(
            ".env loaded: %s (encoding=%s, %d key(s): %s)",
            entry["path"],
            entry["encoding"],
            len(entry["keys_loaded"]),
            ", ".join(entry["keys_loaded"]) or "none",
        )
    if not report["env_files_loaded"]:
        logger.info("No .env file was loaded.")
    for entry in report["env_files_checked"]:
        if not entry["exists"]:
            logger.info(
                "Env file not present (%s): %s", entry["role"], entry["path"]
            )

    logger.info(
        "Config: groq_configured=%s model=%s | hindsight_configured=%s url=%s bank=%s",
        settings.groq_configured,
        settings.groq_model,
        settings.hindsight_configured,
        settings.hindsight_url,
        settings.hindsight_bank_id,
    )

    warnings = configuration_warnings()
    for warning in warnings:
        logger.warning("Configuration warning: %s", warning)
    return warnings


def _main() -> None:  # pragma: no cover - developer utility
    """``python -m app.config`` — print a secret-free configuration report."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = config_report()
    for key, value in report.items():
        print(f"{key} = {value}")
    print()
    warnings = configuration_warnings()
    if warnings:
        print("WARNINGS:")
        for warning in warnings:
            print(f"  - {warning}")
    else:
        print("No configuration warnings. Groq and Hindsight are both configured.")


if __name__ == "__main__":  # pragma: no cover - developer utility
    _main()
