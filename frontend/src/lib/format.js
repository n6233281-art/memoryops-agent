// Small presentation helpers. No business logic, no API access.

/**
 * Derive the single most important piece of UI state in the whole demo:
 * did Hindsight actually recall a memory for the incident on screen?
 *
 *   'recalled'    -> real memories came back from Hindsight
 *   'none'        -> Hindsight reachable, but the bank holds nothing relevant
 *   'unavailable' -> Hindsight unreachable / not configured (never fake this)
 *   'idle'        -> no incident has been analysed yet
 */
export function memoryVerdict(memoryStatus, memories) {
  if (!memoryStatus || memoryStatus.available === undefined) {
    return 'idle';
  }
  if (!memoryStatus.available) {
    return 'unavailable';
  }
  return (memories ?? []).length > 0 ? 'recalled' : 'none';
}

export const MEMORY_VERDICT_COPY = {
  recalled: {
    label: 'Hindsight Memory Recalled',
    tone: 'memory',
    blurb:
      'The agent recognised this incident from previous experience and is recommending the fix that already worked.',
  },
  none: {
    label: 'No Memory Available',
    tone: 'warn',
    blurb:
      'Hindsight is connected but has no experience for this service and symptom yet, so this is general guidance only.',
  },
  unavailable: {
    label: 'Hindsight Unavailable',
    tone: 'danger',
    blurb:
      'The memory layer could not be reached, so nothing was recalled. The agent will not pretend to remember.',
  },
  idle: {
    label: 'Waiting for an incident',
    tone: 'neutral',
    blurb: 'Report an incident to search long-term memory for similar previous incidents.',
  },
};

export function formatDateTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatScore(value) {
  if (value === null || value === undefined) return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toFixed(3) : null;
}

export function truncate(value, max = 10) {
  const text = String(value ?? '');
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

export function severityTone(severity) {
  switch (severity) {
    case 'SEV1':
      return 'danger';
    case 'SEV2':
      return 'warn';
    case 'SEV3':
      return 'info';
    default:
      return 'neutral';
  }
}

/** Count incidents where Hindsight actually returned at least one memory. */
export function countRecalled(incidents) {
  return (incidents ?? []).filter(
    (incident) =>
      incident.memory_status?.available !== false &&
      (incident.retrieved_memories ?? []).length > 0,
  ).length;
}

export function countResolved(incidents) {
  return (incidents ?? []).filter((incident) => incident.status === 'resolved').length;
}
