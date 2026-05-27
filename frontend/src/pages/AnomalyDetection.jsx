import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { AlertTriangle, AlertCircle, AlertOctagon, CheckCircle, ChevronRight, Filter, RefreshCw, Trash, ArrowRight, ShieldCheck, Check, Info, Eye } from 'lucide-react'
import axios from 'axios'
import { useNavigate } from 'react-router-dom'

import API_BASE from '../api'

const SEVERITY_CONFIG = {
  critical: { icon: AlertOctagon, color: 'bg-purple-100 text-purple-800 border-purple-200 dark:bg-purple-900/30 dark:text-purple-300 dark:border-purple-800', label: 'CRITICAL' },
  high: { icon: AlertTriangle, color: 'bg-red-100 text-red-800 border-red-200 dark:bg-red-900/30 dark:text-red-300 dark:border-red-800', label: 'HIGH' },
  medium: { icon: AlertCircle, color: 'bg-yellow-100 text-yellow-800 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-300 dark:border-yellow-800', label: 'MEDIUM' },
  low: { icon: AlertCircle, color: 'bg-blue-100 text-blue-800 border-blue-200 dark:bg-blue-900/30 dark:text-blue-300 dark:border-blue-800', label: 'LOW' },
}

const CHECKS = [
  { name: 'Sensor Drift', desc: 'Gradual deviation from baseline (>1%/hr drift rate)' },
  { name: 'Stuck Values', desc: 'Tag value unchanged for an unusual period (<3 unique values)' },
  { name: 'Impossible Readings', desc: 'Outside physical limits (e.g., negative pressure)' },
  { name: 'Rate of Change', desc: 'Value changed faster than process physics allow' },
  { name: 'Noise Burst', desc: 'Variance spike >5x normal baseline' },
  { name: 'Correlation Break', desc: 'Related tags no longer moving together (r shift >0.8)' },
  { name: 'CIP Issues', desc: 'Clean-in-place temperature below protocol threshold' },
  { name: 'FDA Audit Trail', desc: 'Quality code pattern indicates compliance concern' },
  { name: 'Cross-Sensor Corroboration', desc: 'Sensor contradicts correlated witnesses — plausible but WRONG', novel: true },
]

const HUMAN_REASONS = {
  sensor_drift: 'Value is slowly drifting away from its normal range — calibration may be degrading.',
  stuck_value: 'Sensor reading has not changed for an unusual period — possible communication or hardware failure.',
  impossible_reading: 'Reading violates physical limits (e.g., temperature below absolute zero).',
  rate_of_change_violation: 'Value changed faster than the process physics allow — likely a spike or data error.',
  noise_burst: 'Variance spiked far above baseline — possible electrical interference or sensor malfunction.',
  quality_code_mismatch: 'High outlier ratio despite Good quality codes — the SCADA quality flag may be wrong.',
  data_gap: 'Expected readings are missing from the time series — collection or storage failure.',
  statistical_outlier: 'Value is an extreme statistical outlier (>5 sigma) from the 24-hour baseline.',
  correlation_breakdown: 'Two tags that normally move together have diverged — one may be malfunctioning.',
  cip_temperature_issue: 'CIP supply temperature is outside the required 70–85°C cleaning protocol range.',
  fda_audit_trail_concern: 'Unusual quality code pattern — potential 21 CFR Part 11 compliance concern.',
  cross_sensor_inconsistency: 'Sensor reads within normal range but contradicts its physically-correlated witnesses — it is plausible but WRONG.',
}

export default function AnomalyDetection() {
  const [anomalies, setAnomalies] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')
  const [runningAnalysis, setRunningAnalysis] = useState(false)
  const [showChecks, setShowChecks] = useState(false)
  const navigate = useNavigate()

  const fetchAnomalies = async () => {
    try {
      const r = await axios.get(`${API_BASE}/anomalies`)
      setAnomalies(r.data)
      setLoading(false)
    } catch { setLoading(false) }
  }

  useEffect(() => { fetchAnomalies() }, [])

  const runAnalysis = async () => {
    setRunningAnalysis(true)
    try {
      const startRes = await axios.post(`${API_BASE}/analyze`, { hours: 24 })
      const jobId = startRes.data.job_id
      if (!jobId) {
        setRunningAnalysis(false)
        alert('Analysis failed to start — no job ID returned.')
        return
      }
      let pollAttempts = 0
      const poll = setInterval(async () => {
        pollAttempts++
        if (pollAttempts > 60) {
          clearInterval(poll)
          setRunningAnalysis(false)
          alert('Analysis timed out. Please try again.')
          return
        }
        try {
          const statusRes = await axios.get(`${API_BASE}/analyze/status/${jobId}`)
          const { status, progress, result, error } = statusRes.data
          if (status === 'completed') {
            clearInterval(poll)
            setRunningAnalysis(false)
            await fetchAnomalies()
            if (result && result.anomalies_detected === 0) {
              alert('Analysis complete — no anomalies detected.')
            }
          } else if (status === 'failed') {
            clearInterval(poll)
            setRunningAnalysis(false)
            alert('Analysis failed: ' + (error || 'Unknown error'))
          }
        } catch (err) {
          clearInterval(poll)
          setRunningAnalysis(false)
          alert('Polling error: ' + (err.message || 'Network error'))
        }
      }, 3000)
    } catch (err) {
      setRunningAnalysis(false)
      alert('Failed to start analysis: ' + (err.message || 'Network error'))
    }
  }

  const filteredAnomalies = filter === 'all' ? anomalies : anomalies.filter(a => a.severity === filter)
  const countBySeverity = {
    critical: anomalies.filter(a => a.severity === 'critical').length,
    high: anomalies.filter(a => a.severity === 'high').length,
    medium: anomalies.filter(a => a.severity === 'medium').length,
    low: anomalies.filter(a => a.severity === 'low').length,
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Anomaly Detection</h1>
          <p className="text-muted-foreground text-sm mt-0.5">9 integrity checks applied across 20 tags</p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={runAnalysis} disabled={runningAnalysis} className="btn-primary flex items-center gap-2">
            <RefreshCw className={`w-4 h-4 ${runningAnalysis ? 'animate-spin' : ''}`} />
            {runningAnalysis ? 'Analyzing (~8s)...' : 'Run Analysis'}
          </button>
          <button onClick={async () => { try { await axios.delete(`${API_BASE}/anomalies/clear`); await fetchAnomalies() } catch {} }} className="btn-secondary flex items-center gap-2">
            <Trash className="w-4 h-4" />Clear
          </button>
        </div>
      </div>

      <div className="hint">
        <Info className="w-3.5 h-3.5 shrink-0" />
        <span>Each detected anomaly includes the specific check that failed, the evidence, and why it matters.</span>
      </div>

      {/* 10 Checks Grid */}
      <div className="card p-4">
        <button onClick={() => setShowChecks(!showChecks)} className="flex items-center justify-between w-full text-left">
          <span className="text-sm font-semibold text-foreground">9 Data Integrity Checks</span>
          <ChevronRight className={`w-4 h-4 text-muted-foreground transition-transform ${showChecks ? 'rotate-90' : ''}`} />
        </button>
        {showChecks && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} className="mt-3 grid grid-cols-2 md:grid-cols-5 gap-2">
            {CHECKS.map((c, i) => (
              <div key={i} className={`flex items-start gap-2 p-2 rounded-lg ${c.novel ? 'bg-indigo-50 dark:bg-indigo-900/10 border border-indigo-200 dark:border-indigo-800' : 'bg-secondary'}`}>
                {c.novel ? <Eye className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400 mt-0.5 shrink-0" /> : <Check className="w-3.5 h-3.5 text-blue-600 mt-0.5 shrink-0" />}
                <div><p className="text-xs font-medium text-foreground">{c.name} {c.novel && <span className="text-[9px] font-bold uppercase tracking-wider text-indigo-600 dark:text-indigo-400">Novel</span>}</p><p className="text-[10px] text-muted-foreground leading-tight">{c.desc}</p></div>
              </div>
            ))}
          </motion.div>
        )}
      </div>

      {/* Severity Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {Object.entries(SEVERITY_CONFIG).map(([severity, config]) => (
          <motion.button key={severity} onClick={() => setFilter(filter === severity ? 'all' : severity)} whileTap={{ scale: 0.98 }} className={`card p-3 border-l-4 text-left ${config.color} hover:shadow-md transition-all ${filter === severity ? 'ring-2 ring-blue-500' : ''}`}>
            <div className="flex items-center gap-1.5 mb-1">
              <config.icon className={`w-4 h-4`} />
              <span className="text-xs font-medium text-muted-foreground">{config.label}</span>
            </div>
            <span className="text-2xl font-bold text-foreground">{countBySeverity[severity]}</span>
          </motion.button>
        ))}
      </div>

      {/* Anomalies List */}
      <div className="card overflow-hidden">
        <div className="px-5 py-3 border-b border-border bg-secondary">
          <h2 className="text-sm font-semibold text-foreground">Detected ({filteredAnomalies.length})</h2>
        </div>
        {loading ? (
          <div className="p-6 space-y-4">{Array(5).fill(0).map((_, i) => <div key={i} className="animate-pulse flex items-center gap-4"><div className="w-9 h-9 bg-secondary rounded-lg" /><div className="flex-1"><div className="h-4 bg-secondary rounded w-1/4 mb-2" /><div className="h-3 bg-secondary rounded w-1/2" /></div></div>)}</div>
        ) : filteredAnomalies.length === 0 ? (
          <div className="p-10 text-center">
            <CheckCircle className="w-12 h-12 text-green-500 mx-auto mb-3" />
            <h3 className="text-base font-semibold text-foreground">{anomalies.length === 0 ? 'Run analysis to detect anomalies' : 'No anomalies match filter'}</h3>
          </div>
        ) : (
          <div className="divide-y divide-border">
            {filteredAnomalies.map((anomaly, index) => {
              const severityConfig = SEVERITY_CONFIG[anomaly.severity] || SEVERITY_CONFIG.low
              const SeverityIcon = severityConfig.icon
              const humanReason = HUMAN_REASONS[anomaly.anomaly_type] || 'Anomaly detected by integrity checks.'
              const isSilentLie = anomaly.is_silent_lie || anomaly.anomaly_type === 'cross_sensor_inconsistency'
              return (
                <motion.div key={anomaly.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: index * 0.03 }} className={`p-4 hover:bg-secondary/50 transition-colors ${isSilentLie ? 'border-l-4 border-l-indigo-500 bg-indigo-50/50 dark:bg-indigo-900/10' : ''}`}>
                    <div className="flex items-start gap-3">
                      <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${isSilentLie ? 'bg-indigo-100 text-indigo-800 border border-indigo-300 dark:bg-indigo-900/30 dark:text-indigo-300 dark:border-indigo-700' : severityConfig.color}`}>
                        {isSilentLie ? <Eye className="w-4 h-4" /> : <SeverityIcon className="w-4 h-4" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className="font-semibold text-foreground text-sm">{anomaly.tag_id}</span>
                        {isSilentLie && <span className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-300">Corroboration</span>}
                        {!isSilentLie && <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-medium ${severityConfig.color}`}>{severityConfig.label}</span>}
                        {isSilentLie ? (
                          <span className="text-xs text-amber-700 dark:text-amber-300 font-medium">Sensor contradicts witnesses</span>
                        ) : (
                          <span className="text-xs text-muted-foreground">{anomaly.anomaly_type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</span>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground mb-1.5">{humanReason}</p>
                      {isSilentLie && anomaly.evidence?.witnesses && (
                        <p className="text-[11px] text-amber-700 dark:text-amber-300 mb-1.5">
                          Witness sensors contradict: <strong>{anomaly.evidence.witnesses}</strong>
                          {anomaly.evidence.contradictions?.map((c, ci) => (
                            <span key={ci} className="block ml-2 text-[10px] text-muted-foreground italic">
                              {c.witness}: r dropped from {c.baseline_correlation} to {c.recent_correlation} ({c.relationship})
                            </span>
                          ))}
                        </p>
                      )}
                      {anomaly.evidence && Object.keys(anomaly.evidence).length > 0 && (
                        <div className="flex flex-wrap gap-1.5 mb-1.5">
                          {Object.entries(anomaly.evidence).filter(([k]) => k !== 'contradictions').slice(0, 4).map(([key, value]) => (
                            <span key={key} className="text-[10px] bg-secondary px-2 py-0.5 rounded font-mono">
                              {key}: {typeof value === 'number' ? value.toFixed(2) : String(value)}
                            </span>
                          ))}
                        </div>
                      )}
                      <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                        <span>{(anomaly.confidence * 100).toFixed(0)}% confidence</span>
                        {anomaly.hitl_status !== 'pending' && <span className={`font-medium ${anomaly.hitl_status === 'approved' ? 'text-emerald-600' : 'text-red-500'}`}>{anomaly.hitl_status}</span>}
                      </div>
                    </div>
                    <ChevronRight className="w-4 h-4 text-muted-foreground" />
                  </div>
                </motion.div>
              )
            })}
          </div>
        )}
      </div>

      {anomalies.length > 0 && (
        <div className="next-step">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-blue-600" />
            <span className="text-sm font-medium text-foreground">Next: approve or reject anomalies</span>
          </div>
          <button onClick={() => navigate('/hitl')} className="next-step-btn"><ArrowRight className="w-4 h-4" /></button>
        </div>
      )}
    </div>
  )
}