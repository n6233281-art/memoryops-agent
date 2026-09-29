// Small presentational primitives shared by every screen.
// Inline SVG icons keep the bundle dependency-free.

const ICON_PATHS = {
  grid: 'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z',
  alert: 'M12 3 2 20h20L12 3Zm0 6v5m0 3h.01',
  spark: 'M12 3v4m0 10v4M3 12h4m10 0h4M5.6 5.6l2.8 2.8m7.2 7.2 2.8 2.8m0-12.8-2.8 2.8M8.4 15.6l-2.8 2.8',
  memory: 'M12 3a4 4 0 0 0-4 4v1a3 3 0 0 0 0 6v1a4 4 0 0 0 8 0v-1a3 3 0 0 0 0-6V7a4 4 0 0 0-4-4Zm0 0v18',
  check: 'm5 13 4 4L19 7',
  bolt: 'M13 2 4 14h6l-1 8 9-12h-6l1-8Z',
  shield: 'M12 3 5 6v6c0 4.4 3 8 7 9 4-1 7-4.6 7-9V6l-7-3Z',
  arrowRight: 'M5 12h14m-6-6 6 6-6 6',
  refresh: 'M3 12a9 9 0 0 1 15.5-6.3M21 12a9 9 0 0 1-15.5 6.3M18 3v4h-4M6 21v-4h4',
  book: 'M4 5a2 2 0 0 1 2-2h5v17H6a2 2 0 0 0-2 2V5Zm16 0a2 2 0 0 0-2-2h-5v17h5a2 2 0 0 1 2 2V5Z',
  clock: 'M12 7v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
  database:
    'M12 3c4.4 0 8 1.3 8 3s-3.6 3-8 3-8-1.3-8-3 3.6-3 8-3Zm8 6c0 1.7-3.6 3-8 3s-8-1.3-8-3m16 6c0 1.7-3.6 3-8 3s-8-1.3-8-3M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6',
  plug: 'M9 3v6m6-6v6M6 9h12v3a6 6 0 0 1-12 0V9Zm6 9v3',
  link: 'M10 14a4 4 0 0 0 5.7 0l3-3A4 4 0 0 0 13 5.3l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3A4 4 0 0 0 11 18.7l1-1',
  plus: 'M12 5v14M5 12h14',
  play: 'M7 4.5v15l12-7.5-12-7.5Z',
};

export function Icon({ name, size = 18, className }) {
  const path = ICON_PATHS[name] ?? ICON_PATHS.bolt;
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={path} />
    </svg>
  );
}

export function Pill({ tone = 'neutral', icon, children, className = '' }) {
  return (
    <span className={`pill pill--${tone} ${className}`.trim()}>
      {icon ? <Icon name={icon} size={13} /> : <span className="pill__dot" />}
      <span>{children}</span>
    </span>
  );
}

export function Spinner({ label }) {
  return (
    <span className="spinner-wrap">
      <span className="spinner" aria-hidden="true" />
      {label ? <span>{label}</span> : null}
    </span>
  );
}

export function Alert({ tone = 'info', title, children, className = '' }) {
  return (
    <div className={`alert alert--${tone} ${className}`.trim()} role={tone === 'danger' ? 'alert' : undefined}>
      {title ? <p className="alert__title">{title}</p> : null}
      {children ? <div className="alert__body">{children}</div> : null}
    </div>
  );
}

export function Card({
  title,
  subtitle,
  eyebrow,
  icon,
  actions,
  tone = 'default',
  className = '',
  bodyClassName = '',
  children,
}) {
  return (
    <section className={`card card--${tone} ${className}`.trim()}>
      {title || actions ? (
        <header className="card__head">
          <div className="card__heading">
            {eyebrow ? <span className="card__eyebrow">{eyebrow}</span> : null}
            <h2 className="card__title">
              {icon ? <Icon name={icon} size={17} /> : null}
              {title}
            </h2>
            {subtitle ? <p className="card__subtitle">{subtitle}</p> : null}
          </div>
          {actions ? <div className="card__actions">{actions}</div> : null}
        </header>
      ) : null}
      <div className={`card__body ${bodyClassName}`.trim()}>{children}</div>
    </section>
  );
}

export function StatCard({ label, value, hint, tone = 'neutral', icon }) {
  return (
    <div className={`stat stat--${tone}`}>
      <div className="stat__top">
        <span className="stat__label">{label}</span>
        {icon ? <Icon name={icon} size={15} /> : null}
      </div>
      <div className="stat__value">{value}</div>
      {hint ? <div className="stat__hint">{hint}</div> : null}
    </div>
  );
}

export function EmptyState({ icon = 'spark', title, children, actions }) {
  return (
    <div className="empty-state">
      <span className="empty-state__icon">
        <Icon name={icon} size={20} />
      </span>
      <p className="empty-state__title">{title}</p>
      {children ? <p className="empty-state__text">{children}</p> : null}
      {actions ? <div className="empty-state__actions">{actions}</div> : null}
    </div>
  );
}

export function KeyValue({ rows }) {
  const visible = (rows ?? []).filter((row) => row && row.value !== undefined && row.value !== null);
  if (visible.length === 0) return null;
  return (
    <dl className="kv">
      {visible.map((row) => (
        <div className="kv__row" key={row.label}>
          <dt>{row.label}</dt>
          <dd className={row.mono ? 'mono' : undefined}>{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Field({ label, hint, htmlFor, children }) {
  return (
    <div className="field">
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {hint ? <span className="field__hint">{hint}</span> : null}
    </div>
  );
}
