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
import UsersPage from './pages/Users'
import TelegramPage from './pages/Telegram'
import BulkPage from './pages/Bulk'
import ProjectsPage from './pages/Projects'
import ProfilePage from './pages/Profile'

export default function App() {
  const { me, loading } = useAuth()
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
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/settings/types" element={<TypesPage />} />
        <Route path="/settings/templates" element={<TemplatesPage />} />
        <Route path="/settings/users" element={<UsersPage />} />
        <Route path="/settings/telegram" element={<TelegramPage />} />
        <Route path="/settings/profile" element={<ProfilePage />} />
        <Route path="/bulk" element={<BulkPage />} />
        <Route path="*" element={<Navigate to="/tasks" replace />} />
      </Routes>
    </Layout>
  )
}
