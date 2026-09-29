# Hackathon Demo Script — 2 to 3 minutes

**Goal:** show one thing convincingly — *MemoryOps gives a specific answer because Hindsight
remembered the previous incident.*

**Before you start**

1. Backend running: `cd backend; uvicorn app.main:app --reload --port 8000`
2. Frontend running: `cd frontend; npm run dev`
3. `backend/.env` has both `GROQ_API_KEY` and `HINDSIGHT_API_KEY`.
4. Open http://localhost:5173 — you should land on the **Landing** page and see a green
   **Hindsight Connected** pill in the top-right.
5. Optional clean slate: `POST /api/demo/reset?clear_hindsight=true`, then reload.

All incident data in this script is **synthetic**. Say that once, then move on.

---

## 0:00 — Landing page (20 s)

> "This is MemoryOps — an incident-response agent with long-term memory. Everything you're about
> to see runs against a real Hindsight bank; the status pill at the top right is a live probe of
> the memory service, not a mock."

Point at the landing page's right-hand **Memory layer** panel (provider, bank, incidents
remembered), then at the amber-vs-purple comparison cards:

> "First incident: generic advice. Second incident, same symptom: the exact fix that worked
> before. That difference is what I'm going to demonstrate."

Press **Enter Dashboard**.

---

## 0:20 — Dashboard + Demo Mode (15 s)

Point at the stat cards (incidents tracked, open, resolved, memory-assisted) and the **Memory
layer** card.

> "Five steps, left to right: Report, Analyse, Recall, Resolve, Remember. I'll use the demo
> buttons here so we move quickly — they load clearly-labelled synthetic incidents."

---

## 0:35 — Step 1: the first incident, and no memory (30 s)

Click **Step 1 · First incident**. You land on **AI Analysis** (watch the "Analyse" step on the
learning-loop rail).

> "Payment API is returning HTTP 503s in production. The agent first searches Hindsight for
> anything relevant…"

Point at the amber banner:

> "**No Memory Available** — and a *Cold start* badge. Hindsight is connected, but it has never
> seen this service and symptom, so the agent says so honestly and sets `memory_used: false`.
> What follows is a generic checklist: check the blast radius, review recent deploys, look for
> upstream saturation. Sound, but nothing an engineer doesn't already know."

Click **Open memory recall** in the sidebar and point at the **Memory layer status** card:

> "This is the live `GET /api/memory/status` probe, and this is the recall result for *this*
> incident: zero memories, bank empty. Nothing on this screen is fabricated."

**Key line:** *"This is what an assistant without memory gives you."*

---

## 1:05 — Step 2: resolve it, and teach the agent (35 s)

Go to **Resolve & Remember**. Click **Fill demo fix** (or type it):

| Field | Value |
|---|---|
| Root cause | `Database connection pool exhaustion` |
| Resolution | `Increased database connection pool from 50 to 100` |
| Outcome | `Payment API recovered and error rate returned to normal` |

Click **Resolve & remember**, then point at the green **Experience stored** card:

> "The engineer's actual fix — pool size 50 to 100 — is now written into Hindsight as a memory,
> with the root cause and the resolution attached as structured fields. Note the Hindsight
> document id and the fact that the write is confirmed, not assumed."

**Key line:** *"That's the learning step — and it happened in Hindsight, not in this app."*

---

## 1:40 — Step 3: the same incident again (35 s)

Click **Now report the similar incident** on the green card. You land back on **AI Analysis**.

> "Days later — same service, same symptom. This is the moment that matters."

Point at the **purple** banner:

> "**Hindsight Memory Recalled.** Compare that to the amber 'No Memory Available' two minutes
> ago. Same service, same symptom, same model — the only thing that changed is the memory."

Then open **Hindsight Memory** and walk the fields top to bottom, slowly:

- **Previous incident INC-001**
- **Previous root cause** — database connection pool exhaustion
- **Previous resolution** — pool raised 50 → 100
- **Previous outcome** — error rate returned to normal
- **Why Hindsight recalled this** — same affected service, matching symptom, shared terms
- **Retrieval scores** — `final`, `reranker`, `semantic`, `keyword`

> "It's not saying 'here are some similar documents'. It's saying *this exact incident happened,
> this was the cause, this fixed it* — and it shows the actual retrieval scores Hindsight
> returned, plus the memory id."

---

## 2:15 — The better recommendation (30 s)

Back on **AI Analysis**, point at **Recommended actions**:

> "Now compare. The top action is tagged **From Hindsight memory** — apply the previously
> successful fix, naming the exact change: raise the database connection pool from 50 to 100.
> The second action has nothing behind it, so it's labelled **General knowledge**. And the
> analysis card has a 'How memory changed the answer' note."

Point at the incident id / severity / status strip, and the **Similar incidents: INC-001** row.

---

## 2:45 — Close (20 s)

> "Same model, same prompt, same incident. The only difference between the generic advice at the
> start and the specific fix at the end is the memory. That's the whole product: **recall,
> reason, resolve, retain** — an agent that gets better every time your team ships a fix. And
> because it's Hindsight, that memory is durable: it survives restarts, redeploys and cleared
> browsers, exactly like the incident knowledge your team needs to keep."

---

## Backup lines and Q&A

**"Is the memory faked?"**
> Point at the API. `POST /api/incidents/analyze` returns `retrieved_memories` with real Hindsight
> memory ids, `document_id: incident-INC-001`, Hindsight's own `scores` and a `relevance_reason`.
> Open `/docs` and run it live if asked. The **Memory layer status** card on the memory screen is
> a direct `GET /api/memory/status` probe.

**"What if Hindsight is down?"**
> Clear `HINDSIGHT_API_KEY` (or use a bad key) and re-run Step 1. The banner turns **red**:
> *Hindsight Unavailable*, `retrieved_memories` is `[]`, and the agent falls back to generic
> guidance. It never pretends to remember, and the sidebar pill flips to *Hindsight Unavailable*.

**"Why not just a vector database?"**
> Vector search returns similar *text*. Hindsight returns extracted, structured *experience* —
> root cause, resolution and outcome as separate facts — plus observations synthesised across
> incidents. That structure is what lets MemoryOps say "raise the pool to 100" instead of "here's
> a paragraph that mentions connection pools."

**"How long does the demo take?"**
> About 2–3 minutes. The only waits are the Hindsight recall/retain calls and the Groq completion
> — a few seconds each.

**If something stalls:** the sidebar has a **Refresh** button (re-probes health, memory and
history). If you need a clean slate, click **Reset** in Demo Mode and run Step 1 → resolve →
similar incident again. The reset clears the local ledger but *keeps* Hindsight memory, so the
second incident will still find `INC-001` — a nice point to make about durable memory.
