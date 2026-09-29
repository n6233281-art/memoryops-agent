// Incident history table. Rows are clickable and load that incident into the
// analysis / memory screens without any extra API call.

import { useNavigate } from 'react-router-dom';

import { formatDateTime, severityTone, truncate } from '../lib/format.js';
import { useAppState } from '../state/AppStateContext.jsx';
import { Icon, Pill } from './ui.jsx';

export default function IncidentTable({ incidents = [], limit }) {
  const navigate = useNavigate();
  const { selectIncident, selectedId } = useAppState();

  const rows = limit ? incidents.slice(0, limit) : incidents;

  if (rows.length === 0) {
    return (
      <p className="muted">
        No incidents recorded yet. Report one to start building Hindsight memory.
      </p>
    );
  }

  const open = (incident) => {
    selectIncident(incident);
    navigate('/analysis');
  };

  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Incident</th>
            <th>Service / symptom</th>
            <th>Severity</th>
            <th>Memory</th>
            <th>Status</th>
            <th>Recorded</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {rows.map((incident) => {
            const memories = incident.retrieved_memories ?? [];
            const unavailable = incident.memory_status?.available === false;
            const memoryTone = unavailable ? 'danger' : memories.length > 0 ? 'memory' : 'warn';
            const memoryLabel = unavailable
              ? 'unavailable'
              : memories.length > 0
                ? `${memories.length} recalled`
                : 'none found';

            return (
              <tr
                key={incident.incident_id}
                className={selectedId === incident.incident_id ? 'is-selected' : undefined}
                onClick={() => open(incident)}
              >
                <td className="mono">{incident.incident_id}</td>
                <td>
                  <strong>{incident.service}</strong>
                  <div className="table__sub">{truncate(incident.symptom, 48)}</div>
                </td>
                <td>
                  <Pill tone={severityTone(incident.severity)}>{incident.severity}</Pill>
                </td>
                <td>
                  <Pill tone={memoryTone} icon={memories.length > 0 ? 'memory' : undefined}>
                    {memoryLabel}
                  </Pill>
                </td>
                <td>
                  <Pill tone={incident.status === 'resolved' ? 'success' : 'warn'}>
                    {incident.status}
                  </Pill>
                </td>
                <td className="table__sub">{formatDateTime(incident.created_at)}</td>
                <td className="table__action">
                  <Icon name="arrowRight" size={15} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
