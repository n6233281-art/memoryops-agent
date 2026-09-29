// Shared constants: demo presets, empty form states and navigation.
// These mirror the payload shape the backend expects (see backend/app/models.py).

/** Synthetic demo incident #1 — cold start, no memory exists yet. */
export const DEMO_INCIDENT = {
  service: 'Payment API',
  symptom: 'HTTP 503 errors',
  severity: 'SEV2',
  environment: 'production',
  error_signature: 'upstream connect error / connection pool timeout',
  description:
    'SYNTHETIC DEMO DATA. The Payment API started returning HTTP 503 for roughly 4% of ' +
    'checkout requests within two minutes of the evening traffic peak. No deployment had ' +
    'shipped in the previous 12 hours.',
};

/** Synthetic demo incident #2 — same service and symptom, several days later. */
export const DEMO_SECOND_INCIDENT = {
  ...DEMO_INCIDENT,
  description:
    'SYNTHETIC DEMO DATA. The Payment API is again returning HTTP 503 — this time for ' +
    'roughly 7% of checkout requests during the traffic peak. Same error signature as the ' +
    'previous incident several days ago.',
};

/** The fix the engineer records after incident #1. This is what the agent learns. */
export const DEMO_RESOLUTION = {
  root_cause: 'Database connection pool exhaustion',
  resolution: 'Increased database connection pool from 50 to 100',
  outcome: 'Payment API recovered and error rate returned to normal',
  outcome_status: 'resolved',
  time_to_resolve_minutes: 18,
  store_in_hindsight: true,
};

export const EMPTY_INCIDENT = {
  service: '',
  symptom: '',
  severity: 'SEV2',
  environment: 'production',
  error_signature: '',
  description: '',
};

export const EMPTY_RESOLUTION = {
  root_cause: '',
  resolution: '',
  outcome: '',
  outcome_status: 'resolved',
  time_to_resolve_minutes: '',
  store_in_hindsight: true,
};

export const SEVERITIES = ['SEV1', 'SEV2', 'SEV3', 'SEV4'];
export const ENVIRONMENTS = ['production', 'staging', 'development'];
export const OUTCOME_STATUSES = ['resolved', 'mitigated', 'monitoring'];

/** Sidebar navigation. `end` marks the index route so it is not matched loosely. */
export const NAV_ITEMS = [
  { to: '/dashboard', label: 'Dashboard', icon: 'grid', hint: 'Overview and demo flow' },
  { to: '/report', label: 'Report Incident', icon: 'alert', hint: 'Capture a new incident' },
  { to: '/analysis', label: 'AI Analysis', icon: 'spark', hint: 'Triage and action plan' },
  { to: '/memory', label: 'Hindsight Memory', icon: 'memory', hint: 'Recalled experience', accent: true },
  { to: '/resolve', label: 'Resolve & Remember', icon: 'check', hint: 'Store the fix' },
];

/** The seven beats of the learning loop, shown in the demo rail. */
export const DEMO_STEPS = [
  'Report the first Payment API 503 incident',
  'Hindsight finds no useful memory (general guidance only)',
  'Record the fix: connection pool exhaustion',
  'Experience stored back into Hindsight',
  'Report the second, similar incident',
  'Hindsight recalls the previous experience',
  'Review the memory-specific recommendation',
];
