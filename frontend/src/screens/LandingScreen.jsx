// Landing screen — public entry point. No authentication, just the story and
// a live status read-out so the jury can see the memory layer is really wired up.

import { Link, useNavigate } from 'react-router-dom';

import { HindsightStatus } from '../components/AppShell.jsx';
import { Icon, Pill } from '../components/ui.jsx';
import { useAppState } from '../state/AppStateContext.jsx';

const LOOP = [
  { icon: 'memory', title: 'Recall', text: 'Search Hindsight for similar past incidents.' },
  { icon: 'spark', title: 'Reason', text: 'Groq triages the incident using that experience.' },
  { icon: 'check', title: 'Resolve', text: 'Engineers record the root cause and the fix.' },
  { icon: 'database', title: 'Retain', text: 'The experience is written back into Hindsight.' },
];

const FEATURES = [
  {
    icon: 'memory',
    title: 'Real long-term memory',
    text: 'Memory is served by Hindsight by Vectorize — structured experiences, not a pile of similar-looking text.',
  },
  {
    icon: 'bolt',
    title: 'Memory-first reasoning',
    text: 'Groq reasons over the live incident plus recalled experiences, and every action is labelled with its source.',
  },
  {
    icon: 'shield',
    title: 'Honest by design',
    text: 'If Hindsight is unavailable the agent says so. It never invents a memory it did not retrieve.',
  },
];

export default function LandingScreen() {
  const navigate = useNavigate();
  const { health, hindsightConnected, hindsightConfigured, probeStatus, stats } = useAppState();

  return (
    <div className="landing">
      <header className="landing__nav">
        <div className="landing__brand">
          <span className="sidebar__mark">MO</span>
          <span className="landing__brand-text">
            <strong>MemoryOps</strong>
            <small>AI Incident Response Agent</small>
          </span>
        </div>
        <div className="landing__nav-right">
          <HindsightStatus connected={hindsightConnected} configured={hindsightConfigured} />
          <button type="button" className="btn btn--primary" onClick={() => navigate('/dashboard')}>
            Enter Dashboard
            <Icon name="arrowRight" size={16} />
          </button>
        </div>
      </header>

      <section className="hero">
        <div className="hero__copy">
          <Pill tone="memory" icon="memory">
            Hindsight by Vectorize · Memory-powered
          </Pill>
          <h1>
            Incident response that
            <span className="hero__accent"> remembers what fixed it last time</span>
          </h1>
          <p className="hero__lead">
            MemoryOps is an on-call assistant with durable memory of your production incidents.
            Report a 503, resolve it, and the next time the same symptom appears the agent
            recommends the fix that already worked — citing the previous incident it learned from.
          </p>

          <div className="hero__cta">
            <button
              type="button"
              className="btn btn--primary btn--lg"
              onClick={() => navigate('/dashboard')}
            >
              Enter Dashboard
              <Icon name="arrowRight" size={17} />
            </button>
            <Link className="btn btn--ghost btn--lg" to="/memory">
              Explore the memory
            </Link>
          </div>

          <p className="hero__note">
            No sign-up, no authentication. All incident data in this build is synthetic.
          </p>
        </div>

        <aside className="hero__panel">
          <div className="hero__panel-head">
            <span className="hero__panel-title">Memory layer</span>
            <HindsightStatus connected={hindsightConnected} configured={hindsightConfigured} />
          </div>
          <ul className="status-list">
            <li>
              <span>Provider</span>
              <strong>{probeStatus?.provider ?? 'Hindsight by Vectorize'}</strong>
            </li>
            <li>
              <span>Bank</span>
              <strong className="mono">{health?.hindsight_bank_id ?? '—'}</strong>
            </li>
            <li>
              <span>Remembered incidents</span>
              <strong>{stats.recalled}</strong>
            </li>
            <li>
              <span>Incidents tracked</span>
              <strong>{stats.total}</strong>
            </li>
            <li>
              <span>Reasoning model</span>
              <strong className="mono">{health?.groq_model ?? '—'}</strong>
            </li>
          </ul>
          {probeStatus?.message ? (
            <p className="hero__panel-message">{probeStatus.message}</p>
          ) : null}
          {probeStatus?.error ? (
            <p className="hero__panel-error mono">{probeStatus.error}</p>
          ) : null}
        </aside>
      </section>

      <section className="compare">
        <article className="compare__col compare__col--before">
          <span className="compare__tag">First incident · no memory</span>
          <h3>Generic troubleshooting</h3>
          <ul>
            <li>Check the blast radius</li>
            <li>Review recent deployments</li>
            <li>Inspect upstream dependencies</li>
          </ul>
          <p className="compare__verdict">
            Sound advice — but nothing your team didn’t already know.
          </p>
        </article>

        <article className="compare__col compare__col--after">
          <span className="compare__tag">Second incident · memory recalled</span>
          <h3>“Raise the DB connection pool from 50 to 100”</h3>
          <ul>
            <li>Previous root cause: DB connection pool exhaustion</li>
            <li>Previous fix: pool raised 50 → 100</li>
            <li>Outcome: error rate returned to normal</li>
          </ul>
          <p className="compare__verdict">
            Labelled <strong>from Hindsight memory</strong>, with the incident it came from.
          </p>
        </article>
      </section>

      <section className="loop">
        {LOOP.map((step, index) => (
          <div className="loop__step" key={step.title}>
            <span className="loop__index">{index + 1}</span>
            <Icon name={step.icon} size={18} />
            <strong>{step.title}</strong>
            <p>{step.text}</p>
          </div>
        ))}
      </section>

      <section className="features">
        {FEATURES.map((feature) => (
          <article className="feature" key={feature.title}>
            <span className="feature__icon">
              <Icon name={feature.icon} size={19} />
            </span>
            <h3>{feature.title}</h3>
            <p>{feature.text}</p>
          </article>
        ))}
      </section>

      <footer className="landing__foot">
        <p>
          MemoryOps · Hackathon MVP · Memory by{' '}
          <a href="https://hindsight.vectorize.io" target="_blank" rel="noreferrer">
            Hindsight by Vectorize
          </a>{' '}
          · Reasoning by Groq
        </p>
        <Link className="btn btn--primary" to="/dashboard">
          Enter Dashboard
          <Icon name="arrowRight" size={16} />
        </Link>
      </footer>
    </div>
  );
}
