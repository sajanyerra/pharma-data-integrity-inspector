import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle, XCircle, Send, ArrowRight, Cpu, ChevronDown, Loader2 } from 'lucide-react'
import axios from 'axios'
import { useNavigate } from 'react-router-dom'

import API_BASE from '../api'

const HUMAN_REASONS = {
  sensor_drift: 'Value is slowly drifting away from its normal range, suggesting calibration degradation.',
  stuck_value: 'Reading has not changed for an unusual period, indicating possible hardware failure.',
  impossible_reading: 'Reading violates physical limits (e.g., temperature below absolute zero).',
  rate_of_change_violation: 'Value changed faster than the process physics allow.',
  quality_code_mismatch: 'High outlier ratio despite good quality codes — SCADA flags may be wrong.',
  data_gap: 'Expected readings are missing from the time series.',
  statistical_outlier: 'Value is a statistical outlier (Z-score > 3) from the 24-hour baseline.',
  correlation_breakdown: 'Two normally correlated tags have diverged.',
  cip_temperature_issue: 'CIP supply temperature is outside the 70-85°C protocol range.',
  fda_audit_trail_concern: 'Same user ID in both manufacturing and QA, violating separation of duties.',
}

export default function HITLSelection() {
  const [anomalies, setAnomalies] = useState([])
  const [selections, setSelections] = useState({})
  const [comments, setComments] = useState({})
  const [processing, setProcessing] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [expandedAnomaly, setExpandedAnomaly] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    const fetchAnomalies = async () => {
      try {
        const r = await axios.get(`${API_BASE}/anomalies?status=pending`)
        setAnomalies(r.data)
        const init = {}
        r.data.forEach(a => { init[a.id] = null })
        setSelections(init)
      } catch {}
    }
    fetchAnomalies()
  }, [])

  const handleSelection = (id, status) => {
    setSelections(prev => ({ ...prev, [id]: prev[id] === status ? null : status }))
  }

  const handleComment = (id, comment) => {
    setComments(prev => ({ ...prev, [id]: comment }))
  }

  const handleSubmit = async () => {
    setProcessing(true)
    try {
      const payload = Object.entries(selections)
        .filter(([_, status]) => status !== null)
        .map(([anomaly_id, status]) => ({ anomaly_id: parseInt(anomaly_id), status, comment: comments[anomaly_id] || '' }))
      await axios.post(`${API_BASE}/anomalies/select-batch`, payload)
      setSubmitted(true)
    } catch {} finally { setProcessing(false) }
  }

  const handleAutoAdvance = async () => {
    setProcessing(true)
    try {
      const payload = Object.entries(selections)
        .filter(([_, status]) => status !== null)
        .map(([anomaly_id, status]) => ({ anomaly_id: parseInt(anomaly_id), status, comment: comments[anomaly_id] || '' }))
      await axios.post(`${API_BASE}/anomalies/select-batch`, payload)
      const approvedCount = Object.values(selections).filter(s => s === 'approved').length
      if (approvedCount > 0) {
        await axios.post(`${API_BASE}/generate-hypotheses`)
        navigate('/hypotheses')
      } else {
        navigate('/hypotheses')
      }
    } catch {} finally { setProcessing(false) }
  }

  const approvedCount = anomalies.filter(a => selections[a.id] === 'approved').length
  const rejectedCount = anomalies.filter(a => selections[a.id] === 'rejected').length
  const pendingCount = anomalies.length - approvedCount - rejectedCount
  const allDecided = anomalies.length > 0 && pendingCount === 0

  return (
    <div className="space-y-5 pb-28">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Human-in-the-Loop Review</h1>
        <p className="text-muted-foreground text-sm mt-0.5">Approve real anomalies, reject false positives</p>
      </div>

      <div className="card p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-foreground">Progress</span>
          <span className="text-xs text-muted-foreground">{approvedCount + rejectedCount}/{anomalies.length}</span>
        </div>
        <div className="flex gap-1 h-2.5 rounded-full bg-secondary overflow-hidden">
          {anomalies.map(a => (
            <div key={a.id} className={`rounded-full transition-all duration-300 flex-1 ${selections[a.id] === 'approved' ? 'bg-emerald-500' : selections[a.id] === 'rejected' ? 'bg-red-400' : 'bg-border'}`} />
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-3 sm:gap-4 mt-2 text-xs text-muted-foreground">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500" />{approvedCount} approved</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-400" />{rejectedCount} rejected</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-border" />{pendingCount} pending</span>
        </div>
      </div>

      {!allDecided && (approvedCount > 0 || rejectedCount > 0) && (
        <div className="card p-3 bg-blue-50 border-blue-200 dark:bg-blue-900/20 dark:border-blue-800">
          <p className="text-xs text-blue-800 dark:text-blue-300 font-medium">
            {pendingCount > 0 ? `Review all ${pendingCount} remaining anomaly${pendingCount !== 1 ? 's' : ''} to auto-advance, or submit partial reviews with the button below.` : ''}
          </p>
        </div>
      )}

      {anomalies.length === 0 ? (
        <div className="card p-12 text-center">
          <CheckCircle className="w-12 h-12 text-green-500 mx-auto mb-3" />
          <h3 className="text-base font-semibold text-foreground">No pending anomalies</h3>
          <p className="text-sm text-muted-foreground mt-1">All anomalies have been reviewed</p>
        </div>
      ) : (
        <div className="space-y-3">
          {anomalies.map((anomaly, index) => {
            const sel = selections[anomaly.id]
            const isExpanded = expandedAnomaly === anomaly.id
            const humanReason = HUMAN_REASONS[anomaly.anomaly_type] || 'Anomaly detected by integrity checks.'
            return (
              <motion.div
                key={anomaly.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.04 }}
                className={`card overflow-hidden transition-all duration-200 ${sel === 'approved' ? 'border-emerald-400 dark:border-emerald-600 shadow-md' : sel === 'rejected' ? 'opacity-60' : 'hover:shadow-md'}`}
              >
                <div className="p-4">
                  <div className="flex flex-col sm:flex-row sm:items-start gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-2 mb-1">
                        <span className="font-bold text-foreground">{anomaly.tag_id}</span>
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-secondary text-muted-foreground">{anomaly.severity?.toUpperCase()}</span>
                        <span className="text-xs text-muted-foreground">{anomaly.anomaly_type.replace(/_/g, ' ')}</span>
                      </div>
                      <p className="text-xs text-muted-foreground mb-1.5">{humanReason}</p>
                      <p className="text-[11px] sm:text-[10px] text-muted-foreground mb-2">{(anomaly.confidence * 100).toFixed(0)}% confidence {anomaly.tag_name && `· ${anomaly.tag_name}`}</p>

                      <button onClick={() => setExpandedAnomaly(isExpanded ? null : anomaly.id)} className="text-[10px] text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1">
                        <ChevronDown className={`w-3 h-3 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                        {isExpanded ? 'Hide' : 'Show'} evidence
                      </button>
                      <AnimatePresence>
                        {isExpanded && anomaly.evidence && (
                          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="mt-2 overflow-hidden">
                            <div className="flex flex-wrap gap-1.5">
                              {Object.entries(anomaly.evidence).slice(0, 5).map(([key, value]) => (
                                <span key={key} className="text-[10px] bg-secondary px-2 py-1 rounded-md font-mono break-all"><span className="font-medium">{key}:</span> {typeof value === 'number' ? value.toFixed(2) : String(value)}</span>
                              ))}
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>

                      <input type="text" placeholder="Comment (optional)..." value={comments[anomaly.id] || ''} onChange={(e) => handleComment(anomaly.id, e.target.value)} className="mt-2 w-full px-2.5 py-1.5 border border-border rounded-lg text-xs bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent" />
                    </div>

                    {/* Buttons: side on desktop, bottom on mobile */}
                    <div className="flex sm:flex-col gap-1.5 shrink-0">
                      <button onClick={() => handleSelection(anomaly.id, 'approved')} className={sel === 'approved' ? 'btn-approve-active' : 'btn-approve'}>
                        <span className="flex items-center gap-1 sm:gap-1.5"><CheckCircle className="w-3.5 h-3.5" /><span className="hidden sm:inline">Approve</span></span>
                      </button>
                      <button onClick={() => handleSelection(anomaly.id, 'rejected')} className={sel === 'rejected' ? 'btn-reject-active' : 'btn-reject'}>
                        <span className="flex items-center gap-1 sm:gap-1.5"><XCircle className="w-3.5 h-3.5" /><span className="hidden sm:inline">Reject</span></span>
                      </button>
                    </div>
                  </div>
                </div>
              </motion.div>
            )
          })}
        </div>
      )}

      <AnimatePresence>
        {(approvedCount > 0 || rejectedCount > 0) && !submitted && (
          <motion.div
            initial={{ y: 100, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 100, opacity: 0 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className="fixed bottom-0 left-0 right-0 z-40 bg-card/95 backdrop-blur-md border-t border-border shadow-[0_-4px_20px_rgba(0,0,0,0.08)]"
          >
            <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3.5 flex flex-col sm:flex-row items-center justify-between gap-2">
              <div className="flex items-center gap-4 text-sm">
                <span className="text-emerald-600 font-semibold">{approvedCount} approved</span>
                <span className="text-red-500 font-semibold">{rejectedCount} rejected</span>
                {pendingCount > 0 && <span className="text-muted-foreground">{pendingCount} pending</span>}
              </div>
              <div className="flex items-center gap-3">
                {allDecided ? (
                  <button
                    onClick={handleAutoAdvance}
                    disabled={processing}
                    className="flex items-center gap-2 bg-emerald-600 text-white px-4 sm:px-5 py-2.5 rounded-lg font-semibold hover:bg-emerald-700 transition-all shadow-md active:scale-[0.97] disabled:opacity-50 text-sm"
                  >
                    {processing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Cpu className="w-4 h-4" />}
                    {processing ? (approvedCount > 0 ? 'Generating...' : 'Submitting...') : (approvedCount > 0 ? `Generate ${approvedCount} Hypothes${approvedCount !== 1 ? 'es' : 'is'}` : 'Submit')}
                    {!processing && <ArrowRight className="w-4 h-4" />}
                  </button>
                ) : (
                  <button onClick={handleSubmit} disabled={processing} className="btn-primary flex items-center gap-2 disabled:opacity-50 text-sm">
                    {processing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                    {processing ? 'Submitting...' : 'Submit Partial'}
                  </button>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {submitted && (
          <motion.div initial={{ y: 50, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 50, opacity: 0 }} className="fixed bottom-16 sm:bottom-6 right-4 sm:right-6 card p-4 bg-emerald-600 text-white shadow-lg z-50">
            <div className="flex items-center gap-2"><CheckCircle className="w-4 h-4" /><span className="text-sm font-medium">Submitted!</span></div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}