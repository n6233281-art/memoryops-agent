// Dashboard — the command centre: memory health, the demo loop, and history.

import { Link } from 'react-router-dom';

import DemoControls from '../components/DemoControls.jsx';
import IncidentTable from '../components/IncidentTable.jsx';
import MemoryVerdict from '../components/MemoryVerdict.jsx';
import { Alert, Card, Icon, KeyValue, Pill, StatCard } from '../components/ui.jsx';
import { formatDateTime } from '../lib/format.js';
import { useAppState } from '../state/AppStateContext.jsx';

export default function DashboardScreen() {
  const {
    health,
    probeStatus,
    stats,
    incidents,
    historyLoading,
    historyError,
    analysis,
    incident,
    memoryState,
    memories,
    memoryStatus,
    memoryUsed,
  } = useAppState();

  return (
    <div className="page">
      <section className="stats">
        <StatCard label="Incidents tracked" value={stats.total} icon="book" tone="info" />
        <StatCard label="Open" value={stats.open} icon="alert" tone="warn" />
        <StatCard label="Resolved" value={stats.resolved} icon="check" tone="success" />
        <StatCard
          label="Memory-assisted"
          value={stats.recalled}
          hint="Incidents where Hindsight returned experience"
          icon="memory"
          tone="memory"
        />
      </section>

      <div className="columns">
        <Card
          title="Memory layer"
          eyebrow="Hindsight by Vectorize"
          icon="memory"
          tone="memory"
          actions={
            <Pill tone={probeStatus?.available ? 'memory' : 'danger'}>
              {probeStatus?.available ? 'connected' : 'unavailable'}
            </Pill>
          }
        >
          <KeyValue
            rows={[
              { label: 'Provider', value: probeStatus?.provider ?? 'Hindsight by Vectorize' },
              { label: 'Bank', value: health?.hindsight_bank_id ?? '—', mono: true },
              { label: 'Endpoint', value: health?.hindsight_url ?? probeStatus?.endpoint ?? '—', mono: true },
              { label: 'Memories found', value: probeStatus?.memories_found ?? 0 },
              { label: 'Reasoning model', value: health?.groq_model ?? '—', mono: true },
            ]}
          />
          {probeStatus?.message ? (
            <p className="callout callout--memory">{probeStatus.message}</p>
          ) : null}
          {probeStatus?.error ? (
            <Alert tone="danger" title="Hindsight unavailable">
              <span className="mono">{probeStatus.error}</span>
            </Alert>
          ) : null}
        </Card>

        <Card
          title="Latest analysis"
          eyebrow={incident ? incident.incident_id : 'no incident yet'}
          icon="spark"
          actions={
            analysis ? (
              <Link className="btn btn--ghost btn--sm" to="/analysis">
                Open analysis
                <Icon name="arrowRight" size={14} />
              </Link>
            ) : (
              <Link className="btn btn--primary btn--sm" to="/report">
                Report incident
              </Link>
            )
          }
        >
          {analysis ? (
            <>
              <MemoryVerdict state={memoryState} memories={memories} memoryStatus={memoryStatus} />
              <KeyValue
                rows={[
                  { label: 'Service', value: incident?.service ?? '—' },
                  { label: 'Symptom', value: incident?.symptom ?? '—' },
                  { label: 'Analysed', value: formatDateTime(analysis.created_at) },
                  { label: 'Status', value: incident?.status ?? '—' },
                  {
                    label: 'Memory used',
                    value: memoryUsed ? 'yes — experience applied' : 'no — general guidance',
                  },
                ]}
              />
            </>
          ) : (
            <p className="muted">
              No analysis yet. Use <strong>Step 1</strong> below to run the first demo incident,
              or report your own.
            </p>
          )}
        </Card>
      </div>

      <DemoControls variant="full" />

      <Card
        title="Incident history"
        eyebrow={`${stats.total} recorded`}
        icon="book"
        actions={
          <span className="muted small">Click a row to open its analysis and memories</span>
        }
      >
        {historyError ? (
          <Alert tone="danger" title="Could not load history">
            {historyError}
          </Alert>
        ) : null}
        {historyLoading && incidents.length === 0 ? (
          <p className="muted">Loading incident history…</p>
        ) : (
          <IncidentTable incidents={incidents} limit={8} />
        )}
      </Card>

      <p className="footnote">
        Incident metadata is stored in <span className="mono">data/incidents.json</span> for the
        demo dashboard. The agent’s learned experience lives in Hindsight, not in this app.
      </p>
    </div>
  );
}
