# MemoryOps — AI Incident Response Agent

**An incident-response assistant that actually remembers.** MemoryOps recalls previous
production incidents from **[Hindsight by Vectorize](https://hindsight.vectorize.io)** and
turns them into specific, experience-based recommendations — instead of generic advice.

> The second time the Payment API returns HTTP 503, MemoryOps already knows the answer:
> *"Last time this exact symptom on this exact service was database connection pool
> exhaustion, and raising the pool from 50 to 100 fixed it. Do that first."*

---

## The problem

Every on-call rotation relearns the same lessons. The postmortem gets written, filed, and
forgotten. A month later a different engineer sees the same symptom and starts from scratch:

- Runbooks are static and generic — they cannot say *"this service, this symptom, this fix."*
- Vector RAG over documents finds **similar text**, not **similar incidents and what fixed them**.
- Chat assistants have no durable memory of what actually happened in your environment.

## The solution

MemoryOps closes the loop:

1. An engineer reports an incident (service + symptom + details).
2. The agent **recalls real memories from Hindsight** for that service and symptom.
3. Groq reasons over the live incident **plus those recalled experiences**.
4. Every recommendation is tagged `hindsight_memory` or `general_knowledge`, so you can see
   exactly when experience — not guesswork — drove the answer.
5. When the engineer resolves the incident, the **complete experience** (root cause, fix,
   outcome) is written back into Hindsight.
6. The next similar incident retrieves that experience and gets a **specific** answer.

The agent gets better with every resolved incident. Nothing is hard-coded and nothing is
faked: if Hindsight is unavailable, the UI says so.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│ React + Vite dashboard (port 5173)                                   │
│  New Incident · Analysis · Hindsight Memory · Actions · Resolve ·    │
│  History · Demo Mode                                                 │
└───────────────────────────┬──────────────────────────────────────────┘
                            │  /api/*  (Vite dev proxy)
┌───────────────────────────▼──────────────────────────────────────────┐
│ FastAPI backend (port 8000)                                          │
│                                                                      │
│  main.py             HTTP endpoints + CORS                           │
│  agent.py            the agent: recall → reason → explain            │
│  incident_service.py orchestration + demo ledger                     │
│  hindsight_client.py Hindsight by Vectorize (memory)   ◄── LEARNING  │
│  llm.py              Groq reasoning over incident + memories         │
│  prompts.py          prompt contracts (no-memory is explicit)        │
│  models.py           Pydantic request/response models                │
│  config.py           env-driven settings (no hard-coded secrets)     │
└────────┬───────────────────────────────────┬─────────────────────────┘
         │                                   │
┌────────▼───────────────┐        ┌──────────▼───────────────────────┐
│ Hindsight by Vectorize │        │ Groq                             │
│ retain / recall /      │        │ openai/gpt-oss-120b              │
│ observations           │        │ structured JSON analysis         │
└────────────────────────┘        └──────────────────────────────────┘
         │
┌────────▼─────────────────────────────────────────────────────────────┐
│ data/incidents.json — DEMO LEDGER ONLY (incident metadata)           │
└──────────────────────────────────────────────────────────────────────┘
```

Full breakdown: [`docs/architecture.md`](docs/architecture.md).

---

## How Hindsight is used

[`backend/app/hindsight_client.py`](backend/app/hindsight_client.py) is the memory layer. It
calls the real Hindsight HTTP API (verified against **Hindsight HTTP API 0.10.2**):

| Operation | Call | Purpose |
|---|---|---|
| Create/update bank | `PUT /v1/default/banks/{bank_id}` | Idempotent bank setup + incident-response mission |
| **Retain** (learn) | `POST /v1/default/banks/{bank_id}/memories` | Store the resolved incident experience |
| **Recall** (remember) | `POST /v1/default/banks/{bank_id}/memories/recall` | Multi-strategy search for similar incidents |

Authentication is `Authorization: Bearer $HINDSIGHT_API_KEY`.

**Why Hindsight rather than a vector store + RAG?** Hindsight does not hand back raw text
chunks. It extracts **structured facts and experiences** from the retained postmortem —
separating the symptom from the root cause from the resolution — and recalls them with four
fused strategies (semantic, keyword/BM25, graph traversal, temporal). That is precisely why
MemoryOps can display *"previous root cause"* and *"previous resolution"* as distinct fields
instead of dumping a paragraph of similar-looking text.

The integration:

- Creates a bank with `enable_observations=True`, so Hindsight can also synthesise
  cross-incident patterns over time.
- Retains with `async=False`, so extraction has completed before the response returns and the
  memory is **immediately** recallable by the next demo step.
- Stores structured metadata (`incident_id`, `service`, `symptom`, `root_cause`,
  `resolution`, `outcome`) alongside the memory, so a recalled fact maps back to the exact
  previous incident.
- Uses the official `hindsight-client` SDK when installed and falls back to raw `httpx` REST
  calls against the same documented endpoints.

Details: [`docs/hindsight-memory.md`](docs/hindsight-memory.md).

---

## How the agent learns from incidents

```
Incident #1  ──► recall → (nothing relevant)  ──► general guidance   (memory_used = false)
     │
     └─ resolve: root cause + fix + outcome
              │
              └─► retain ──► Hindsight extracts: "Payment API 503 ← db pool exhaustion
                                              ← pool 50→100 ← recovered"

Incident #2  ──► recall → MATCH ──► Groq recommends the remembered fix   (memory_used = true)
```

On resolution the service renders the postmortem as a labelled document and retains it:

```
POST-INCIDENT EXPERIENCE REPORT
Incident ID: INC-001
Service: Payment API
Symptom: HTTP 503 errors
Root cause: Database connection pool exhaustion
Resolution applied: Increased database connection pool from 50 to 100
Outcome: Payment API recovered and error rate returned to normal
Outcome status: resolved
```

Hindsight turns that into durable, queryable memory. The recall query for the next incident is:

> *"Production incident on the Payment API with the symptom: HTTP 503 errors. What was the
> root cause, the resolution that fixed it, and the outcome of previous similar incidents on
> this service?"*

---

## Configuration

All secrets come from the environment. Nothing is hard-coded.

1. **Groq API key** — https://console.groq.com/keys
2. **Hindsight API key** — https://hindsight.vectorize.io (keys look like `hsk_...`)

```powershell
Copy-Item backend/.env.example backend/.env
```

Then edit `backend/.env`:

```ini
GROQ_API_KEY=your-groq-key
GROQ_MODEL=openai/gpt-oss-120b

HINDSIGHT_API_KEY=hsk_your-hindsight-key
HINDSIGHT_URL=https://api.hindsight.vectorize.io
```

`HINDSIGHT_API_URL` / `HINDSIGHT_API_KEY` are accepted aliases (the names the official
Hindsight CLI uses), and a self-hosted server works too:

```ini
HINDSIGHT_URL=http://localhost:8888
HINDSIGHT_API_KEY=
```

### Optional settings

| Variable | Default | Meaning |
|---|---|---|
| `HINDSIGHT_BANK_ID` | `memoryops-incidents` | Memory bank holding incident experiences |
| `HINDSIGHT_RECALL_LIMIT` | `5` | Max recalled memories passed to the LLM |
| `HINDSIGHT_TIMEOUT_SECONDS` | `45` | Per-request timeout |
| `GROQ_MAX_TOKENS` | `2048` | Completion budget |
| `GROQ_TEMPERATURE` | `0.2` | Sampling temperature |
| `DATA_FILE` | `data/incidents.json` | Demo ledger path |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Allowed frontend origins |

### Running without keys (graceful degradation)

MemoryOps is deliberately honest when unconfigured:

- **No `HINDSIGHT_API_KEY`** → `memory_status.message` is
  `"Hindsight memory unavailable"`, `retrieved_memories` is `[]`, and the UI shows a red
  *Hindsight memory unavailable* banner. No memory is ever invented.
- **No `GROQ_API_KEY`** → the agent falls back to a deterministic runbook. Memory-grounded
  fallbacks keep the `hindsight_memory` label; generic ones are labelled `general_knowledge`.

---

## How to run the backend

Requires Python 3.11+.

```powershell
# from the project root
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt

Copy-Item backend\.env.example backend\.env   # then add your keys

cd backend
uvicorn app.main:app --reload --port 8000
```

- API root: http://127.0.0.1:8000
- Interactive docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/api/health

### Run the backend tests

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -v
```

The tests never touch the network — Hindsight and Groq are stubbed. Coverage:

| File | What it proves |
|---|---|
| `test_health.py` | Health endpoint, demo reset, labelled synthetic data |
| `test_analyze.py` | Recall + reasoning; general guidance when no memory exists; memory-grounded answers when it does |
| `test_resolve.py` | The experience is retained; failures report "NOT stored" instead of pretending |
| `test_memory_status.py` | `GET /api/memory/status` readiness probe |
| `test_hindsight_client.py` | Documented REST paths, prompt/document builders, unavailability and transport errors |
| `test_hindsight_rest.py` | Raw-HTTP fallback: exact URL, `Bearer` header and JSON body for retain/recall |
| `test_memory_loop.py` | **The core claim** — incident 1 finds no memory, resolve retains it, incident 2 recalls it and gets a memory-attributed recommendation |

---

## How to run the frontend

Requires Node 20+.

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The Vite dev server proxies `/api/*` to
`http://127.0.0.1:8000`, so start the backend first.

Production build:

```powershell
cd frontend
npm run build      # output in frontend/dist
npm run preview
```

---

## Demo steps

The UI is split into focused screens behind a sidebar. Open the app, land on the marketing page,
then press **Enter Dashboard**. Each demo step also advances a numbered "learning loop" rail so
the jury can see where they are.

| Route | Screen | Purpose |
|---|---|---|
| `/` | **Landing** | Pitch, live memory-layer status, `Enter Dashboard` CTA (no auth) |
| `/dashboard` | **Dashboard** | Stats, memory health, Demo Mode controls, incident history |
| `/report` | **Report Incident** | Capture service, symptom, severity, error signature |
| `/analysis` | **AI Analysis** | Memory verdict, Groq analysis, ranked action plan |
| `/memory` | **Hindsight Memory Recall** | The recalled experience, in full, with why it matched |
| `/resolve` | **Resolve & Remember** | Record root cause / fix / outcome → written into Hindsight |

The 7-step walkthrough (top of the dashboard, or **Demo Mode** on the memory screen):

| # | Action | What to point at |
|---|---|---|
| 1 | Click **Step 1 · First incident** | You are taken to **AI Analysis**; the synthetic Payment API 503 is analysed |
| 2 | Read the amber banner | **“No Memory Available”** + a *Cold start* chip — general guidance, `memory_used: false` |
| 3 | Open **Hindsight Memory** | The verifiable *no memory* state, plus the live `GET /api/memory/status` probe |
| 4 | Go to **Resolve & Remember**, click **Fill demo fix**, then **Resolve & remember** | Root cause: DB connection pool exhaustion; fix: pool 50 → 100 |
| 5 | Read the green confirmation | *Experience stored in Hindsight* + the Hindsight document id |
| 6 | Click **Now report the similar incident** (or **Step 2**) | Same service, same symptom, days later |
| 7 | Read the purple banner | **“Hindsight Memory Recalled”** — previous incident, previous root cause, previous resolution, why it matched, and the retrieval scores |
| 8 | Compare the action plans | Generic checklist → top action tagged **From Hindsight memory** naming the remembered fix |

**This is the money shot:** step 2 is amber *“No Memory Available”*, step 7 is purple
*“Hindsight Memory Recalled”*. Same service, same symptom, completely different answer — and the
only thing that changed is the memory.

To start over, click **Reset** in Demo Mode. It clears the local ledger only; the learned memory
in Hindsight survives, which is exactly the point.

---

## API reference

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Service status + configuration (never calls external services) |
| `GET` | `/api/memory/status` | Live Hindsight readiness probe |
| `GET` | `/api/incidents` | Incident history, newest first |
| `GET` | `/api/incidents/{id}` | Single incident |
| `POST` | `/api/incidents/analyze` | Recall memories → Groq analysis → persist |
| `POST` | `/api/incidents/{id}/resolve` | Store the experience in Hindsight |
| `POST` | `/api/demo/reset` | Clear the demo ledger (`?clear_hindsight=true` also clears the bank) |
| `GET` | `/api/demo/synthetic-example` | The clearly labelled synthetic demo incident |

<details>
<summary><code>POST /api/incidents/analyze</code> — request</summary>

```json
{
  "service": "Payment API",
  "symptom": "HTTP 503 errors",
  "severity": "SEV2",
  "environment": "production",
  "error_signature": "upstream connect error / connection pool timeout",
  "description": "4% of checkout requests failing under peak load."
}
```
</details>

<details>
<summary><code>POST /api/incidents/analyze</code> — response (excerpt)</summary>

```json
{
  "incident_id": "INC-002",
  "analysis": {
    "summary": "…",
    "memory_used": true,
    "memory_influence": "Hindsight recalled INC-001, where the same symptom was fixed by raising the database connection pool from 50 to 100.",
    "similar_incident_ids": ["INC-001"]
  },
  "recommended_actions": [
    {
      "action": "Raise the database connection pool from 50 to 100",
      "confidence": "high",
      "source": "hindsight_memory",
      "priority": 1,
      "based_on_memory_ids": ["a1b2…"]
    }
  ],
  "retrieved_memories": [
    {
      "id": "a1b2…",
      "text": "The Payment API returned HTTP 503 … database connection pool exhaustion …",
      "fact_type": "experience",
      "score": 0.87,
      "related_incident_id": "INC-001",
      "relevance_reason": "Hindsight matched this memory because of same affected service (Payment API); matching symptom (HTTP 503 errors). Retrieval scores: final=0.870, …",
      "demo_metadata": {
        "root_cause": "Database connection pool exhaustion",
        "resolution": "Increased database connection pool from 50 to 100"
      }
    }
  ],
  "memory_status": {
    "provider": "Hindsight by Vectorize",
    "available": true,
    "memories_found": 1,
    "message": "Hindsight recalled 1 relevant memory item(s) from bank 'memoryops-incidents'."
  },
  "llm_status": { "provider": "Groq", "used": true, "model": "openai/gpt-oss-120b" }
}
```
</details>

<details>
<summary><code>POST /api/incidents/{id}/resolve</code> — request</summary>

```json
{
  "root_cause": "Database connection pool exhaustion",
  "resolution": "Increased database connection pool from 50 to 100",
  "outcome": "Payment API recovered and error rate returned to normal",
  "outcome_status": "resolved",
  "resolved_by": "oncall@example.com",
  "time_to_resolve_minutes": 18
}
```
</details>

---

## Project layout

```
memoryops-agent/
├── backend/
│   ├── app/
│   │   ├── main.py               FastAPI app + endpoints
│   │   ├── config.py             env-driven settings
│   │   ├── models.py             Pydantic models
│   │   ├── agent.py              the agent: recall → reason → explain
│   │   ├── hindsight_client.py   Hindsight by Vectorize integration
│   │   ├── llm.py                Groq integration + deterministic fallback
│   │   ├── incident_service.py   orchestration + demo ledger
│   │   └── prompts.py            prompt contracts
│   ├── tests/                    pytest suite (health, analyze, resolve, failures)
│   ├── requirements.txt
│   └── .env.example
├── frontend/                     React + Vite + React Router dashboard
│   ├── src/
│   │   ├── App.jsx               route table
│   │   ├── main.jsx              BrowserRouter + AppStateProvider
│   │   ├── api.js                API client (unchanged endpoint contract)
│   │   ├── styles.css            design system
│   │   ├── state/
│   │   │   └── AppStateContext.jsx   all app state + API calls
│   │   ├── lib/
│   │   │   ├── constants.js      demo presets, nav, empty forms
│   │   │   └── format.js         memory verdict + formatting helpers
│   │   ├── components/
│   │   │   ├── AppShell.jsx      sidebar + topbar + Hindsight status
│   │   │   ├── MemoryVerdict.jsx first-vs-second incident banner
│   │   │   ├── MemoryCard.jsx    one recalled memory
│   │   │   ├── DemoControls.jsx  learning-loop rail + demo buttons
│   │   │   ├── ActionList.jsx    ranked actions with source labels
│   │   │   ├── IncidentTable.jsx history table
│   │   │   └── ui.jsx            Card / Pill / Alert / icons
│   │   └── screens/
│   │       ├── LandingScreen.jsx
│   │       ├── DashboardScreen.jsx
│   │       ├── ReportIncidentScreen.jsx
│   │       ├── AnalysisScreen.jsx
│   │       ├── MemoryRecallScreen.jsx
│   │       └── ResolveScreen.jsx
│   └── package.json
├── data/incidents.json           demo ledger (labelled synthetic example)
├── docs/
│   ├── architecture.md
│   ├── hindsight-memory.md
│   └── demo-script.md
└── README.md
```

---

## Demo data disclaimer

`data/incidents.json` ships with a **synthetic** Payment API 503 example, explicitly labelled
`"synthetic": true` / `"SYNTHETIC DEMO DATA — not a real incident"`. It is used only to
prefill Demo Mode. The incident list itself starts empty, so the first demo incident produces
a genuine *no-memory* result.

---

## Why Hindsight is central

Remove Hindsight and MemoryOps is just another LLM wrapper that gives the same generic advice
on the first incident and on the hundredth. **The product is the memory.**

- Hindsight **extracts structured experience** from a postmortem (root cause vs resolution vs
  outcome), which is what makes a targeted recommendation possible.
- Hindsight's **multi-strategy recall** (semantic + keyword + graph + temporal) finds
  *similar incidents*, not merely similar wording.
- Hindsight's **observations** let the bank accumulate patterns across incidents over time.
- Hindsight is **external and durable**: it survives a backend restart, a cleared UI and a
  redeployed container — exactly what production incident knowledge requires.

That learning loop — recall, reason, resolve, retain — is the entire thesis of MemoryOps.

---

## License

Apache-2.0 (Hackathon MVP).
