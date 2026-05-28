import { useState, useEffect } from 'react'
import { Activity, AlertTriangle, Thermometer, Gauge, Droplet, Waves, ArrowRight, BarChart3, FileText, ShieldCheck, Play, ChevronRight, RotateCcw, Eye, Shield, Zap, Search, Brain } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'

import API_BASE from '../api'

const TAG_ICONS = {
  Temperature: Thermometer,
  Pressure: Gauge,
  Flow: Droplet,
  Level: Waves,
  Vibration: Activity,
  Conductivity: Activity,
}

export default function Dashboard({ liveTags = [] }) {
  const [selectedUnit, setSelectedUnit] = useState('all')
  const [anomalyCount, setAnomalyCount] = useState(0)
  const [resetting, setResetting] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    const fetchState = async () => {
      try {
        const r = await axios.get(`${API_BASE}/anomalies`)
        setAnomalyCount(r.data.length)
      } catch {}
    }
    fetchState()
    const interval = setInterval(fetchState, 5000)
    return () => clearInterval(interval)
  }, [])

  const handleReset = async () => {
    setResetting(true)
    try {
      await axios.post(`${API_BASE}/reset`)
      setAnomalyCount(0)
    } catch {} finally { setResetting(false) }
  }

  const tags = liveTags
  const unitTypes = ['all', ...new Set(tags.map(t => (t.unit_type || t.tag_id.split('-')[0])))]
  const filteredTags = selectedUnit === 'all' ? tags : tags.filter(t => (t.unit_type || t.tag_id.split('-')[0]) === selectedUnit)

  return (
    <div className="space-y-5">
      {/* Hero */}
      <div className="card p-5 bg-gradient-to-br from-slate-700 to-slate-800 text-white border-0">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold">Pharma Data Integrity Inspector</h1>
            <p className="text-slate-300 mt-1 text-xs">5-stage pipeline catches sensor anomalies — including ones that look normal but are wrong.</p>
            <div className="flex items-center gap-2 mt-3">
              <button onClick={() => navigate(anomalyCount === 0 ? '/anomalies' : '/hitl')}
                className="flex items-center gap-1.5 bg-white text-slate-800 px-4 py-2 rounded-lg text-sm font-semibold hover:bg-slate-100 transition-colors shadow">
                <Play className="w-3.5 h-3.5" />{anomalyCount === 0 ? 'Start Analysis' : 'Review Anomalies'}<ArrowRight className="w-3.5 h-3.5" />
              </button>
              <button onClick={handleReset} disabled={resetting}
                className="flex items-center gap-1 bg-slate-600/50 text-slate-300 px-2.5 py-2 rounded-lg text-xs hover:bg-slate-600/80 transition-colors disabled:opacity-50">
                <RotateCcw className={`w-3 h-3 ${resetting ? 'animate-spin' : ''}`} />Reset
              </button>
            </div>
          </div>
          <div className="hidden md:flex items-center gap-0.5 shrink-0">
            {[
              { icon: AlertTriangle, label: 'Detect', color: 'bg-violet-500' },
              { icon: Search, label: 'Investigate', color: 'bg-blue-500' },
              { icon: ShieldCheck, label: 'HITL', color: 'bg-amber-500' },
              { icon: Brain, label: 'Hypothesize', color: 'bg-teal-500' },
              { icon: FileText, label: 'Report', color: 'bg-orange-500' },
            ].map((s, i, arr) => (
              <div key={s.label} className="flex items-center">
                <div className="flex flex-col items-center gap-1 px-2">
                  <div className={`w-8 h-8 ${s.color} rounded-lg flex items-center justify-center`}>
                    <s.icon className="w-4 h-4 text-white" />
                  </div>
                  <span className="text-[8px] text-slate-400">{s.label}</span>
                </div>
                {i < arr.length - 1 && <ChevronRight className="w-3 h-3 text-slate-500" />}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Key features — 3 compact cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        <div className="relative rounded-lg overflow-hidden border border-indigo-200 dark:border-indigo-800 bg-white dark:bg-slate-900">
          <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-indigo-500" />
          <div className="p-3 pl-4 flex items-start gap-2.5">
            <div className="w-7 h-7 rounded bg-indigo-100 dark:bg-indigo-900/30 flex items-center justify-center shrink-0">
              <Zap className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400" />
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <p className="text-xs font-bold text-foreground">Cross-Sensor Corroboration</p>
                <span className="text-[8px] font-bold uppercase tracking-wider bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-300 px-1 py-0.5 rounded">Novel</span>
              </div>
              <p className="text-[10px] text-muted-foreground mt-0.5 leading-relaxed">Catches sensors that read within range but contradict their physically-coupled witnesses.</p>
            </div>
          </div>
        </div>
        <div className="relative rounded-lg overflow-hidden border border-amber-200 dark:border-amber-800 bg-white dark:bg-slate-900">
          <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-amber-400" />
          <div className="p-3 pl-4 flex items-start gap-2.5">
            <div className="w-7 h-7 rounded bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center shrink-0">
              <ShieldCheck className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
            </div>
            <div>
              <p className="text-xs font-bold text-foreground">Human-in-the-Loop Gate</p>
              <p className="text-[10px] text-muted-foreground mt-0.5 leading-relaxed">You approve AI investigation findings before root cause analysis. FDA 21 CFR Part 11 aligned.</p>
            </div>
          </div>
        </div>
        <div className="relative rounded-lg overflow-hidden border border-emerald-200 dark:border-emerald-800 bg-white dark:bg-slate-900">
          <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-emerald-400" />
          <div className="p-3 pl-4 flex items-start gap-2.5">
            <div className="w-7 h-7 rounded bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center shrink-0">
              <Shield className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
            </div>
            <div>
              <p className="text-xs font-bold text-foreground">Output Guardrail</p>
              <p className="text-[10px] text-muted-foreground mt-0.5 leading-relaxed">PII, credentials, and dangerous recommendations are blocked before any AI output reaches you.</p>
            </div>
          </div>
        </div>
      </div>

      {/* Live Tags */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-xs font-bold text-foreground">Live Sensor Tags</h2>
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
            <span className="text-[10px] text-muted-foreground">{tags.length} tags · 5s</span>
          </div>
        </div>

        <div className="flex gap-1 overflow-x-auto pb-1.5 mb-2">
          {unitTypes.map(unit => (
            <button key={unit} onClick={() => setSelectedUnit(unit)}
              className={`px-2 py-0.5 rounded text-[10px] font-medium whitespace-nowrap transition-colors ${selectedUnit === unit ? 'bg-slate-700 text-white dark:bg-slate-500' : 'bg-secondary text-muted-foreground hover:text-foreground'}`}>
              {unit === 'all' ? 'All' : unit}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-1.5">
          {filteredTags.length === 0 ? (
            <div className="col-span-full card p-6 text-center">
              <Activity className="w-6 h-6 text-muted-foreground mx-auto mb-1.5" />
              <p className="text-xs text-muted-foreground">Connecting to sensors...</p>
            </div>
          ) : (
            filteredTags.map((tag) => {
              const Icon = TAG_ICONS[tag.data_type] || Activity
              return (
                <div key={tag.tag_id} className={`card p-2.5 hover:shadow-sm transition-all ${tag.is_anomaly ? 'border-amber-200 dark:border-amber-800 bg-amber-50/50 dark:bg-amber-900/10' : ''}`}>
                  <div className="flex items-center justify-between mb-0.5">
                    <div className="flex items-center gap-1">
                      <Icon className="w-2.5 h-2.5 text-muted-foreground" />
                      <span className="font-semibold text-foreground text-xs">{tag.tag_id}</span>
                    </div>
                    <div className={`w-1 h-1 rounded-full ${tag.quality_code === 'Good' ? 'bg-green-500' : tag.quality_code === 'Warning' ? 'bg-yellow-500' : 'bg-red-500'}`} />
                  </div>
                  <div className="flex items-baseline gap-0.5">
                    <span className="text-base font-bold text-foreground">{typeof tag.value === 'number' ? tag.value.toFixed(1) : tag.value}</span>
                    <span className="text-[9px] text-muted-foreground">{tag.unit}</span>
                  </div>
                  {tag.is_anomaly && (
                    <span className="text-[8px] text-amber-600 dark:text-amber-400 font-bold mt-0.5 block">{tag.anomaly_type.replace(/_/g, ' ')}</span>
                  )}
                </div>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}