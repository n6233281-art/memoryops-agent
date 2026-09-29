// Demo Mode controls: the two-act learning loop in one click each.
// Step 1 runs an incident with an empty memory bank; Step 2 runs the same
// symptom again so the jury can watch Hindsight recall the stored fix.

import { useNavigate } from 'react-router-dom';

import { DEMO_STEPS } from '../lib/constants.js';
import { useAppState } from '../state/AppStateContext.jsx';
import { Icon, Spinner } from './ui.jsx';

export default function DemoControls({ variant = 'full', activeStep = null }) {
  const navigate = useNavigate();
  const { demoStep, demoBusy, analyzeFirstDemo, analyzeSecondDemo, resetDemoData } =
    useAppState();

  const step = activeStep ?? demoStep;

  const runFirst = async () => {
    const result = await analyzeFirstDemo();
    if (result) navigate('/analysis');
  };

  const runSecond = async () => {
    const result = await analyzeSecondDemo();
    if (result) navigate('/analysis');
  };

  const runReset = async () => {
    await resetDemoData();
    navigate('/dashboard');
  };

  return (
    <section className={`demo ${variant === 'compact' ? 'demo--compact' : ''}`.trim()}>
      <div className="demo__bar">
        <div className="demo__intro">
          <span className="demo__eyebrow">
            <Icon name="bolt" size={13} /> Demo Mode
          </span>
          <strong>The learning loop, in three clicks</strong>
          <span className="demo__hint">
            Step 1 has no memory. Resolve it. Step 2 is the same symptom — with memory.
          </span>
        </div>

        <div className="demo__actions">
          <button type="button" className="btn btn--warn" onClick={runFirst} disabled={demoBusy}>
            {demoBusy ? <Spinner /> : <Icon name="play" size={15} />}
            Step 1 · First incident <span className="btn__aside">no memory</span>
          </button>
          <button
            type="button"
            className="btn btn--memory"
            onClick={runSecond}
            disabled={demoBusy}
          >
            <Icon name="memory" size={15} />
            Step 2 · Similar incident <span className="btn__aside">uses memory</span>
          </button>
          <button
            type="button"
            className="btn btn--ghost"
            onClick={runReset}
            disabled={demoBusy}
          >
            <Icon name="refresh" size={15} />
            Reset
          </button>
        </div>
      </div>

      {variant === 'full' ? (
        <ol className="rail">
          {DEMO_STEPS.map((label, index) => {
            const index1 = index + 1;
            const status =
              step === index1 ? 'current' : step > index1 ? 'done' : 'todo';
            return (
              <li key={label} className={`rail__step rail__step--${status}`}>
                <span className="rail__dot">
                  {status === 'done' ? <Icon name="check" size={11} /> : index1}
                </span>
                <span className="rail__label">{label}</span>
              </li>
            );
          })}
        </ol>
      ) : null}
    </section>
  );
}
