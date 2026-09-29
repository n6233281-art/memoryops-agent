// Ranked recommended actions, each labelled with where it came from:
// Hindsight memory (experience) or general knowledge (runbook).

import { Pill } from './ui.jsx';

const CONFIDENCE_TONE = { high: 'success', medium: 'info', low: 'warn' };

export default function ActionList({ actions = [] }) {
  if (actions.length === 0) {
    return <p className="muted">No actions were produced for this incident.</p>;
  }

  return (
    <ol className="actions">
      {actions.map((action, index) => {
        const fromMemory = action.source === 'hindsight_memory';
        return (
          <li
            key={`${action.action}-${index}`}
            className={`action${fromMemory ? ' action--memory' : ''}`}
          >
            <span className="action__priority">{action.priority ?? index + 1}</span>
            <div className="action__body">
              <p className="action__title">{action.action}</p>
              {action.rationale ? <p className="action__rationale">{action.rationale}</p> : null}
              <div className="action__chips">
                <Pill tone={fromMemory ? 'memory' : 'neutral'} icon={fromMemory ? 'memory' : 'book'}>
                  {fromMemory ? 'From Hindsight memory' : 'General knowledge'}
                </Pill>
                <Pill tone={CONFIDENCE_TONE[action.confidence] ?? 'neutral'}>
                  confidence · {action.confidence}
                </Pill>
                {(action.based_on_memory_ids ?? []).map((id) => (
                  <span className="chip chip--mono" key={id} title="Recalled memory id">
                    {id}
                  </span>
                ))}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
