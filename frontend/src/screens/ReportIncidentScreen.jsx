// Report Incident — capture the details, then hand off to the analysis screen.

import { useNavigate } from 'react-router-dom';

import { Alert, Card, Field, Icon, Pill, Spinner } from '../components/ui.jsx';
import { DEMO_INCIDENT, DEMO_SECOND_INCIDENT, ENVIRONMENTS, SEVERITIES } from '../lib/constants.js';
import { useAppState } from '../state/AppStateContext.jsx';

export default function ReportIncidentScreen() {
  const navigate = useNavigate();
  const { form, setForm, analyzeForm, analyzing, analyzeError, demoBusy } = useAppState();

  const update = (field) => (event) => setForm({ ...form, [field]: event.target.value });

  const prefill = (preset) => setForm(preset);

  const submit = async (event) => {
    event.preventDefault();
    const result = await analyzeForm();
    if (result) navigate('/analysis');
  };

  return (
    <div className="page page--narrow">
      <Card
        title="New incident"
        eyebrow="Step 1 · Report"
        icon="alert"
        subtitle="The agent will search Hindsight for similar past incidents before it answers."
        actions={
          <>
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() => prefill(DEMO_INCIDENT)}
            >
              <Icon name="bolt" size={14} />
              Fill demo incident
            </button>
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() => prefill(DEMO_SECOND_INCIDENT)}
            >
              Fill demo #2
            </button>
          </>
        }
      >
        <form onSubmit={submit}>
          <div className="field-grid">
            <Field label="Service" htmlFor="service">
              <input
                id="service"
                value={form.service}
                onChange={update('service')}
                placeholder="Payment API"
                required
              />
            </Field>

            <Field label="Symptom" htmlFor="symptom">
              <input
                id="symptom"
                value={form.symptom}
                onChange={update('symptom')}
                placeholder="HTTP 503 errors"
                required
              />
            </Field>

            <Field label="Severity" htmlFor="severity">
              <select id="severity" value={form.severity} onChange={update('severity')}>
                {SEVERITIES.map((severity) => (
                  <option key={severity} value={severity}>
                    {severity}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Environment" htmlFor="environment">
              <select id="environment" value={form.environment} onChange={update('environment')}>
                {ENVIRONMENTS.map((environment) => (
                  <option key={environment} value={environment}>
                    {environment}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          <Field
            label="Error signature"
            htmlFor="error_signature"
            hint="Optional. Helps Hindsight match the failure mode."
          >
            <input
              id="error_signature"
              value={form.error_signature}
              onChange={update('error_signature')}
              placeholder="upstream connect error / connection pool timeout"
            />
          </Field>

          <Field label="What is happening" htmlFor="description">
            <textarea
              id="description"
              value={form.description}
              onChange={update('description')}
              rows={4}
              placeholder="When it started, what changed recently, who is affected…"
            />
          </Field>

          {analyzeError ? <Alert tone="danger" title="Analysis failed">{analyzeError}</Alert> : null}

          <div className="form-foot">
            <div className="form-foot__chips">
              <Pill tone="memory" icon="memory">
                Hindsight recall
              </Pill>
              <Icon name="arrowRight" size={15} />
              <Pill tone="info" icon="bolt">
                Groq reasoning
              </Pill>
            </div>
            <button type="submit" className="btn btn--primary btn--lg" disabled={analyzing || demoBusy}>
              {analyzing ? <Spinner label="Searching memory and analysing…" /> : 'Analyse with memory'}
            </button>
          </div>
        </form>
      </Card>

      <p className="footnote">
        Nothing is sent anywhere except your own backend. Demo presets are clearly labelled
        synthetic data.
      </p>
    </div>
  );
}
