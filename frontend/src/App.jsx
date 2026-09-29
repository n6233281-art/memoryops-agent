// Route table. The dashboard area shares one persistent shell (sidebar + topbar);
// the landing screen is deliberately standalone.

import { Navigate, Route, Routes } from 'react-router-dom';

import AppShell from './components/AppShell.jsx';
import AnalysisScreen from './screens/AnalysisScreen.jsx';
import DashboardScreen from './screens/DashboardScreen.jsx';
import LandingScreen from './screens/LandingScreen.jsx';
import MemoryRecallScreen from './screens/MemoryRecallScreen.jsx';
import ReportIncidentScreen from './screens/ReportIncidentScreen.jsx';
import ResolveScreen from './screens/ResolveScreen.jsx';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingScreen />} />

      <Route element={<AppShell />}>
        <Route path="/dashboard" element={<DashboardScreen />} />
        <Route path="/report" element={<ReportIncidentScreen />} />
        <Route path="/analysis" element={<AnalysisScreen />} />
        <Route path="/memory" element={<MemoryRecallScreen />} />
        <Route path="/resolve" element={<ResolveScreen />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
