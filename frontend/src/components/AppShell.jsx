// Application shell: persistent sidebar navigation + connection status top bar.

import { NavLink, Outlet, useLocation } from 'react-router-dom';

import { NAV_ITEMS } from '../lib/constants.js';
import { useAppState } from '../state/AppStateContext.jsx';
import { Icon, Pill, Spinner } from './ui.jsx';

const PAGE_TITLES = {
  '/dashboard': { title: 'Dashboard', subtitle: 'Incident overview and the memory learning loop' },
  '/report': { title: 'Report Incident', subtitle: 'Capture a new production incident for analysis' },
  '/analysis': { title: 'AI Analysis', subtitle: 'Triage, likely causes and a ranked action plan' },
  '/memory': {
    title: 'Hindsight Memory Recall',
    subtitle: 'Experience recalled from long-term memory by Hindsight',
  },
  '/resolve': { title: 'Resolve & Remember', subtitle: 'Record the fix so the agent learns from it' },
};

export function HindsightStatus({ connected, configured, compact = false }) {
  if (connected === null || connected === undefined) {
    return (
      <Pill tone="neutral">
        <Spinner />
        {compact ? '' : 'Hindsight Checking…'}
      </Pill>
    );
  }
  if (connected) {
    return (
      <Pill tone="memory" icon="memory">
        Hindsight Connected
      </Pill>
    );
  }
  return (
    <Pill tone="danger" icon="plug">
      {configured === false ? 'Hindsight Not Configured' : 'Hindsight Unavailable'}
    </Pill>
  );
}

function Sidebar() {
  const { hindsightConnected, hindsightConfigured, health, stats } = useAppState();

  return (
    <aside className="sidebar">
      <NavLink to="/" className="sidebar__brand" end>
        <span className="sidebar__mark">MO</span>
        <span className="sidebar__brand-text">
          <strong>MemoryOps</strong>
          <small>AI Incident Response</small>
        </span>
      </NavLink>

      <nav className="sidebar__nav" aria-label="Main navigation">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `nav-item${isActive ? ' nav-item--active' : ''}${item.accent ? ' nav-item--accent' : ''}`
            }
            title={item.hint}
          >
            <Icon name={item.icon} size={17} />
            <span className="nav-item__label">{item.label}</span>
            {item.to === '/memory' && stats.recalled > 0 ? (
              <span className="nav-item__badge">{stats.recalled}</span>
            ) : null}
          </NavLink>
        ))}
      </nav>

      <div className="sidebar__foot">
        <div className="sidebar__status">
          <span className="sidebar__status-title">Memory layer</span>
          <HindsightStatus
            connected={hindsightConnected}
            configured={hindsightConfigured}
            compact
          />
        </div>
        <p className="sidebar__note">
          {health?.hindsight_bank_id ? (
            <>
              Bank <span className="mono">{health.hindsight_bank_id}</span>
            </>
          ) : (
            'Memory bank unknown'
          )}
        </p>
        <p className="sidebar__disclaimer">
          Demo uses synthetic incident data. Memory is served by Hindsight by Vectorize.
        </p>
      </div>
    </aside>
  );
}

function Topbar() {
  const { health, hindsightConnected, hindsightConfigured, groqConfigured, refreshAll } =
    useAppState();
  const { pathname } = useLocation();
  const page = PAGE_TITLES[pathname] ?? {
    title: 'MemoryOps',
    subtitle: 'AI incident response with long-term memory',
  };

  return (
    <header className="topbar">
      <div className="topbar__titles">
        <h1>{page.title}</h1>
        <p>{page.subtitle}</p>
      </div>
      <div className="topbar__status">
        <HindsightStatus connected={hindsightConnected} configured={hindsightConfigured} />
        <Pill tone={groqConfigured ? 'info' : 'warn'} icon="bolt">
          {groqConfigured ? `Groq · ${health?.groq_model ?? 'ready'}` : 'Groq Not Configured'}
        </Pill>
        <button type="button" className="btn btn--ghost btn--sm" onClick={refreshAll}>
          <Icon name="refresh" size={15} />
          Refresh
        </button>
      </div>
    </header>
  );
}

export default function AppShell() {
  const { bannerError } = useAppState();

  return (
    <div className="shell">
      <Sidebar />
      <div className="shell__main">
        <Topbar />
        <main className="shell__content">
          {bannerError ? (
            <div className="alert alert--danger" role="alert">
              <p className="alert__title">Backend unreachable</p>
              <div className="alert__body">{bannerError}</div>
            </div>
          ) : null}
          <Outlet />
        </main>
      </div>
    </div>
  );
}
