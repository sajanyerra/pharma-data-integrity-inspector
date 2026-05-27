import { Routes, Route, Link, useLocation, useNavigate } from 'react-router-dom'
import { 
  AlertTriangle, FileText, ChevronRight, 
  Database, CheckCircle, Bot, Cpu, BarChart3, ShieldCheck,
  Moon, Sun, BookOpen
} from 'lucide-react'
import { useState, useEffect } from 'react'
import axios from 'axios'
import Dashboard from './pages/Dashboard'
import AnomalyDetection from './pages/AnomalyDetection'
import HITLSelection from './pages/HITLSelection'
import HypothesisView from './pages/HypothesisView'
import ReportPreview from './pages/ReportPreview'
import TraceView from './pages/TraceView'
import StatsForNerds from './pages/StatsForNerds'

import API_BASE from './api'

const STEPS = [
  { path: '/', label: 'Profile', icon: BarChart3 },
  { path: '/anomalies', label: 'Detect', icon: AlertTriangle },
  { path: '/hitl', label: 'Review', icon: ShieldCheck },
  { path: '/hypotheses', label: 'Hypothesize', icon: Cpu },
  { path: '/reports', label: 'Report', icon: FileText },
]

function App() {
  const location = useLocation()
  const navigate = useNavigate()
  const [systemStatus, setSystemStatus] = useState('healthy')
  const [anomalyCount, setAnomalyCount] = useState(0)
  const [approvedCount, setApprovedCount] = useState(0)
  const [hypothesisCount, setHypothesisCount] = useState(0)
  const [darkMode, setDarkMode] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('darkMode') === 'true'
    }
    return false
  })

  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode)
    localStorage.setItem('darkMode', darkMode)
  }, [darkMode])

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const r = await axios.get(`${API_BASE}/health`)
        setSystemStatus(r.data.status)
      } catch { setSystemStatus('error') }
    }

    const fetchState = async () => {
      try {
        const [anomaliesRes, allAnomalies] = await Promise.all([
          axios.get(`${API_BASE}/anomalies`),
          axios.get(`${API_BASE}/anomalies`)
        ])
        const all = allAnomalies.data
        setAnomalyCount(all.length)
        setApprovedCount(all.filter(a => a.hitl_status === 'approved').length)
        setHypothesisCount(all.filter(a => a.hypothesis).length)
      } catch {}
    }

    checkHealth()
    fetchState()
    const interval = setInterval(fetchState, 5000)
    return () => clearInterval(interval)
  }, [])

  const currentIndex = STEPS.findIndex(s => s.path === location.pathname)
  const isTracePage = location.pathname === '/trace'
  const isStatsPage = location.pathname === '/stats'

  const getStepState = (i) => {
    if (i === 0) return anomalyCount > 0 ? 'done' : 'available'
    if (i === 1) return anomalyCount > 0 ? 'done' : 'locked'
    if (i === 2) return anomalyCount > 0 ? 'available' : 'locked'
    if (i === 3) return anomalyCount > 0 ? 'available' : 'locked'
    if (i === 4) return anomalyCount > 0 ? 'available' : 'locked'
    return 'locked'
  }

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col transition-colors duration-300">
      <header className="bg-card border-b border-border sticky top-0 z-50 transition-colors duration-300">
        <div className="px-6 py-2.5 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5 hover:opacity-80 transition-opacity">
            <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
              <Bot className="w-4.5 h-4.5 text-white" />
            </div>
            <div>
              <h1 className="text-sm font-bold text-foreground leading-tight">Pharma Data Integrity Inspector</h1>
              <p className="text-[10px] text-muted-foreground">4-Agent AI Pipeline</p>
            </div>
          </Link>

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <div className={`w-1.5 h-1.5 rounded-full ${systemStatus === 'healthy' ? 'bg-green-500' : 'bg-red-500'}`} />
              <span className="text-muted-foreground text-xs">{systemStatus === 'healthy' ? 'Online' : 'Offline'}</span>
            </div>

            <button
              onClick={() => setDarkMode(!darkMode)}
              className="p-2 rounded-lg text-muted-foreground hover:bg-secondary transition-colors"
              title={darkMode ? 'Light mode' : 'Dark mode'}
            >
              {darkMode ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>

            <Link
              to="/stats"
              className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                isStatsPage ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300' : 'text-muted-foreground hover:bg-secondary'
              }`}
            >
              <BookOpen className="w-3.5 h-3.5" />Stats
            </Link>

            <Link
              to="/trace"
              className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                isTracePage ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300' : 'text-muted-foreground hover:bg-secondary'
              }`}
            >
              <Database className="w-3.5 h-3.5" />Trace
            </Link>
          </div>
        </div>

        {!isTracePage && !isStatsPage && (
          <div className="border-t border-border px-6">
            <div className="flex items-center">
              {STEPS.map((step, i) => {
                const isActive = step.path === location.pathname
                const state = getStepState(i)
                const isDone = state === 'done'
                const isLocked = state === 'locked'
                const isClickable = isDone || isActive || state === 'available'
                const Icon = step.icon

                return (
                  <div key={step.path} className="flex items-center">
                    <button
                      onClick={() => isClickable && navigate(step.path)}
                      disabled={!isClickable}
                      className={`flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium transition-all border-b-2 ${
                        isActive
                          ? 'border-blue-600 text-blue-600 dark:text-blue-400 dark:border-blue-400'
                          : isDone
                          ? 'border-emerald-400 text-emerald-600 dark:text-emerald-400 hover:text-emerald-700'
                          : isLocked
                          ? 'border-transparent text-muted-foreground/40 cursor-not-allowed'
                          : 'border-transparent text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      {isDone && !isActive ? (
                        <CheckCircle className="w-3.5 h-3.5" />
                      ) : (
                        <Icon className="w-3.5 h-3.5" />
                      )}
                      {step.label}
                      {step.path === '/anomalies' && anomalyCount > 0 && (
                        <span className="bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 px-1 py-0.5 rounded-full text-[10px] font-bold leading-none">
                          {anomalyCount}
                        </span>
                      )}
                    </button>
                    {i < STEPS.length - 1 && (
                      <ChevronRight className={`w-3.5 h-3.5 ${isDone ? 'text-emerald-300 dark:text-emerald-700' : 'text-border'}`} />
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </header>

      <main className="flex-1 px-6 py-6 max-w-7xl mx-auto w-full">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/anomalies" element={<AnomalyDetection />} />
          <Route path="/hitl" element={<HITLSelection />} />
          <Route path="/hypotheses" element={<HypothesisView />} />
          <Route path="/reports" element={<ReportPreview />} />
          <Route path="/trace" element={<TraceView />} />
          <Route path="/stats" element={<StatsForNerds />} />
        </Routes>
      </main>
    </div>
  )
}

export default App