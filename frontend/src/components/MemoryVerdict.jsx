// The single most important visual in the demo: did Hindsight recall experience?
// The four states are deliberately unmissable and colour-coded so a jury can see
// the first incident (no memory) flip into the second incident (memory recalled).

import { MEMORY_VERDICT_COPY } from '../lib/format.js';
import { Icon, Pill } from './ui.jsx';

const VERDICT_ICON = {
  recalled: 'memory',
  none: 'alert',
  unavailable: 'plug',
  idle: 'spark',
};

export default function MemoryVerdict({ state, memories = [], memoryStatus = null, footer }) {
  const copy = MEMORY_VERDICT_COPY[state] ?? MEMORY_VERDICT_COPY.idle;
  const count = memories.length;

  return (
    <section className={`verdict verdict--${state}`}>
      <div className="verdict__icon">
        <Icon name={VERDICT_ICON[state]} size={22} />
      </div>

      <div className="verdict__main">
        <div className="verdict__headline">
          <span className="verdict__badge">
            {state === 'recalled' ? 'Hindsight Memory Recalled' : copy.label}
          </span>
          {state === 'recalled' ? (
            <Pill tone="memory">
              {count} {count === 1 ? 'memory' : 'memories'} used
            </Pill>
          ) : null}
          {state === 'none' ? <Pill tone="warn">Cold start</Pill> : null}
          {state === 'unavailable' ? <Pill tone="danger">Memory offline</Pill> : null}
        </div>
        <p className="verdict__blurb">{copy.blurb}</p>
        {footer ? <div className="verdict__footer">{footer}</div> : null}
      </div>

      {memoryStatus?.bank_id ? (
        <div className="verdict__meta">
          <span className="verdict__meta-label">Bank</span>
          <span className="mono">{memoryStatus.bank_id}</span>
          {memoryStatus.provider ? (
            <span className="verdict__meta-provider">{memoryStatus.provider}</span>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
