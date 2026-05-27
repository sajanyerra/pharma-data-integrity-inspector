import { useState, useEffect } from 'react'
import { Activity, AlertTriangle, Thermometer, Gauge, Droplet, Waves, ArrowRight, BarChart3, Cpu, FileText, ShieldCheck, Play, ChevronRight, RotateCcw, Eye, Shield, Zap } from 'lucide-react'
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

const AGENTS = [
  { num: '1', name: 'Anomaly Detector', icon: AlertTriangle, color: 'bg-violet-500', lightColor: 'bg-violet-50 dark:bg-violet-900/20', desc: 'Loads 24h of sensor data in 1 query, computes inline profiles, runs 9 integrity checks (including Cross-Sensor Corroboration), then AI prioritizes findings. Returns in ~5s.' },
  { num: '2', name: 'Hypothesis Generator', icon: Cpu, color: 'bg-teal-500', lightColor: 'bg-teal-50 dark:bg-teal-900/20', desc: 'Uses AI to propose root causes with confidence scores and remediation steps. Guardrail blocks PII and pharma-sensitive data.' },
  { num: '3', name: 'Report Generator', icon: FileText, color: 'bg-orange-500', lightColor: 'bg-orange-50 dark:bg-orange-900/20', desc: 'Packages findings into PDF, HTML, JSON, with AI-written executive narrative. Guardrail checks for dangerous recommendations.' },
]

export default function Dashboard({ liveTags = [] }) {
  const [selectedUnit, setSelectedUnit] = useState('all')
  const [anomalyCount, setAnomalyCount] = useState(0)
  const [approvedCount, setApprovedCount] = useState(0)
  const [resetting, setResetting] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    const fetchState = async () => {
      try {
        const r = await axios.get(`${API_BASE}/anomalies`)
        setAnomalyCount(r.data.length)
        setApprovedCount(r.data.filter(a => a.hitl_status === 'approved').length)
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
      setApprovedCount(0)
    } catch {} finally { setResetting(false) }
  }

  const tags = liveTags
  const unitTypes = ['all', ...new Set(tags.map(t => (t.unit_type || t.tag_id.split('-')[0])))]
  const filteredTags = selectedUnit === 'all' ? tags : tags.filter(t => (t.unit_type || t.tag_id.split('-')[0]) === selectedUnit)

  const nextStep = anomalyCount === 0 ? '/anomalies' : approvedCount === 0 ? '/hitl' : null
  const nextLabel = anomalyCount === 0 ? 'Start Analysis' : 'Review Anomalies'

  return (
    <div className="space-y-6">
      {/* Hero */}
      <div className="card p-6 bg-gradient-to-br from-slate-700 to-slate-800 text-white border-0">
        <div className="flex items-start justify-between gap-6">
          <div className="max-w-lg">
            <h1 className="text-2xl font-bold">Pharma Data Integrity Inspector</h1>
            <p className="text-slate-300 mt-2 text-sm">3 AI agents monitor your pharma sensors — including Cross-Sensor Corroboration that catches sensors no historian can.</p>
            <div className="flex items-center gap-3 mt-4">
              {nextStep ? (
                <button onClick={() => navigate(nextStep)} className="flex items-center gap-2 bg-white text-slate-800 px-5 py-2.5 rounded-lg font-semibold hover:bg-slate-100 transition-colors shadow-lg">
                  <Play className="w-4 h-4" />{nextLabel}<ArrowRight className="w-4 h-4" />
                </button>
              ) : (
                <button onClick={() => navigate('/hypotheses')} className="flex items-center gap-2 bg-white text-slate-800 px-5 py-2.5 rounded-lg font-semibold hover:bg-slate-100 transition-colors shadow-lg">
                  View Hypotheses<ArrowRight className="w-4 h-4" />
                </button>
              )}
              <button onClick={handleReset} disabled={resetting} className="flex items-center gap-1.5 bg-slate-600/50 text-slate-300 px-3 py-2 rounded-lg text-sm font-medium hover:bg-slate-600/80 transition-colors disabled:opacity-50">
                <RotateCcw className={`w-3.5 h-3.5 ${resetting ? 'animate-spin' : ''}`} />Reset
              </button>
            </div>
          </div>
          <div className="hidden md:flex items-center gap-0.5 shrink-0">
            {AGENTS.map((agent, i) => {
              const Icon = agent.icon
              return (
                <div key={agent.num} className="flex items-center">
                  <div className="flex flex-col items-center gap-1.5 px-3">
                    <div className={`w-10 h-10 ${agent.color} rounded-xl flex items-center justify-center shadow-lg`}>
                      <Icon className="w-5 h-5 text-white" />
                    </div>
                    <div className="text-center">
                      <p className="text-[9px] font-bold text-white leading-none">{agent.name}</p>
                      <p className="text-[8px] text-slate-400 leading-tight mt-0.5">Agent {agent.num}</p>
                    </div>
                  </div>
                  {i < AGENTS.length - 1 && (
                    <div className="flex flex-col items-center gap-1">
                      {i === 1 && <ShieldCheck className="w-4 h-4 text-amber-400" />}
                      <ChevronRight className={`${i === 1 ? 'w-3 h-3' : 'w-4 h-4'} text-slate-500`} />
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Agent cards */}
      <div>
        <h2 className="text-sm font-bold text-foreground mb-3">How the 3 Agents Work</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {AGENTS.map((agent, i) => {
            const Icon = agent.icon
            return (
              <div key={agent.num} className={`card p-4 flex items-start gap-3 ${agent.lightColor}`}>
                <div className={`w-10 h-10 ${agent.color} rounded-xl flex items-center justify-center shrink-0`}>
                  <Icon className="w-5 h-5 text-white" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-[10px] text-muted-foreground font-medium">Agent {agent.num}</span>
                    <span className="text-sm font-bold text-foreground">{agent.name}</span>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed">{agent.desc}</p>
                </div>
                {i === 1 && (
                  <div className="flex items-center gap-1 px-2 py-1 rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 shrink-0">
                    <Eye className="w-3 h-3" />
                    <span className="text-[10px] font-bold">HITL</span>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Cross-Sensor Corroboration — the differentiator */}
      <div className="relative rounded-xl overflow-hidden border border-indigo-200 dark:border-indigo-800 bg-white dark:bg-slate-900">
        <div className="absolute left-0 top-0 bottom-0 w-1 bg-indigo-500" />
        <div className="p-4 pl-5 flex items-start gap-4">
          <div className="w-10 h-10 rounded-lg bg-indigo-100 dark:bg-indigo-900/30 flex items-center justify-center shrink-0">
            <Zap className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <h3 className="text-sm font-bold text-foreground">Cross-Sensor Corroboration</h3>
              <span className="text-[9px] font-bold uppercase tracking-wider bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-300 px-1.5 py-0.5 rounded">Novel</span>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              A sensor reads 172°C — within normal range, quality code "Good" — passes every threshold check. But its correlated sensors say the real temperature is 175°C. The sensor is wrong by 3°C, and <strong className="text-foreground">no historian in the world would flag it</strong>. Cross-sensor corroboration cross-references physically-coupled sensors to catch what every other tool misses.
            </p>
            <button onClick={() => navigate('/stats')} className="mt-2 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:underline flex items-center gap-1">
              Read how it works <ChevronRight className="w-3 h-3" />
            </button>
          </div>
        </div>
      </div>

      {/* Safety layer */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="relative rounded-xl overflow-hidden border border-amber-200 dark:border-amber-800 bg-white dark:bg-slate-900">
          <div className="absolute left-0 top-0 bottom-0 w-1 bg-amber-400" />
          <div className="p-4 pl-5 flex items-start gap-3">
            <div className="w-8 h-8 rounded-lg bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center shrink-0">
              <ShieldCheck className="w-4 h-4 text-amber-600 dark:text-amber-400" />
            </div>
            <div>
              <p className="text-sm font-bold text-foreground">Human-in-the-Loop Gate</p>
              <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">Between Agent 1 and 2 — you approve which anomalies get AI root cause analysis. Required for FDA 21 CFR Part 11.</p>
            </div>
          </div>
        </div>
        <div className="relative rounded-xl overflow-hidden border border-emerald-200 dark:border-emerald-800 bg-white dark:bg-slate-900">
          <div className="absolute left-0 top-0 bottom-0 w-1 bg-emerald-400" />
          <div className="p-4 pl-5 flex items-start gap-3">
            <div className="w-8 h-8 rounded-lg bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center shrink-0">
              <Shield className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
            </div>
            <div>
              <p className="text-sm font-bold text-foreground">Output Guardrail</p>
              <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">PII, credentials, batch numbers, and dangerous recommendations are blocked or redacted before any AI output reaches you.</p>
            </div>
          </div>
        </div>
      </div>

      {/* Live Tags */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-bold text-foreground">Live Sensor Tags</h2>
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
            <span className="text-xs text-muted-foreground">{tags.length} tags · 5s refresh</span>
          </div>
        </div>

        <div className="flex gap-1.5 overflow-x-auto pb-2 mb-3">
          {unitTypes.map(unit => (
            <button key={unit} onClick={() => setSelectedUnit(unit)} className={`px-2.5 py-1 rounded-md text-xs font-medium whitespace-nowrap transition-colors ${selectedUnit === unit ? 'bg-slate-700 text-white dark:bg-slate-500' : 'bg-secondary text-muted-foreground hover:text-foreground'}`}>
              {unit === 'all' ? 'All' : unit}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-2">
          {filteredTags.length === 0 ? (
            <div className="col-span-full card p-8 text-center">
              <Activity className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
              <p className="text-sm text-muted-foreground">Connecting to sensors...</p>
            </div>
          ) : (
            filteredTags.map((tag) => {
              const Icon = TAG_ICONS[tag.data_type] || Activity
              return (
                <div key={tag.tag_id} className={`card p-3 hover:shadow-md transition-all ${tag.is_anomaly ? 'border-amber-200 dark:border-amber-800 bg-amber-50/50 dark:bg-amber-900/10' : ''}`}>
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-1.5">
                      <Icon className="w-3 h-3 text-muted-foreground" />
                      <span className="font-semibold text-foreground text-sm">{tag.tag_id}</span>
                    </div>
                    <div className={`w-1.5 h-1.5 rounded-full ${tag.quality_code === 'Good' ? 'bg-green-500' : tag.quality_code === 'Warning' ? 'bg-yellow-500' : 'bg-red-500'}`} />
                  </div>
                  <p className="text-[10px] text-muted-foreground mb-1.5 truncate">{tag.tag_name || tag.tag_id}</p>
                  <div className="flex items-baseline gap-1">
                    <span className="text-lg font-bold text-foreground">{typeof tag.value === 'number' ? tag.value.toFixed(1) : tag.value}</span>
                    <span className="text-xs text-muted-foreground">{tag.unit}</span>
                  </div>
                  <div className="flex items-center gap-2 mt-1.5 text-[9px]">
                    <span className="text-muted-foreground">Range: {tag.normal_min}–{tag.normal_max}</span>
                    {tag.is_anomaly && <span className="text-amber-600 dark:text-amber-400 font-bold">{tag.anomaly_type.replace(/_/g, ' ')}</span>}
                  </div>
                </div>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}