# Hindsight Memory Integration

This document describes exactly how MemoryOps uses **[Hindsight by
Vectorize](https://hindsight.vectorize.io)** — the long-term memory service that makes the
agent learn from previous incidents.

Everything here is implemented in
[`backend/app/hindsight_client.py`](../backend/app/hindsight_client.py) and verified against
**Hindsight HTTP API 0.10.2** (`hindsight-client` 0.10.2).

---

## 1. Why Hindsight and not a vector store

A vector store over postmortem documents answers *"which documents look like this text?"*.
Hindsight answers *"which incidents were like this one, what caused them, and what fixed
them?"* The difference matters:

| | Vector RAG over documents | Hindsight by Vectorize |
|---|---|---|
| Unit of storage | Raw text chunk | Extracted **fact / experience / observation** |
| Retrieval | Semantic similarity | **Four fused strategies**: semantic, keyword (BM25), graph traversal, temporal |
| Structure | None — you re-parse prose | `root cause`, `resolution`, `outcome` come back as separate fields |
| Cross-incident knowledge | None | **Observations** synthesise patterns across incidents |
| Relevance signal | Cosine distance | `final`, `reranker`, `semantic`, `keyword` scores |

For an incident-response agent, "the fix that worked last time" must be a first-class,
retrievable fact — not a paragraph you hope the model notices.

---

## 2. The bank

| Setting | Value |
|---|---|
| Bank id | `$HINDSIGHT_BANK_ID` (default `memoryops-incidents`) |
| Name | `MemoryOps — Incident Response` |
| `background` | Explains that the bank stores post-incident experiences (service, symptom, root cause, resolution, outcome) for an on-call team |
| `retain_mission` | Steers extraction toward durable incident facts and *preserving numeric before/after values* (e.g. pool 50 → 100) |
| `enable_observations` | `true` — lets Hindsight synthesise cross-incident patterns |

The bank is created with an **idempotent `PUT`**, so it is safe to call on every request:

```
PUT /v1/default/banks/{bank_id}
Authorization: Bearer <HINDSIGHT_API_KEY>
{
  "name": "MemoryOps — Incident Response",
  "background": "...",
  "retain_mission": "...",
  "enable_observations": true
}
```

`HindsightClient._bank_ready` caches success so this only happens once per process.

---

## 3. Storing an experience (the *learning* step)

`POST /api/incidents/{id}/resolve` → `HindsightClient.store_incident_experience()`

```
POST /v1/default/banks/{bank_id}/memories
Authorization: Bearer <HINDSIGHT_API_KEY>
{
  "items": [
    {
      "content": "POST-INCIDENT EXPERIENCE REPORT\nIncident ID: INC-001\n...",
      "context": "production incident postmortem",
      "document_id": "incident-INC-001",
      "metadata": {
        "incident_id": "INC-001",
        "service": "Payment API",
        "symptom": "HTTP 503 errors",
        "severity": "SEV2",
        "environment": "production",
        "root_cause": "Database connection pool exhaustion",
        "resolution": "Increased database connection pool from 50 to 100",
        "outcome": "Payment API recovered and error rate returned to normal",
        "outcome_status": "resolved",
        "resolved_at": "2026-04-01T10:05:00+00:00",
        "record_type": "incident_postmortem"
      },
      "tags": ["incident-experience", "service:payment-api", "env:production"]
    }
  ],
  "async": false
}
```

### Why the content is shaped like a postmortem

Hindsight extracts facts with an LLM, so the document is written as **labelled fields**
(`Root cause:`, `Resolution applied:`, `Outcome:`) rather than prose paragraphs. That makes the
resulting memories cleanly separable: *"the root cause was database connection pool
exhaustion"* and *"the resolution was increasing the pool from 50 to 100"* become two linked
facts instead of one blob.

### Why `async: false`

Synchronous retain blocks until Hindsight has finished extracting facts. The resolved incident
is therefore **immediately** recallable — critical for a demo where the next incident is
reported seconds later. Queueing with `async: true` would risk the second incident finding an
empty bank.

### Why metadata

`metadata` values must be strings. The `incident_id`, `root_cause`, `resolution` and `outcome`
entries let the dashboard map a recalled fact straight back to the exact previous incident, so
the **Hindsight Memory** card can show *Previous root cause* and *Previous resolution* without
guessing from free text.

---

## 4. Recalling memories (the *remembering* step)

`POST /api/incidents/analyze` → `HindsightClient.search_relevant_memories()`

```
POST /v1/default/banks/{bank_id}/memories/recall
Authorization: Bearer <HINDSIGHT_API_KEY>
{
  "query": "Production incident on the Payment API with the symptom: HTTP 503 errors. What was the root cause, the resolution that fixed it, and the outcome of previous similar incidents on this service?",
  "types": ["world", "experience", "observation"],
  "budget": "mid",
  "max_tokens": 4096,
  "include": { "entities": true }
}
```

> **Note:** recall lives at `/memories/recall`, not `/recall`. This is asserted by
> `tests/test_hindsight_client.py::test_recall_path_is_not_the_bare_recall_endpoint`, so a path
> change fails the build instead of silently returning "no memory found".

| Parameter | Value | Rationale |
|---|---|---|
| `query` | Full sentence from `build_recall_query()` | Hindsight fuses keyword + semantic retrieval, so natural language containing the service and symptom wins |
| `types` | `world`, `experience`, `observation` | `experience` carries incident events; `observation` carries cross-incident synthesis |
| `budget` | `mid` | Balanced latency/quality for an interactive dashboard |
| `max_tokens` | `4096` | Enough context for several memories without flooding the Groq prompt |
| `include.entities` | `true` | Entities are rendered as chips in the UI |

### Response handling

```json
{
  "results": [
    {
      "id": "a1b2…",
      "text": "The Payment API returned HTTP 503 … database connection pool exhaustion …",
      "type": "experience",
      "context": "production incident postmortem",
      "document_id": "incident-INC-001",
      "metadata": { "incident_id": "INC-001", "root_cause": "…", "resolution": "…" },
      "entities": ["Payment API", "database connection pool"],
      "mentioned_at": "2026-04-01T10:05:00Z",
      "scores": { "final": 0.87, "reranker": 0.8, "semantic": 0.75, "keyword": 6.1 }
    }
  ]
}
```

`_to_hit()` converts each result into a `MemoryHit`, and the list is capped at
`HINDSIGHT_RECALL_LIMIT` (default 5).

---

## 5. Explaining relevance

The dashboard must answer *"why is this memory relevant?"* — honestly.
`_relevance_reason()` builds the explanation **from real data only**:

1. **Same affected service** — if the remembered `metadata.service` also appears in the recall
   query.
2. **Matching symptom** — if terms from the remembered `metadata.symptom` appear in the query.
3. **Shared incident signals** — the actual overlapping significant terms (stopwords removed).
4. **Retrieval scores** — the real Hindsight scores (`final`, `reranker`, `semantic`, `keyword`).

Example output:

> Hindsight matched this memory because of same affected service (Payment API); matching
> symptom (HTTP 503 errors); shared incident signals: checkout, failing, peak.
> Retrieval scores: final=0.870, reranker=0.800, semantic=0.750, keyword=6.100.

If none of those hold, it falls back to *"Hindsight ranked this memory as the closest match to
the current incident."* — no invented justification.

---

## 6. Honest status reporting

Every memory operation returns a `MemoryStatus`, which the UI renders verbatim.

| Situation | `available` | `memories_found` | `message` |
|---|---|---|---|
| No API key | `false` | `0` | `Hindsight memory unavailable` (`error` explains `HINDSIGHT_API_KEY` is missing) |
| Transport / HTTP error | `false` | `0` | `Hindsight memory unavailable` (with the underlying error) |
| Reachable, nothing relevant | `true` | `0` | `Hindsight is reachable but bank '…' holds no relevant memory for this incident yet.` |
| Memories recalled | `true` | `n` | `Hindsight recalled n relevant memory item(s) from bank '…'.` |
| Retain succeeded | `true` | — | `Experience stored in Hindsight bank '…' (n memory item(s) extracted).` |
| Retain failed | `false` | — | `Hindsight memory unavailable — the experience was NOT stored.` |

**Design rule:** `available = false` always implies `retrieved_memories = []`. The agent never
presents a memory it did not retrieve, and `IncidentResponseAgent.investigate()` additionally
downgrades any LLM action that claims a memory id which was not actually recalled.

---

## 7. Transports

`HindsightClient` tries two transports, in order:

1. **Official SDK** — `from hindsight_client import Hindsight`,
   `Hindsight(base_url=…, api_key=…)`, using the native async methods `acreate_bank`,
   `aretain`, `arecall`. Used whenever `hindsight-client` is importable.
2. **Raw REST** — `httpx` calls to the documented endpoints above, so the integration still
   works if the SDK is unavailable or pinned differently.

Both paths produce identical `MemoryHit` / `MemoryStatus` objects, so nothing downstream cares
which one ran. `tests/test_hindsight_rest.py` exercises transport 2 with a fake
`httpx.AsyncClient` and asserts the exact URL, `Authorization: Bearer` header and JSON body.

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Banner: *Hindsight memory unavailable* | `HINDSIGHT_API_KEY` empty | Add the key to `backend/.env` and restart the backend |
| Banner: *Hindsight memory unavailable* and `error` mentions 401/403 | Invalid or expired key | Regenerate the key at hindsight.vectorize.io |
| *Hindsight is reachable but bank '…' holds no relevant memory yet* | Nothing retained for this service/symptom | Resolve an incident first (the *learning* step) |
| Second incident still finds no memory | The resolve step did not report `stored_to_memory: true` | Check the resolve confirmation; confirm the key and bank id |
| Recalled memory shows *not provided by Hindsight* for root cause | The memory was retained without metadata (e.g. created outside MemoryOps) | Retain through `POST /api/incidents/{id}/resolve` so metadata is attached |
| Memories accumulate during rehearsals | Hindsight is durable by design | `POST /api/demo/reset?clear_hindsight=true` to delete the bank |
