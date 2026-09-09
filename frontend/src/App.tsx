import React from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { useAuth } from './lib/auth'
import { useT } from './lib/i18n'
import Admin from './pages/Admin'
import Home from './pages/Home'
import Login from './pages/Login'
import MyTasks from './pages/MyTasks'
import Reports from './pages/Reports'
import Settings from './pages/Settings'
import Tasks from './pages/Tasks'

/** Menyudagi ruxsat bilan bir xil — to'g'ridan-to'g'ri manzil yozib kirishning oldini oladi. */
function Guard({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return ok ? <>{children}</> : <Navigate to="/my" replace />
}

export default function App() {
  const { me, loading, isManager } = useAuth()
  const { t } = useT()
  if (loading) return <div className="empty">{t('loading')}</div>
  if (!me) return <Login />
  const home = isManager ? '/home' : '/my'
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to={home} replace />} />
        <Route path="/home" element={<Guard ok={isManager}><Home /></Guard>} />
        <Route path="/tasks" element={<Guard ok={isManager}><Tasks /></Guard>} />
        <Route path="/tasks/:id" element={<Guard ok={isManager}><Tasks /></Guard>} />
        <Route path="/reports" element={<Guard ok={isManager}><Reports /></Guard>} />
        <Route path="/admin" element={<Guard ok={isManager}><Admin /></Guard>} />
        <Route path="/my" element={<MyTasks />} />
        <Route path="/my/:id" element={<MyTasks />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to={home} replace />} />
      </Routes>
    </Layout>
  )
}
