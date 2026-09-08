import React from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './lib/auth'
import { useT } from './lib/i18n'
import Layout from './components/Layout'
import Login from './pages/Login'
import TasksPage from './pages/Tasks'
import ReportsPage from './pages/Reports'
import TypesPage from './pages/Types'
import TemplatesPage from './pages/Templates'
import TelegramPage from './pages/Telegram'
import BulkPage from './pages/Bulk'
import ProjectsPage from './pages/Projects'
import ProfilePage from './pages/Profile'
import StaffPage from './pages/Staff'
import AdminPage from './pages/Admin'

/** Nav item bilan bir xil ruxsat - to'g'ridan-to'g'ri manzil yozib kirishning ham oldini oladi. */
function Guard({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return ok ? <>{children}</> : <Navigate to="/tasks" replace />
}

export default function App() {
  const { me, loading, can } = useAuth()
  const { t } = useT()
  if (loading) return <div className="empty">{t('loading')}</div>
  if (!me) return <Login />
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/tasks" replace />} />
        <Route path="/tasks" element={<TasksPage view="board" />} />
        <Route path="/tasks/:id" element={<TasksPage view="board" />} />
        <Route path="/table" element={<TasksPage view="table" />} />
        <Route path="/table/:id" element={<TasksPage view="table" />} />
        <Route path="/reports" element={<Guard ok={can('reports.read')}><ReportsPage /></Guard>} />
        <Route path="/projects" element={<Guard ok={can('admin.projects') || can('tasks.create')}><ProjectsPage /></Guard>} />
        <Route path="/settings/types" element={<Guard ok={can('admin.task_types')}><TypesPage /></Guard>} />
        <Route path="/settings/templates" element={<Guard ok={can('admin.templates')}><TemplatesPage /></Guard>} />
        <Route path="/staff" element={<Guard ok={can('admin.users')}><StaffPage /></Guard>} />
        <Route path="/admin" element={<Guard ok={can('admin.users') || can('admin.roles') || can('admin.bot')}><AdminPage /></Guard>} />
        <Route path="/settings/telegram" element={<TelegramPage />} />
        <Route path="/settings/profile" element={<ProfilePage />} />
        <Route path="/bulk" element={<Guard ok={can('tasks.bulk_create')}><BulkPage /></Guard>} />
        <Route path="*" element={<Navigate to="/tasks" replace />} />
      </Routes>
    </Layout>
  )
}
