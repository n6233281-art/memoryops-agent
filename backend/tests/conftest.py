"""Shared pytest fixtures for the MemoryOps backend tests.

The tests never touch the network: Hindsight and Groq are replaced by the stubs
in ``fakes.py``. Each test gets its own temporary incident ledger.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import DEFAULT_HINDSIGHT_URL, Settings
from app.incident_service import IncidentService, IncidentStore
from app.llm import GroqLLM
from app.main import create_app, get_incident_service

from .fakes import StubAsyncGroq, StubMemory


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    """Settings with no API keys and a throwaway data file."""
    values: dict[str, object] = {
        "groq_api_key": "",
        "groq_model": "openai/gpt-oss-120b",
        "hindsight_api_key": "",
        "hindsight_url": DEFAULT_HINDSIGHT_URL,
        "hindsight_bank_id": "memoryops-test-bank",
        "data_file": tmp_path / "incidents.json",
        "hindsight_timeout_seconds": 5.0,
        "groq_timeout_seconds": 5.0,
    }
    values.update(overrides)
    # _env_file=None keeps a developer's real backend/.env out of the tests.
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def build_client(settings: Settings, memory: object, llm: object | None = None) -> TestClient:
    """Build a TestClient whose incident service uses the supplied stubs."""
    service = IncidentService(
        settings=settings,
        memory=memory,  # type: ignore[arg-type]
        llm=llm or GroqLLM(settings),  # type: ignore[arg-type]
        store=IncidentStore(settings.data_file),
    )
    app = create_app()
    app.dependency_overrides[get_incident_service] = lambda: service
    return TestClient(app)


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    """Unconfigured settings (no keys at all)."""
    return make_settings(tmp_path)


@pytest.fixture()
def stub_groq() -> StubAsyncGroq:
    return StubAsyncGroq()


@pytest.fixture()
def client(settings: Settings, stub_groq: StubAsyncGroq) -> TestClient:
    """Client backed by the real HindsightClient with no key -> unavailable."""
    from app.hindsight_client import HindsightClient

    return build_client(
        settings,
        HindsightClient(settings),
        GroqLLM(settings),
    )


@pytest.fixture()
def memory_client(settings: Settings) -> TestClient:
    """Client backed by a stub Hindsight that returns one recalled memory."""
    return build_client(
        make_settings(settings.data_file.parent), StubMemory(), StubAsyncGroq()
    )


@pytest.fixture()
def failing_memory_client(settings: Settings) -> TestClient:
    """Client backed by a stub Hindsight that always errors."""
    return build_client(
        make_settings(settings.data_file.parent), StubMemory(fail=True), StubAsyncGroq()
    )


@pytest.fixture()
def failing_groq_memory_client(settings: Settings) -> TestClient:
    """Hindsight works, but the Groq call raises -> memory-driven fallback."""
    return build_client(
        make_settings(settings.data_file.parent),
        StubMemory(),
        StubAsyncGroq(fail=True),
    )
