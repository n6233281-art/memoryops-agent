// One recalled memory, rendered as the structured experience it represents.
// Values shown here come straight from Hindsight (metadata + text + scores).

import { formatDateTime, formatScore } from '../lib/format.js';
import { Icon, KeyValue, Pill } from './ui.jsx';

const FIELDS = [
  ['Previous service', 'service'],
  ['Previous symptom', 'symptom'],
  ['Previous root cause', 'root_cause'],
  ['Previous resolution', 'resolution'],
  ['Previous outcome', 'outcome'],
];

export default function MemoryCard({ memory, index = 0 }) {
  const meta = memory.demo_metadata ?? {};
  const incidentId = meta.incident_id ?? memory.related_incident_id ?? null;
  const score = formatScore(memory.score || memory.scores?.final);

  const rows = FIELDS.map(([label, key]) => ({
    label,
    value: meta[key] || 'not provided by Hindsight',
  }));

  rows.push({
    label: 'Recalled at',
    value: formatDateTime(memory.mentioned_at),
  });
  if (memory.context) rows.push({ label: 'Context', value: memory.context });
  rows.push({ label: 'Memory ID', value: memory.id, mono: true });
  if (memory.document_id) {
    rows.push({ label: 'Source document', value: memory.document_id, mono: true });
  }

  const scoreChips = ['final', 'reranker', 'semantic', 'keyword']
    .map((name) => {
      const value = formatScore(memory.scores?.[name]);
      return value === null ? null : `${name} ${value}`;
    })
    .filter(Boolean);

  return (
    <article className="memory-card">
      <header className="memory-card__head">
        <div className="memory-card__title">
          <span className="memory-card__index">{index + 1}</span>
          <div>
            <h3>
              {incidentId ? `Previous incident ${incidentId}` : 'Previous experience'}
            </h3>
            <p className="memory-card__type">
              Extracted by Hindsight as a <strong>{memory.fact_type ?? 'fact'}</strong>
            </p>
          </div>
        </div>
        <div className="memory-card__chips">
          {score !== null ? <Pill tone="memory">relevance {score}</Pill> : null}
        </div>
      </header>

      <blockquote className="memory-card__quote">“{memory.text}”</blockquote>

      <KeyValue rows={rows} />

      {memory.relevance_reason ? (
        <div className="why-box">
          <span className="why-box__label">
            <Icon name="link" size={14} /> Why Hindsight recalled this
          </span>
          <p>{memory.relevance_reason}</p>
        </div>
      ) : null}

      {(scoreChips.length > 0 || (memory.entities ?? []).length > 0) && (
        <div className="memory-card__chips memory-card__chips--bottom">
          {scoreChips.map((chip) => (
            <span className="chip chip--mono" key={chip}>
              {chip}
            </span>
          ))}
          {(memory.entities ?? []).slice(0, 5).map((entity) => (
            <span className="chip" key={entity}>
              {entity}
            </span>
          ))}
        </div>
      )}
    </article>
  );
}
