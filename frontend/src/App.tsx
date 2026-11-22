import { lazy, Suspense, useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { BrowserRouter, Route, Routes, useLocation } from 'react-router-dom'
import { CheckCircle2, X } from 'lucide-react'
import { Sidebar } from './components/Sidebar'
import { Topbar } from './components/Topbar'
import './App.css'

const Dashboard = lazy(() => import('./pages/Dashboard').then((module) => ({ default: module.Dashboard })))
const ModulePlaceholder = lazy(() => import('./pages/ModulePlaceholder').then((module) => ({ default: module.ModulePlaceholder })))

function Workspace() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem('cropfarmai-theme') === 'dark')
  const [toast, setToast] = useState('')
  const location = useLocation()

  useEffect(() => {
    document.documentElement.dataset.theme = darkMode ? 'dark' : 'light'
    localStorage.setItem('cropfarmai-theme', darkMode ? 'dark' : 'light')
  }, [darkMode])

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(''), 3600)
    return () => window.clearTimeout(timer)
  }, [toast])

  return (
    <div className={`workspace${sidebarCollapsed ? ' workspace-sidebar-collapsed' : ''}`}>
      <Sidebar
        collapsed={sidebarCollapsed}
        mobileOpen={mobileNavOpen}
        onCloseMobile={() => setMobileNavOpen(false)}
        onSignOut={() => setToast('There is no signed-in account in this preview to sign out.')}
        onToggleCollapsed={() => setSidebarCollapsed((collapsed) => !collapsed)}
      />
      <div className="workspace-main">
        <Topbar
          darkMode={darkMode}
          onOpenMobileNav={() => setMobileNavOpen(true)}
          onNavigate={() => setMobileNavOpen(false)}
          onToggleSidebar={() => setSidebarCollapsed((collapsed) => !collapsed)}
          onToggleTheme={() => setDarkMode((enabled) => !enabled)}
        />
        <main className="workspace-content">
          <AnimatePresence mode="wait">
            <motion.div
              animate={{ opacity: 1, y: 0 }}
              initial={{ opacity: 0, y: 8 }}
              key={location.pathname}
              transition={{ duration: 0.18, ease: 'easeOut' }}
            >
              <Suspense fallback={<div aria-live="polite" className="page-loading">Loading page…</div>}>
                <Routes location={location}>
                  <Route element={<Dashboard />} path="/" />
                  <Route element={<ModulePlaceholder />} path="*" />
                </Routes>
              </Suspense>
            </motion.div>
          </AnimatePresence>
        </main>
        <footer className="workspace-footer">
          <span>CropFarmAI</span>
          <span>Smart Farming. Better Tomorrow.</span>
        </footer>
      </div>
      <AnimatePresence>
        {toast && (
          <motion.div
            animate={{ opacity: 1, y: 0 }}
            className="toast-message"
            exit={{ opacity: 0, y: 8 }}
            initial={{ opacity: 0, y: 8 }}
            role="status"
          >
            <CheckCircle2 aria-hidden="true" size={18} />
            <span>{toast}</span>
            <button aria-label="Dismiss message" onClick={() => setToast('')} type="button"><X size={15} /></button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Workspace />
    </BrowserRouter>
  )
}
