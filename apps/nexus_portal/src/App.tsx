import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useAuthStore } from './stores/authStore';

// Layout
import AdminLayout from './layouts/AdminLayout';

// Pages
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Agents from './pages/Agents';
import TaskRoutes from './pages/TaskRoutes';
import Tasks from './pages/Tasks';
import Personas from './pages/Personas';
import PersonaDefaults from './pages/PersonaDefaults';
import KbSources from './pages/KbSources';
import KbDocuments from './pages/KbDocuments';
import KbSearch from './pages/KbSearch';
import AskNexus from './pages/AskNexus';
import Entities from './pages/Entities';
import Audits from './pages/Audits';
import IntegrationsPbx from './pages/IntegrationsPbx';
import IntegrationsMonitoring from './pages/IntegrationsMonitoring';
import IntegrationsStorage from './pages/IntegrationsStorage';
import IntegrationsCarrier from './pages/IntegrationsCarrier';
import IntegrationsEmail from './pages/IntegrationsEmail';
import IntegrationsDns from './pages/IntegrationsDns';
import InfrastructureServers from './pages/InfrastructureServers';
import MonitoringDashboard from './pages/MonitoringDashboard';
import MailboxInbox from './pages/MailboxInbox';
import Secrets from './pages/Secrets';
import Docs from './pages/Docs';
import Users from './pages/Users';
import ApiKeys from './pages/ApiKeys';
import AuditLog from './pages/AuditLog';
import IpAllowlist from './pages/IpAllowlist';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function ProtectedRoute({ children, allowedRoles }: { children: React.ReactNode, allowedRoles?: string[] }) {
  const { accessToken, user } = useAuthStore();
  const location = useLocation();

  if (!accessToken || !user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to="/" replace />;
  }

  return children;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />

          <Route path="/" element={
            <ProtectedRoute>
              <AdminLayout />
            </ProtectedRoute>
          }>
            <Route index element={<Dashboard />} />

            {/* Orchestration */}
            <Route path="agents" element={<Agents />} />
            <Route path="routes" element={<TaskRoutes />} />
            <Route path="tasks" element={<Tasks />} />

            {/* Personas */}
            <Route path="personas" element={<Personas />} />
            <Route path="personas/defaults" element={<PersonaDefaults />} />

            {/* KB */}
            <Route path="kb/sources" element={<KbSources />} />
            <Route path="kb/documents" element={<KbDocuments />} />
            <Route path="kb/search" element={<KbSearch />} />
            <Route path="kb/ask" element={<AskNexus />} />

            {/* SoR */}
            <Route path="entities" element={<Entities />} />
            <Route path="secrets" element={<Secrets />} />
            <Route path="audits" element={<Audits />} />

            {/* Integrations */}
            <Route path="integrations/pbx" element={<IntegrationsPbx />} />
            <Route path="integrations/monitoring" element={<IntegrationsMonitoring />} />
            <Route path="integrations/storage" element={<IntegrationsStorage />} />
            <Route path="integrations/carrier" element={<IntegrationsCarrier />} />
            <Route path="integrations/email" element={<IntegrationsEmail />} />
            <Route path="integrations/email/mailbox/:email" element={<MailboxInbox />} />
            <Route path="integrations/dns" element={<IntegrationsDns />} />

            {/* Infrastructure */}
            <Route path="infrastructure/servers" element={<InfrastructureServers />} />

            {/* Monitoring */}
            <Route path="monitoring/dashboard" element={<MonitoringDashboard />} />

            {/* Docs */}
            <Route path="docs" element={<Docs />} />

            {/* Settings (admin only) */}
            <Route path="settings/users" element={
              <ProtectedRoute allowedRoles={['admin']}>
                <Users />
              </ProtectedRoute>
            } />
            <Route path="settings/api-keys" element={
              <ProtectedRoute allowedRoles={['admin']}>
                <ApiKeys />
              </ProtectedRoute>
            } />
            <Route path="settings/audit-log" element={
              <ProtectedRoute allowedRoles={['admin']}>
                <AuditLog />
              </ProtectedRoute>
            } />
            <Route path="settings/ip-allowlist" element={
              <ProtectedRoute allowedRoles={['admin']}>
                <IpAllowlist />
              </ProtectedRoute>
            } />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
