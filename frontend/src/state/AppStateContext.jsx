/* eslint-disable react-refresh/only-export-components */
// Single source of truth for the frontend.
// The API calls here are byte-for-byte the same requests the backend always
// received — this redesign only changes presentation and navigation.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import {
  analyzeIncident,
  getHealth,
  getMemoryStatus,
  listIncidents,
  resetDemo,
  resolveIncident,
} from '../api.js';
import {
  DEMO_INCIDENT,
  DEMO_SECOND_INCIDENT,
  EMPTY_INCIDENT,
  EMPTY_RESOLUTION,
} from '../lib/constants.js';
import { countRecalled, countResolved, memoryVerdict } from '../lib/format.js';

const AppStateContext = createContext(null);

export function AppStateProvider({ children }) {
  // --- connection / readiness -------------------------------------------
  const [health, setHealth] = useState(null);
  const [memoryProbe, setMemoryProbe] = useState(null);
  const [bannerError, setBannerError] = useState('');

  // --- current incident + analysis --------------------------------------
  const [form, setForm] = useState(EMPTY_INCIDENT);
  const [analysis, setAnalysis] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState('');
  const [selectedId, setSelectedId] = useState(null);

  // --- resolution --------------------------------------------------------
  const [resolution, setResolution] = useState(EMPTY_RESOLUTION);
  const [resolving, setResolving] = useState(false);
  const [resolveResult, setResolveResult] = useState(null);
  const [resolveError, setResolveError] = useState('');

  // --- history -----------------------------------------------------------
  const [incidents, setIncidents] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState('');

  // --- demo --------------------------------------------------------------
  const [demoStep, setDemoStep] = useState(0);
  const [busy, setBusy] = useState(false);

  const refreshHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const data = await listIncidents();
      setIncidents(data.incidents ?? []);
      setHistoryError('');
    } catch (error) {
      setHistoryError(error.message);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const refreshMemoryProbe = useCallback(async () => {
    try {
      setMemoryProbe(await getMemoryStatus());
    } catch {
      setMemoryProbe(null);
    }
  }, []);

  const refreshHealth = useCallback(async () => {
    try {
      setHealth(await getHealth());
      setBannerError('');
    } catch (error) {
      setBannerError(
        `Cannot reach the MemoryOps backend (${error.message}). Start it from the backend ` +
          'folder with: uvicorn app.main:app --reload',
      );
    }
  }, []);

  const refreshAll = useCallback(async () => {
    await Promise.all([refreshHealth(), refreshMemoryProbe(), refreshHistory()]);
  }, [refreshHealth, refreshMemoryProbe, refreshHistory]);

  useEffect(() => {
    refreshHealth();
    refreshMemoryProbe();
    refreshHistory();
  }, [refreshHealth, refreshMemoryProbe, refreshHistory]);

  // --- actions (identical payloads to the original frontend) -------------
  const analyzeWith = useCallback(
    async (incident, step) => {
      setAnalyzing(true);
      setAnalyzeError('');
      setResolveResult(null);
      setResolveError('');
      setDemoStep(step ?? 0);
      try {
        const result = await analyzeIncident({
          service: incident.service,
          symptom: incident.symptom,
          severity: incident.severity,
          environment: incident.environment,
          error_signature: incident.error_signature || null,
          description: incident.description || '',
        });
        setAnalysis(result);
        setSelectedId(result.incident_id);
        setResolution({ ...EMPTY_RESOLUTION });
        await Promise.all([refreshHistory(), refreshMemoryProbe()]);
        return result;
      } catch (error) {
        setAnalyzeError(error.message);
        setAnalysis(null);
        return null;
      } finally {
        setAnalyzing(false);
      }
    },
    [refreshHistory, refreshMemoryProbe],
  );

  const analyzeForm = useCallback(async () => {
    if (!form.service.trim() || !form.symptom.trim()) {
      setAnalyzeError('Service and symptom are required.');
      return null;
    }
    return analyzeWith(form, 0);
  }, [form, analyzeWith]);

  /** Demo step 1 — cold start: the bank holds nothing relevant yet. */
  const analyzeFirstDemo = useCallback(async () => {
    setForm(DEMO_INCIDENT);
    setResolution(EMPTY_RESOLUTION);
    return analyzeWith(DEMO_INCIDENT, 1);
  }, [analyzeWith]);

  /** Demo step 2 — the same symptom, now the agent should remember. */
  const analyzeSecondDemo = useCallback(async () => {
    setForm(DEMO_SECOND_INCIDENT);
    setResolution(EMPTY_RESOLUTION);
    return analyzeWith(DEMO_SECOND_INCIDENT, 5);
  }, [analyzeWith]);

  const resolveNow = useCallback(async () => {
    const incidentId = analysis?.incident_id ?? null;
    if (!incidentId) {
      setResolveError('Analyse an incident before resolving it.');
      return null;
    }
    if (
      !resolution.root_cause.trim() ||
      !resolution.resolution.trim() ||
      !resolution.outcome.trim()
    ) {
      setResolveError('Root cause, resolution and outcome are all required.');
      return null;
    }

    setResolving(true);
    setResolveError('');
    try {
      const payload = {
        root_cause: resolution.root_cause,
        resolution: resolution.resolution,
        outcome: resolution.outcome,
        outcome_status: resolution.outcome_status,
        store_in_hindsight: resolution.store_in_hindsight,
      };
      const minutes = Number(resolution.time_to_resolve_minutes);
      if (Number.isFinite(minutes) && minutes > 0) {
        payload.time_to_resolve_minutes = minutes;
      }

      const result = await resolveIncident(incidentId, payload);
      setResolveResult(result);
      setAnalysis((previous) =>
        previous ? { ...previous, incident: result.incident } : previous,
      );
      setDemoStep(result.stored_to_memory ? 4 : 3);
      await Promise.all([refreshHistory(), refreshMemoryProbe()]);
      return result;
    } catch (error) {
      setResolveError(error.message);
      return null;
    } finally {
      setResolving(false);
    }
  }, [analysis, resolution, refreshHistory, refreshMemoryProbe]);

  const resetDemoData = useCallback(async () => {
    setBusy(true);
    try {
      await resetDemo(false);
      setAnalysis(null);
      setResolveResult(null);
      setSelectedId(null);
      setForm(EMPTY_INCIDENT);
      setResolution(EMPTY_RESOLUTION);
      setDemoStep(0);
      await refreshHistory();
    } catch (error) {
      setBannerError(error.message);
    } finally {
      setBusy(false);
    }
  }, [refreshHistory]);

  const selectIncident = useCallback((incident) => {
    setSelectedId(incident.incident_id);
    setAnalysis({
      incident_id: incident.incident_id,
      incident,
      analysis: incident.analysis,
      recommended_actions: incident.recommended_actions ?? [],
      retrieved_memories: incident.retrieved_memories ?? [],
      memory_status: incident.memory_status ?? null,
      llm_status: null,
    });
    setResolveResult(null);
    setResolveError('');
    setResolution(
      incident.status === 'resolved'
        ? {
            root_cause: incident.root_cause ?? '',
            resolution: incident.resolution ?? '',
            outcome: incident.outcome ?? '',
            outcome_status: incident.outcome_status ?? 'resolved',
            time_to_resolve_minutes: incident.time_to_resolve_minutes ?? '',
            store_in_hindsight: true,
          }
        : { ...EMPTY_RESOLUTION },
    );
  }, []);

  // --- derived -----------------------------------------------------------
  const value = useMemo(() => {
    const incident = analysis?.incident ?? null;
    const memories = analysis?.retrieved_memories ?? [];
    const memoryStatus = analysis?.memory_status ?? null;
    const probeStatus = memoryProbe?.memory_status ?? null;

    return {
      // connection
      health,
      memoryProbe,
      probeStatus,
      bannerError,
      hindsightConnected: probeStatus ? Boolean(probeStatus.available) : null,
      hindsightConfigured: health ? Boolean(health.hindsight_configured) : null,
      groqConfigured: health ? Boolean(health.groq_configured) : null,

      // current incident
      form,
      setForm,
      analysis,
      incident,
      incidentId: analysis?.incident_id ?? null,
      incidentResolved: incident?.status === 'resolved',
      analyzing,
      analyzeError,

      // memory (the heart of the demo)
      memories,
      memoryStatus,
      memoryState: memoryVerdict(memoryStatus, memories),
      memoryUsed: Boolean(analysis?.analysis?.memory_used),

      // resolution
      resolution,
      setResolution,
      resolving,
      resolveResult,
      resolveError,

      // history
      incidents,
      historyLoading,
      historyError,
      selectedId,
      stats: {
        total: incidents.length,
        open: incidents.filter((item) => item.status !== 'resolved').length,
        resolved: countResolved(incidents),
        recalled: countRecalled(incidents),
      },

      // demo
      demoStep,
      demoBusy: busy || analyzing || resolving,

      // actions
      analyzeForm,
      analyzeWith,
      analyzeFirstDemo,
      analyzeSecondDemo,
      resolveNow,
      resetDemoData,
      selectIncident,
      refreshAll,
    };
  }, [
    health,
    memoryProbe,
    bannerError,
    form,
    analysis,
    analyzing,
    analyzeError,
    resolution,
    resolving,
    resolveResult,
    resolveError,
    incidents,
    historyLoading,
    historyError,
    selectedId,
    demoStep,
    busy,
    analyzeForm,
    analyzeWith,
    analyzeFirstDemo,
    analyzeSecondDemo,
    resolveNow,
    resetDemoData,
    selectIncident,
    refreshAll,
  ]);

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}

export function useAppState() {
  const context = useContext(AppStateContext);
  if (!context) {
    throw new Error('useAppState must be used inside <AppStateProvider>');
  }
  return context;
}
