// Thin API client for the MemoryOps FastAPI backend.
// All routes go through the Vite dev proxy (see vite.config.js).

const JSON_HEADERS = { 'Content-Type': 'application/json' };

async function request(path, options = {}) {
  const response = await fetch(path, options);
  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { detail: text };
    }
  }
  if (!response.ok) {
    const detail = payload?.detail;
    const message =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((item) => item.msg ?? JSON.stringify(item)).join('; ')
          : `Request failed with status ${response.status}`;
    throw new Error(message);
  }
  return payload;
}

export function getHealth() {
  return request('/api/health');
}

export function getMemoryStatus() {
  return request('/api/memory/status');
}

export function getSyntheticExample() {
  return request('/api/demo/synthetic-example');
}

export function listIncidents() {
  return request('/api/incidents');
}

export function analyzeIncident(incident) {
  return request('/api/incidents/analyze', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(incident),
  });
}

export function resolveIncident(incidentId, resolution) {
  return request(`/api/incidents/${encodeURIComponent(incidentId)}/resolve`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(resolution),
  });
}

export function resetDemo(clearHindsight = false) {
  return request(`/api/demo/reset?clear_hindsight=${clearHindsight ? 'true' : 'false'}`, {
    method: 'POST',
  });
}
