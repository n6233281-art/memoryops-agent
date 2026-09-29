# Architecture

MemoryOps is a small system with one unusual property: **the interesting state is outside the
application**. The FastAPI backend is stateless reasoning; the durable incident knowledge
lives in Hindsight by Vectorize.

---

## 1. Component map

```
React + Vite dashboard          http://localhost:5173
        │  /api/* (Vite dev proxy → http://127.0.0.1:8000)
        ▼
FastAPI backend                 http://127.0.0.1:8000
        │
        ├── IncidentResponseAgent  ──► Hindsight by Vectorize   (memory: recall / retain)
        │                          └─► Groq                     (reasoning)
        └── IncidentStore          ──► data/incidents.json      (demo ledger)
```

| Layer | File | Responsibility |
|---|---|---|
| HTTP | `backend/app/main.py` | Routes, CORS, validation, error mapping. No business logic. |
| Agent | `backend/app/agent.py` | The learning loop: **recall → reason → explain**. Enforces that a memory is never claimed unless it was actually recalled. |
| Memory | `backend/app/hindsight_client.py` | All Hindsight by Vectorize I/O: bank setup, retain, recall, result mapping, honest status reporting. |
| Reasoning | `backend/app/llm.py` | Groq chat completions, strict JSON parsing, deterministic fallback. |
| Prompts | `backend/app/prompts.py` | The contract with the LLM: the memory block is either real memories or the literal `NO_MEMORY_AVAILABLE`. |
| Orchestration | `backend/app/incident_service.py` | Incident lifecycle, ledger persistence, experience composition. |
| Contracts | `backend/app/models.py` | Pydantic models shared by API, agent, memory and UI. |
| Config | `backend/app/config.py` | Env-driven settings, alias handling. No secrets in code. |

---

## 2. Request flows

### 2.1 `POST /api/incidents/analyze`

```
1  main.analyze_incident          validate AnalyzeRequest (Pydantic)
2  IncidentStore.next_incident_id allocate INC-00N, build the open record
3  Agent.build_query              "Production incident on the Payment API with the
                                   symptom: HTTP 503 errors. What was the root cause…"
4  HindsightClient
     .search_relevant_memories    POST /v1/default/banks/{bank}/memories/recall
                                  → up to N MemoryHit + MemoryStatus
5  HindsightClient
     .format_memories_for_prompt  numbered MEMORY blocks, or NO_MEMORY_AVAILABLE
6  GroqLLM.analyze                chat completion, response_format=json_object
7  GroqLLM._parse_actions         validates ids against the recalled set, tags every
                                  action hindsight_memory | general_knowledge
8  Agent.investigate (defensive)  if no memory was recalled, force memory_used=false
                                  and downgrade unbacked memory-sourced actions
9  IncidentStore.upsert           persist record + memories + status
10 AnalyzeResponse                analysis, actions, retrieved_memories, memory_status,
                                  llm_status
```

Important design choice at step 7: `based_on_memory_ids` must reference a *real* recalled
memory id. Hallucinated ids are dropped and the action is downgraded to `general_knowledge`.
The UI therefore never shows a fake memory attribution.

### 2.2 `POST /api/incidents/{id}/resolve`

```
1  IncidentStore.get              load the open incident (404 if unknown)
2  merge                          root_cause, resolution, outcome, outcome_status, timing
3  GroqLLM.summarize_lesson       one-line lesson (skipped when Groq is unconfigured)
4  build_incident_experience      render the labelled postmortem document
5  build_incident_metadata        structured string metadata (incident_id, service,
                                  symptom, root_cause, resolution, outcome…)
6  HindsightClient
     .store_incident_experience   POST /v1/default/banks/{bank}/memories (async=false)
7  IncidentStore.upsert           mark resolved, record the Hindsight document id
8  ResolveResponse                stored_to_memory, memory_status, message, lesson
```

`async=false` is deliberate. Synchronous retain blocks until Hindsight has finished fact
extraction, which guarantees the memory is recallable by the very next request — essential for
a live demo where step 5 follows step 3 within seconds.

---

## 3. Failure behaviour

| Failure | Detected by | Behaviour |
|---|---|---|
| `HINDSIGHT_API_KEY` missing | `Settings.hindsight_configured` | `MemoryStatus.available=false`, `message="Hindsight memory unavailable"`, `retrieved_memories=[]`. Never claims a memory. |
| Hindsight unreachable / 4xx / 5xx | transport exception | `available=false`, `error` carries the cause, empty memory list. |
| Hindsight reachable, bank empty | `results=[]` | `available=true`, `memories_found=0`, message "…holds no relevant memory for this incident yet." The UI shows *No relevant memory found* — distinct from "unavailable". |
| `GROQ_API_KEY` missing | `Settings.groq_configured` | Deterministic runbook. Memory-based fallbacks keep `source=hindsight_memory`; generic ones become `general_knowledge`. `llm_status.used=false`. |
| Groq call fails mid-flight | exception | Same deterministic fallback, with the cause captured in `llm_status.error`. |
| Groq returns malformed JSON | `_extract_json` | Code fences stripped, first `{…}` block extracted; on total failure the fallback path runs. |
| Retain fails | transport exception | `stored_to_memory=false`, `memory_document_id=null`, message "…the experience was NOT stored." The incident is still marked resolved locally. |

---

## 4. Data model

```
IncidentRecord
├── identity    incident_id, title, service, symptom, severity, environment,
│               error_signature, reported_by, created_at, started_at
├── analysis    analysis{summary, severity_assessment, likely_causes, memory_used,
│               memory_influence, similar_incident_ids, generated_by}
├── actions     recommended_actions[{action, rationale, confidence, source, priority,
│               based_on_memory_ids}]
├── memory      retrieved_memories[MemoryHit], memory_status{…}
└── resolution  root_cause, resolution, outcome, outcome_status, resolved_by,
                resolved_at, time_to_resolve_minutes, notes, lesson,
                memory_document_id, memory_ids
```

`MemoryHit.demo_metadata` is derived **only** from what Hindsight returned, and carries the
previous incident's `service`, `symptom`, `root_cause`, `resolution` and `outcome`. That is
what lets the dashboard show a structured "previous incident" card rather than a wall of text.

---

## 5. Storage split

| Store | Contents | Why |
|---|---|---|
| **Hindsight bank** (`memoryops-incidents`) | Extracted facts and experiences from every postmortem | This *is* the product: durable, queryable, semantically recalled experience |
| `data/incidents.json` | Incident metadata ledger for the dashboard | Simple demo bookkeeping. Writes are atomic (temp file + `Path.replace`) |

The ledger is intentionally dumb. It cannot make the agent smarter; only Hindsight can.

---

## 6. Frontend structure

The UI is a small React Router SPA: a standalone landing page, then a shell (sidebar + topbar)
wrapping five focused screens. All API calls live in one state layer, so screens are presentational.

| File | Role |
|---|---|
| `App.jsx` | Route table; landing is standalone, the rest share `AppShell` |
| `main.jsx` | `BrowserRouter` + `AppStateProvider` |
| `api.js` | Thin `fetch` wrapper — **unchanged endpoint contract** |
| `state/AppStateContext.jsx` | Single source of truth: health, memory probe, current incident, analysis, resolution, history, demo step, and every API call |
| `lib/constants.js` | Demo presets, nav items, empty form shapes |
| `lib/format.js` | `memoryVerdict()` (the recalled / none / unavailable / idle signal) + formatters |
| `components/AppShell.jsx` | Sidebar nav, topbar, and the **Hindsight Connected** status pill |
| `components/MemoryVerdict.jsx` | The first-vs-second incident banner (amber *No Memory* vs purple *Memory Recalled*) |
| `components/MemoryCard.jsx` | One recalled memory: previous incident, root cause, resolution, outcome, why relevant, retrieval scores |
| `components/DemoControls.jsx` | Demo buttons + the numbered learning-loop rail |
| `components/ActionList.jsx` | Ranked actions tagged `from Hindsight memory` / `general knowledge` |
| `components/IncidentTable.jsx` | History table; a row click loads that incident without an extra API call |
| `components/ui.jsx` | `Card`, `Pill`, `Alert`, `StatCard`, `EmptyState`, `KeyValue`, inline icons |
| `screens/LandingScreen.jsx` | `/` — pitch, live memory status, **Enter Dashboard** (no auth) |
| `screens/DashboardScreen.jsx` | `/dashboard` — stats, memory health, demo controls, history |
| `screens/ReportIncidentScreen.jsx` | `/report` — incident capture + demo prefills |
| `screens/AnalysisScreen.jsx` | `/analysis` — memory verdict, Groq analysis, action plan |
| `screens/MemoryRecallScreen.jsx` | `/memory` — the recalled experience, in full |
| `screens/ResolveScreen.jsx` | `/resolve` — record the fix, confirm the Hindsight write |

**Preserved contract.** `api.js` is byte-for-byte unchanged, and `AppStateContext` issues the
same requests with the same payload shapes as the original single-page dashboard
(`analyze`, `resolve`, `reset`, `health`, `memory/status`, `incidents`). Only presentation and
navigation changed. `vite.config.js` still proxies `/api/*` to `127.0.0.1:8000`, so the frontend
needs no CORS or host configuration.

---

## 7. Deliberate non-goals (hackathon scope)

No authentication, no Kubernetes, no monitoring stack, no multi-tenant isolation, no database
server. Adding them would not make the memory loop more convincing — and the memory loop is the
demo.
