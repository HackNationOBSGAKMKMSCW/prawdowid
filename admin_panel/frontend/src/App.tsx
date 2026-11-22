import type { ReactElement } from 'react';
import { Link, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, RequireAuth, RequirePermission } from './auth/AuthContext.tsx';
import type { Feature } from './api/types.ts';
import type { Permission } from './auth/permissions.ts';
import Layout from './components/Layout.tsx';
import { EmptyState, ToastProvider } from './components/ui.tsx';
import AlertsPage from './pages/AlertsPage.tsx';
import AuditPage from './pages/AuditPage.tsx';
import CaseDetailPage from './pages/CaseDetailPage.tsx';
import CasesPage from './pages/CasesPage.tsx';
import ChecksPage from './pages/ChecksPage.tsx';
import DashboardPage from './pages/DashboardPage.tsx';
import EndUsersPage from './pages/EndUsersPage.tsx';
import RuntimeConfigPage from './pages/RuntimeConfigPage.tsx';
import TechLogsPage from './pages/TechLogsPage.tsx';
import ThresholdsPage from './pages/ThresholdsPage.tsx';
import StatsPage from './pages/StatsPage.tsx';
import GapsPage from './pages/GapsPage.tsx';
import LoginPage from './pages/LoginPage.tsx';
import ModelsPage from './pages/ModelsPage.tsx';
import RepeatedPage from './pages/RepeatedPage.tsx';
import RulesPage from './pages/RulesPage.tsx';
import SecurityPage from './pages/SecurityPage.tsx';
import SettingsPage from './pages/SettingsPage.tsx';
import SourcesPage from './pages/SourcesPage.tsx';
import UsersPage from './pages/UsersPage.tsx';

const guarded = (permission: Permission, element: ReactElement, feature?: Feature) => (
  <RequirePermission permission={permission} feature={feature}>
    {element}
  </RequirePermission>
);

export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            element={
              <RequireAuth>
                <Layout />
              </RequireAuth>
            }
          >
            <Route index element={guarded('dashboard:read', <DashboardPage />)} />
            <Route path="stats" element={guarded('dashboard:read', <StatsPage />)} />
            <Route path="alerts" element={guarded('alerts:read', <AlertsPage />)} />
            <Route path="gaps" element={guarded('clusters:read', <GapsPage />)} />
            <Route path="repeated" element={guarded('clusters:read', <RepeatedPage />, 'clusters')} />
            <Route path="security" element={guarded('security:read', <SecurityPage />, 'securityEvents')} />
            <Route path="end-users" element={guarded('endusers:read', <EndUsersPage />, 'endUsers')} />
            <Route path="logs" element={guarded('security:read', <TechLogsPage />, 'techEvents')} />
            <Route path="cases" element={guarded('cases:read', <CasesPage />, 'cases')} />
            <Route path="cases/:id" element={guarded('cases:read', <CaseDetailPage />, 'cases')} />
            <Route path="checks" element={guarded('checks:read', <ChecksPage />)} />
            <Route path="sources" element={guarded('sources:read', <SourcesPage />, 'sources')} />
            <Route path="models" element={guarded('models:read', <ModelsPage />, 'providers')} />
            <Route path="runtime" element={guarded('models:read', <RuntimeConfigPage />, 'runtimeConfig')} />
            <Route path="rules" element={guarded('rules:read', <RulesPage />, 'alertRules')} />
            <Route path="thresholds" element={guarded('rules:read', <ThresholdsPage />, 'runtimeConfig')} />
            <Route path="settings" element={guarded('settings:read', <SettingsPage />, 'channels')} />
            <Route path="users" element={guarded('users:read', <UsersPage />, 'staffUsers')} />
            <Route path="audit" element={guarded('audit:read', <AuditPage />)} />
            <Route
              path="*"
              element={
                <EmptyState title="Nie ma takiej strony" icon="info">
                  <Link to="/">Wróć do pulpitu</Link>
                </EmptyState>
              }
            />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </ToastProvider>
  );
}
