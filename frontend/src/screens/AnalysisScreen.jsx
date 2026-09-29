// AI Analysis — the Groq verdict, clearly separated from the memory evidence.

import { Link } from 'react-router-dom';

import ActionList from '../components/ActionList.jsx';
import DemoControls from '../components/DemoControls.jsx';
import MemoryVerdict from '../components/MemoryVerdict.jsx';
import { Alert, Card, EmptyState, Icon, KeyValue, Pill } from '../components/ui.jsx';
import { formatDateTime, severityTone } from '../lib/format.js';
import { useAppState } from '../state/AppStateContext.jsx';

export default function AnalysisScreen() {
  const {
    analysis,
    incident,
    analyzeError,
    analyzing,
    memories,
    memoryStatus,
    memoryState,
    memoryUsed,
  } = useAppState();

  if (!analysis) {
    return (
      <div className="page">
        {analyzeError ? <Alert tone="danger" title="Analysis failed">{analyzeError}</Alert> : null}
        <Card>
          <EmptyState
            icon="spark"
            title="No analysis to show yet"
            actions={
              <>
                <Link className="btn btn--primary" to="/report">
                  Report an incident
                  <Icon name="arrowRight" size={15} />
                </Link>
                <Link className="btn btn--ghost" to="/dashboard">
                  Back to dashboard
                </Link>
              </>
            }
          >
            Report an incident (or run Demo Step 1) and the agent will search Hindsight for
            relevant experience before producing an action plan.
          </EmptyState>
        </Card>
        <DemoControls variant="compact" />
      </div>
    );
  }

  const result = analysis.analysis ?? {};
  const llm = analysis.llm_status;
  const memoryActions = (analysis.recommended_actions ?? []).filter(
    (action) => action.source === 'hindsight_memory',
  ).length;

  return (
    <div className="page">
      <div className="incident-head">
        <div className="incident-head__id">
          <span className="mono">{analysis.incident_id}</span>
          <Pill tone={severityTone(incident?.severity)}>{incident?.severity ?? 'SEV?'}</Pill>
          <Pill tone={incident?.status === 'resolved' ? 'success' : 'warn'}>
            {incident?.status ?? 'open'}
          </Pill>
        </div>
        <div className="incident-head__what">
          <h2>{incident?.service ?? 'Unknown service'}</h2>
          <p>{incident?.symptom ?? 'No symptom recorded'}</p>
        </div>
        <div className="incident-head__meta">
          <span>{formatDateTime(analysis.created_at ?? incident?.created_at)}</span>
          <span className="mono">{incident?.environment ?? '—'}</span>
        </div>
      </div>

      {analyzing ? (
        <Alert tone="info" title="Analysing…">
          Searching Hindsight for similar incidents, then reasoning with Groq.
        </Alert>
      ) : null}

      <MemoryVerdict
        state={memoryState}
        memories={memories}
        memoryStatus={memoryStatus}
        footer={
          <div className="verdict__links">
            <Link className="btn btn--memory btn--sm" to="/memory">
              <Icon name="memory" size={15} />
              {memoryState === 'recalled' ? 'View recalled memory' : 'Open memory recall'}
            </Link>
            {memoryState === 'none' ? (
              <span className="muted small">
                Resolve this incident next — that is what teaches the agent.
              </span>
            ) : null}
          </div>
        }
      />

      <div className="columns columns--analysis">
        <Card
          title="AI analysis"
          eyebrow={result.generated_by ?? 'Groq'}
          icon="spark"
          actions={
            <Pill tone={memoryUsed ? 'memory' : 'warn'}>
              {memoryUsed ? 'memory-grounded' : 'general guidance'}
            </Pill>
          }
        >
          <p className="lead">{result.summary}</p>

          {result.severity_assessment ? (
            <p className="muted">
              <strong>Urgency:</strong> {result.severity_assessment}
            </p>
          ) : null}

          {result.memory_influence ? (
            <div className={`callout callout--${memoryUsed ? 'memory' : 'warn'}`}>
              <span className="callout__label">
                <Icon name="memory" size={14} /> How memory changed the answer
              </span>
              <p>{result.memory_influence}</p>
            </div>
          ) : null}

          {(result.likely_causes ?? []).length > 0 ? (
            <div className="subsection">
              <h3>Likely causes</h3>
              <ol className="causes">
                {result.likely_causes.map((cause) => (
                  <li key={cause}>{cause}</li>
                ))}
              </ol>
            </div>
          ) : null}

          <KeyValue
            rows={[
              {
                label: 'Similar incidents',
                value: (result.similar_incident_ids ?? []).length
                  ? result.similar_incident_ids.join(', ')
                  : 'none recalled',
              },
              {
                label: 'Reasoning model',
                value: llm?.used ? llm.model : llm?.message ?? 'deterministic runbook',
              },
              {
                label: 'Memory items used',
                value: `${memories.length} recalled · ${memoryActions} action(s) from memory`,
              },
            ]}
          />
        </Card>

        <Card
          title="Recommended actions"
          eyebrow={`${(analysis.recommended_actions ?? []).length} ranked`}
          icon="check"
          tone={memoryUsed ? 'memory' : 'default'}
        >
          <ActionList actions={analysis.recommended_actions ?? []} />
        </Card>
      </div>

      <div className="next-step">
        <div>
          <strong>Next: record the fix</strong>
          <p className="muted">
            Resolving the incident writes the root cause, the fix and the outcome into Hindsight —
            that is what makes the next similar incident different.
          </p>
        </div>
        <Link className="btn btn--primary btn--lg" to="/resolve">
          Resolve &amp; Remember
          <Icon name="arrowRight" size={16} />
        </Link>
      </div>
    </div>
  );
}
