// Hindsight Memory Recall — the showcase screen.
// Everything here is evidence of what Hindsight actually returned, or a plain
// statement that nothing was recalled. Nothing is simulated.

import { Link } from 'react-router-dom';

import DemoControls from '../components/DemoControls.jsx';
import MemoryCard from '../components/MemoryCard.jsx';
import MemoryVerdict from '../components/MemoryVerdict.jsx';
import { Alert, Card, EmptyState, Icon, KeyValue, Pill } from '../components/ui.jsx';
import { useAppState } from '../state/AppStateContext.jsx';

export default function MemoryRecallScreen() {
  const {
    analysis,
    incident,
    memories,
    memoryStatus,
    memoryState,
    memoryUsed,
    probeStatus,
    health,
  } = useAppState();

  const recalledCount = memories.length;

  return (
    <div className="page">
      <section className="recall-hero">
        <div className="recall-hero__copy">
          <span className="recall-hero__eyebrow">
            <Icon name="memory" size={14} /> Hindsight Memory Recall
          </span>
          <h2>
            {memoryState === 'recalled'
              ? 'The agent recognised this incident'
              : memoryState === 'none'
                ? 'No prior experience for this incident'
                : memoryState === 'unavailable'
                  ? 'Memory could not be reached'
                  : 'Long-term memory'}
          </h2>
          <p>
            {incident
              ? `${incident.service} · ${incident.symptom}`
              : 'Report an incident to search long-term memory for similar previous incidents.'}
          </p>
        </div>
        <div className="recall-hero__meta">
          <Pill tone={recalledCount > 0 ? 'memory' : 'neutral'}>
            {recalledCount} {recalledCount === 1 ? 'memory' : 'memories'} recalled
          </Pill>
          {analysis ? <Pill tone="info">{analysis.incident_id}</Pill> : null}
        </div>
      </section>

      <MemoryVerdict
        state={memoryState}
        memories={memories}
        memoryStatus={memoryStatus}
        footer={
          analysis?.analysis?.memory_influence ? (
            <div className={`callout callout--${memoryUsed ? 'memory' : 'warn'}`}>
              <span className="callout__label">
                <Icon name="link" size={14} /> What the memory changed
              </span>
              <p>{analysis.analysis.memory_influence}</p>
            </div>
          ) : null
        }
      />

      <div className="columns columns--memory">
        <div className="stack">
          {memoryState === 'recalled' ? (
            memories.map((memory, index) => (
              <MemoryCard key={memory.id || index} memory={memory} index={index} />
            ))
          ) : memoryState === 'none' ? (
            <Card tone="warn" title="Cold start" icon="alert">
              <p className="lead">
                Hindsight is connected, but the bank holds no experience for{' '}
                <strong>{incident?.service ?? 'this service'}</strong> and{' '}
                <strong>{incident?.symptom ?? 'this symptom'}</strong> yet.
              </p>
              <p className="muted">
                The agent answered with general troubleshooting guidance and set{' '}
                <span className="mono">memory_used: false</span>. Record the fix, then report the
                same symptom again — the second answer will be completely different.
              </p>
              <div className="verdict__links">
                <Link className="btn btn--primary" to="/resolve">
                  <Icon name="check" size={15} />
                  Record the fix
                </Link>
              </div>
            </Card>
          ) : memoryState === 'unavailable' ? (
            <Card tone="danger" title="No memory was retrieved" icon="plug">
              <p className="lead">{memoryStatus?.message ?? 'Hindsight memory unavailable'}</p>
              {memoryStatus?.error ? <p className="mono small">{memoryStatus.error}</p> : null}
              <Alert tone="danger" title="The agent did not pretend to remember">
                Because nothing was recalled, the recommendation on the analysis screen came from
                general knowledge and is labelled as such. Set{' '}
                <span className="mono">HINDSIGHT_API_KEY</span> in{' '}
                <span className="mono">backend/.env</span> and restart the backend.
              </Alert>
            </Card>
          ) : (
            <Card>
              <EmptyState
                icon="memory"
                title="No incident analysed yet"
                actions={
                  <Link className="btn btn--primary" to="/report">
                    Report an incident
                    <Icon name="arrowRight" size={15} />
                  </Link>
                }
              >
                Recall runs automatically as part of the analysis. Report an incident, or run the
                demo steps below to watch the memory layer switch from cold to informed.
              </EmptyState>
            </Card>
          )}
        </div>

        <div className="stack">
          <Card
            title="Memory layer status"
            eyebrow="Live probe · GET /api/memory/status"
            icon="database"
            tone="memory"
            actions={
              <Pill tone={probeStatus?.available ? 'memory' : 'danger'}>
                {probeStatus?.available ? 'Hindsight Connected' : 'Unavailable'}
              </Pill>
            }
          >
            <KeyValue
              rows={[
                { label: 'Provider', value: probeStatus?.provider ?? 'Hindsight by Vectorize' },
                {
                  label: 'Bank',
                  value: probeStatus?.bank_id ?? health?.hindsight_bank_id ?? '—',
                  mono: true,
                },
                {
                  label: 'Endpoint',
                  value: probeStatus?.endpoint ?? health?.hindsight_url ?? '—',
                  mono: true,
                },
                { label: 'Bank memories', value: probeStatus?.memories_found ?? 0 },
                { label: 'This incident', value: memoryStatus?.message ?? 'no recall has run yet' },
              ]}
            />
            {probeStatus?.error ? <p className="mono small">{probeStatus.error}</p> : null}
          </Card>

          <Card title="How recall works" icon="book">
            <ol className="facts">
              <li>
                The agent builds a natural-language query from the service, the symptom and the
                error signature.
              </li>
              <li>
                Hindsight fuses semantic, keyword, graph and temporal retrieval, then reranks the
                results.
              </li>
              <li>
                Facts come back as structured experience — root cause, resolution and outcome — and
                are shown above exactly as returned.
              </li>
              <li>
                Groq receives only those memories; every action it attributes to memory carries the
                memory id.
              </li>
            </ol>
          </Card>
        </div>
      </div>

      <DemoControls variant="full" />
    </div>
  );
}
