// Resolve & Remember — capture the fix. This is the step that creates memory.

import { useNavigate } from 'react-router-dom';

import { Alert, Card, EmptyState, Field, Icon, Pill, Spinner } from '../components/ui.jsx';
import { DEMO_RESOLUTION, OUTCOME_STATUSES } from '../lib/constants.js';
import { useAppState } from '../state/AppStateContext.jsx';

export default function ResolveScreen() {
  const navigate = useNavigate();
  const {
    analysis,
    incident,
    resolution,
    setResolution,
    resolveNow,
    resolving,
    resolveResult,
    resolveError,
    incidentResolved,
    demoBusy,
    analyzeSecondDemo,
  } = useAppState();

  if (!analysis || !incident) {
    return (
      <div className="page">
        <Card>
          <EmptyState
            icon="check"
            title="Nothing to resolve yet"
            actions={
              <>
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={() => navigate('/report')}
                >
                  Report an incident
                  <Icon name="arrowRight" size={15} />
                </button>
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => navigate('/dashboard')}
                >
                  Back to dashboard
                </button>
              </>
            }
          >
            Analyse an incident first, then record what fixed it. The agent stores the root cause,
            the resolution and the outcome in Hindsight as durable experience.
          </EmptyState>
        </Card>
      </div>
    );
  }

  const update = (field) => (event) => setResolution({ ...resolution, [field]: event.target.value });

  const submit = async (event) => {
    event.preventDefault();
    await resolveNow();
  };

  const runSecondDemo = async () => {
    const result = await analyzeSecondDemo();
    if (result) navigate('/analysis');
  };

  return (
    <div className="page page--narrow">
      <div className="incident-head incident-head--compact">
        <div className="incident-head__id">
          <span className="mono">{analysis.incident_id}</span>
          <Pill tone={incidentResolved ? 'success' : 'warn'}>{incident.status}</Pill>
        </div>
        <div className="incident-head__what">
          <h2>{incident.service}</h2>
          <p>{incident.symptom}</p>
        </div>
      </div>

      <Card
        title="Record the resolution"
        eyebrow="Step 3 · Retain"
        icon="database"
        tone="memory"
        subtitle="Everything entered here is written into Hindsight as this incident’s experience."
        actions={
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => setResolution({ ...DEMO_RESOLUTION })}
            disabled={resolving}
          >
            <Icon name="bolt" size={14} />
            Fill demo fix
          </button>
        }
      >
        <form onSubmit={submit}>
          <Field label="Root cause" htmlFor="root_cause">
            <input
              id="root_cause"
              value={resolution.root_cause}
              onChange={update('root_cause')}
              placeholder="Database connection pool exhaustion"
              required
            />
          </Field>

          <Field
            label="Resolution"
            htmlFor="resolution"
            hint="Include exact values — the agent reuses these numbers later."
          >
            <input
              id="resolution"
              value={resolution.resolution}
              onChange={update('resolution')}
              placeholder="Increased database connection pool from 50 to 100"
              required
            />
          </Field>

          <Field label="Outcome" htmlFor="outcome">
            <input
              id="outcome"
              value={resolution.outcome}
              onChange={update('outcome')}
              placeholder="Payment API recovered and error rate returned to normal"
              required
            />
          </Field>

          <div className="field-grid">
            <Field label="Outcome status" htmlFor="outcome_status">
              <select
                id="outcome_status"
                value={resolution.outcome_status}
                onChange={update('outcome_status')}
              >
                {OUTCOME_STATUSES.map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Time to resolve (minutes)" htmlFor="time_to_resolve_minutes">
              <input
                id="time_to_resolve_minutes"
                type="number"
                min="0"
                value={resolution.time_to_resolve_minutes}
                onChange={update('time_to_resolve_minutes')}
                placeholder="18"
              />
            </Field>
          </div>

          <label className="switch">
            <input
              type="checkbox"
              checked={resolution.store_in_hindsight}
              onChange={(event) =>
                setResolution({ ...resolution, store_in_hindsight: event.target.checked })
              }
            />
            <span>
              Store this experience in Hindsight memory
              <small>Required for the agent to learn from this incident.</small>
            </span>
          </label>

          {resolveError ? (
            <Alert tone="danger" title="Could not resolve">
              {resolveError}
            </Alert>
          ) : null}

          <div className="form-foot">
            <span className="muted small">
              {incidentResolved
                ? 'Already resolved — re-submitting appends to the same memory document.'
                : 'The agent is ready to learn from this incident.'}
            </span>
            <button
              type="submit"
              className="btn btn--memory btn--lg"
              disabled={resolving || demoBusy}
            >
              {resolving ? <Spinner label="Writing to Hindsight…" /> : 'Resolve & remember'}
            </button>
          </div>
        </form>
      </Card>

      {resolveResult ? (
        <Card
          tone={resolveResult.stored_to_memory ? 'success' : 'warn'}
          title={resolveResult.stored_to_memory ? 'Experience stored' : 'Not stored'}
          eyebrow={resolveResult.incident_id}
          icon={resolveResult.stored_to_memory ? 'database' : 'alert'}
        >
          <p className="lead">{resolveResult.message}</p>

          <KeyValue
            rows={[
              { label: 'Written to memory', value: resolveResult.stored_to_memory ? 'yes' : 'no' },
              {
                label: 'Hindsight document',
                value: resolveResult.memory_document_id ?? '—',
                mono: true,
              },
              {
                label: 'Memory ids',
                value: (resolveResult.memory_ids ?? []).length
                  ? resolveResult.memory_ids.join(', ')
                  : '—',
                mono: true,
              },
              { label: 'Lesson learned', value: resolveResult.lesson || '—' },
            ]}
          />

          {resolveResult.stored_to_memory ? (
            <div className="verdict__links">
              <button
                type="button"
                className="btn btn--memory"
                onClick={runSecondDemo}
                disabled={demoBusy}
              >
                <Icon name="memory" size={15} />
                Now report the similar incident
                <span className="btn__aside">Step 2</span>
              </button>
              <button
                type="button"
                className="btn btn--ghost"
                onClick={() => navigate('/memory')}
              >
                Open Hindsight memory
              </button>
            </div>
          ) : (
            <p className="muted small">
              Nothing was written to Hindsight, so the agent has not learned from this incident.
              Check the memory status on the dashboard.
            </p>
          )}
        </Card>
      ) : null}

      <p className="footnote">
        The written memory is what the next similar incident will retrieve. Nothing is stored
        locally that the agent could “remember” on its own.
      </p>
    </div>
  );
}
