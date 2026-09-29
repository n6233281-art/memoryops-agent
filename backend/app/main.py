"""MemoryOps FastAPI application — AI incident-response agent with Hindsight memory.

Endpoints
---------
GET  /api/health                            Service + configuration status
GET  /api/memory/status                     Live Hindsight readiness probe
GET  /api/incidents                         Incident history
GET  /api/incidents/{incident_id}           Single incident
POST /api/incidents/analyze                 Analyse a new incident (Hindsight + Groq)
POST /api/incidents/{incident_id}/resolve   Store the resolved experience in Hindsight
POST /api/demo/reset                        Clear the demo ledger
GET  /api/demo/synthetic-example            Clearly labelled synthetic demo data
"""

from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import Settings, get_settings, log_configuration
from .incident_service import IncidentService
from .models import (
    AnalyzeRequest,
    AnalyzeResponse,
    HealthResponse,
    IncidentHistoryResponse,
    IncidentRecord,
    MemoryProbeResponse,
    ResolveRequest,
    ResolveResponse,
)

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_incident_service() -> IncidentService:
    """FastAPI dependency returning the shared incident service."""
    return IncidentService(get_settings())


def create_app() -> FastAPI:
    settings: Settings = get_settings()

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    # Report exactly what configuration was loaded (secret-free) and shout about
    # anything that will silently degrade the demo.
    log_configuration()

    app = FastAPI(
        title="MemoryOps — AI Incident Response Agent",
        version=__version__,
        description=(
            "An incident-response assistant that recalls previous production incidents "
            "from Hindsight by Vectorize and turns them into specific recommendations."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list or ["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- health -----------------------------------------------------------
    @app.get("/api/health", response_model=HealthResponse, tags=["system"])
    async def health(
        service: IncidentService = Depends(get_incident_service),
    ) -> HealthResponse:
        """Liveness plus configuration check. Never calls external services."""
        active: Settings = service.settings
        return HealthResponse(
            app=active.app_name,
            version=__version__,
            synthetic_demo_data=active.synthetic_demo_data,
            groq_configured=active.groq_configured,
            groq_model=active.groq_model,
            hindsight_configured=active.hindsight_configured,
            hindsight_bank_id=active.hindsight_bank_id,
            hindsight_url=active.hindsight_url,
            data_file=str(active.data_file),
            incidents_stored=service.store.count(),
        )

    @app.get("/api/memory/status", response_model=MemoryProbeResponse, tags=["memory"])
    async def memory_status(
        service: IncidentService = Depends(get_incident_service),
    ) -> MemoryProbeResponse:
        """Probe Hindsight so the dashboard can show a real memory-layer status."""
        return MemoryProbeResponse(memory_status=await service.memory.probe())

    # -- incidents --------------------------------------------------------
    @app.post(
        "/api/incidents/analyze",
        response_model=AnalyzeResponse,
        status_code=status.HTTP_200_OK,
        tags=["incidents"],
    )
    async def analyze_incident(
        request: AnalyzeRequest,
        service: IncidentService = Depends(get_incident_service),
    ) -> AnalyzeResponse:
        """Search Hindsight for similar incidents, then reason with Groq."""
        try:
            return await service.analyze(request)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Incident analysis failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Incident analysis failed: {exc}",
            ) from exc

    @app.post(
        "/api/incidents/{incident_id}/resolve",
        response_model=ResolveResponse,
        tags=["incidents"],
    )
    async def resolve_incident(
        incident_id: str,
        request: ResolveRequest,
        service: IncidentService = Depends(get_incident_service),
    ) -> ResolveResponse:
        """Store the resolved incident experience in Hindsight."""
        try:
            return await service.resolve(incident_id, request)
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Incident {incident_id} was not found.",
            ) from None
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Incident resolution failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Incident resolution failed: {exc}",
            ) from exc

    @app.get("/api/incidents", response_model=IncidentHistoryResponse, tags=["incidents"])
    async def list_incidents(
        limit: int = Query(default=50, ge=1, le=200),
        service: IncidentService = Depends(get_incident_service),
    ) -> IncidentHistoryResponse:
        """Incident history, newest first."""
        records = service.store.list()
        return IncidentHistoryResponse(incidents=records[:limit], total=len(records))

    @app.get(
        "/api/incidents/{incident_id}",
        response_model=IncidentRecord,
        tags=["incidents"],
    )
    async def get_incident(
        incident_id: str,
        service: IncidentService = Depends(get_incident_service),
    ) -> IncidentRecord:
        record = service.store.get(incident_id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Incident {incident_id} was not found.",
            )
        return record

    # -- demo helpers -----------------------------------------------------
    @app.post("/api/demo/reset", tags=["demo"])
    async def reset_demo(
        clear_hindsight: bool = Query(
            default=False,
            description=(
                "Also delete the memories in the Hindsight bank. Keep this false to show "
                "that learned memory survives a UI reset."
            ),
        ),
        service: IncidentService = Depends(get_incident_service),
    ) -> dict[str, object]:
        """Clear the local demo ledger (optionally the Hindsight bank)."""
        await service.store.reset()
        memory_deleted = False
        if clear_hindsight:
            memory_deleted = await _delete_bank(service.settings)
        return {
            "reset": True,
            "incidents_cleared": True,
            "hindsight_bank_cleared": memory_deleted,
            "bank_id": service.settings.hindsight_bank_id,
        }

    @app.get("/api/demo/synthetic-example", tags=["demo"])
    async def synthetic_example() -> dict[str, object]:
        """The synthetic Payment API 503 example used by Demo Mode.

        Clearly labelled synthetic/demo data — not a real incident.
        """
        return SYNTHETIC_DEMO_INCIDENT

    return app


app = create_app()
SYNTHETIC_DEMO_INCIDENT: dict[str, object] = {
    "synthetic": True,
    "label": "SYNTHETIC DEMO DATA — not a real incident",
    "incident_id": "INC-001",
    "service": "Payment API",
    "symptom": "HTTP 503 errors",
    "severity": "SEV2",
    "environment": "production",
    "error_signature": "upstream connect error / connection pool timeout",
    "description": (
        "Synthetic demo: the Payment API started returning HTTP 503 for roughly 4% of "
        "checkout requests within two minutes of the evening traffic peak. No deployment "
        "had shipped in the previous 12 hours."
    ),
    "root_cause": "Database connection pool exhaustion",
    "resolution": "Increased database connection pool from 50 to 100",
    "outcome": "Payment API recovered and error rate returned to normal",
    "outcome_status": "resolved",
}


async def _delete_bank(settings: Settings) -> bool:
    """Best-effort delete of the Hindsight bank (demo reset only)."""
    if not settings.hindsight_configured:
        return False
    try:
        import httpx

        headers = {"Authorization": f"Bearer {settings.hindsight_api_key}"}
        url = f"{settings.hindsight_url.rstrip('/')}/v1/default/banks/{settings.hindsight_bank_id}"
        async with httpx.AsyncClient(timeout=settings.hindsight_timeout_seconds) as http:
            response = await http.delete(url, headers=headers)
        return response.status_code < 300
    except Exception as exc:  # pragma: no cover - network dependent
        logger.warning("Could not clear Hindsight bank: %s", exc)
        return False
