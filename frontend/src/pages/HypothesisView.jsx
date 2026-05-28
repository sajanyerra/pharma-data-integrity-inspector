import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Lightbulb, Target, ClipboardList, AlertTriangle, CheckCircle, FileText, ArrowRight, Cpu, Loader2, Shield } from 'lucide-react'
import axios from 'axios'
import { useNavigate } from 'react-router-dom'

import API_BASE from '../api'

export default function HypothesisView() {
  const [hypotheses, setHypotheses] = useState([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [allRejected, setAllRejected] = useState(false)
  const navigate = useNavigate()

  const fetchHypotheses = async () => {
    try {
      const r = await axios.get(`${API_BASE}/anomalies`)
      const allAnomalies = r.data
      const approvedOnes = allAnomalies.filter(a => a.hitl_status === 'approved')
      const rejectedOnes = allAnomalies.filter(a => a.hitl_status === 'rejected')
      const withH = allAnomalies.filter(a => a.hypothesis)
      if (withH.length > 0) {
        setHypotheses(withH.map(a => ({
          anomaly_id: a.id,
          tag_id: a.tag_id,
          anomaly_type: a.anomaly_type,
          root_cause: a.hypothesis,
          confidence: a.confidence,
          recommended_action: a.recommended_action || '',
          alternative_causes: [],
          pharma_impact: '',
        })))
      } else if (approvedOnes.length === 0 && rejectedOnes.length > 0) {
        setAllRejected(true)
      }
      setLoading(false)
    } catch { setLoading(false) }
  }

  useEffect(() => { fetchHypotheses() }, [])

  const generateHypotheses = async () => {
    setGenerating(true)
    try {
      const startRes = await axios.post(`${API_BASE}/generate-hypotheses`)
      const jobId = startRes.data.job_id
      if (!jobId) { setGenerating(false); alert('Failed to start hypothesis generation.'); return }
      let pollAttempts = 0
      const poll = setInterval(async () => {
        pollAttempts++
        if (pollAttempts > 60) { clearInterval(poll); setGenerating(false); alert('Timed out.'); return }
        try {
          const statusRes = await axios.get(`${API_BASE}/analyze/status/${jobId}`)
          const { status, error } = statusRes.data
          if (status === 'completed') {
            clearInterval(poll)
            setGenerating(false)
            await fetchHypotheses()
          } else if (status === 'failed') {
            clearInterval(poll)
            setGenerating(false)
            alert('Hypothesis generation failed: ' + (error || 'Unknown error'))
          }
        } catch (err) { clearInterval(poll); setGenerating(false); alert('Polling error: ' + (err.message || 'Network error')) }
      }, 3000)
    } catch (err) { setGenerating(false); alert('Failed to start: ' + (err.message || 'Network error')) }
  }

  if (loading) {
    return (
      <div className="space-y-5">
        <h1 className="text-2xl font-bold text-foreground">Root Cause Hypotheses</h1>
        <div className="grid gap-4">{Array(3).fill(0).map((_, i) => <div key={i} className="card p-6 animate-pulse"><div className="h-6 bg-secondary rounded w-1/3 mb-4" /><div className="h-4 bg-secondary rounded w-full mb-2" /><div className="h-4 bg-secondary rounded w-3/4" /></div>)}</div>
      </div>
    )
  }

  if (hypotheses.length === 0) {
    if (allRejected) {
      return (
        <div className="space-y-5">
          <h1 className="text-2xl font-bold text-foreground">Root Cause Hypotheses</h1>
          <div className="card p-10 text-center">
            <Shield className="w-12 h-12 text-muted-foreground mx-auto mb-3" />
            <h3 className="text-base font-semibold text-foreground">All anomalies rejected</h3>
            <p className="text-sm text-muted-foreground mt-1">No approved anomalies to hypothesize about. You can still generate a clean report.</p>
            <button onClick={() => navigate('/reports')} className="btn-primary mt-4">
              Continue to Report
            </button>
          </div>
        </div>
      )
    }
    return (
      <div className="space-y-5">
        <h1 className="text-2xl font-bold text-foreground">Root Cause Hypotheses</h1>
        <div className="card p-10 text-center">
          <Lightbulb className="w-12 h-12 text-muted-foreground mx-auto mb-3" />
          <h3 className="text-base font-semibold text-foreground">Ready to generate hypotheses</h3>
          <p className="text-sm text-muted-foreground mt-1">Click below to let Stage 4: Hypothesis Agent analyze approved anomalies</p>
          <button onClick={generateHypotheses} disabled={generating} className="btn-primary mt-4">
            {generating ? <span className="flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" />Generating...</span> : 'Generate Hypotheses'}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Root Cause Hypotheses</h1>
        <p className="text-muted-foreground text-sm mt-0.5">{hypotheses.length} root cause{hypotheses.length !== 1 ? 's' : ''} identified</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="card p-3"><p className="text-[10px] text-muted-foreground uppercase tracking-wider">Total</p><p className="text-2xl font-bold text-foreground mt-0.5">{hypotheses.length}</p></div>
        <div className="card p-3"><p className="text-[10px] text-muted-foreground uppercase tracking-wider">High confidence</p><p className="text-2xl font-bold text-emerald-600 mt-0.5">{hypotheses.filter(h => h.confidence > 0.7).length}</p></div>
        <div className="card p-3"><p className="text-[10px] text-muted-foreground uppercase tracking-wider">Actions</p><p className="text-2xl font-bold text-blue-600 mt-0.5">{hypotheses.length}</p></div>
      </div>

      <div className="flex items-start gap-2 px-1">
        <Shield className="w-3.5 h-3.5 text-emerald-600 shrink-0 mt-0.5" />
        <span className="text-xs sm:text-[10px] text-muted-foreground">All outputs sanitized by guardrail — PII, credentials, batch numbers, and unsafe recommendations are blocked.</span>
      </div>

      <div className="grid gap-5">
        {hypotheses.map((h, index) => (
          <motion.div key={h.tag_id || index} initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.08 }} className="card overflow-hidden">
            {/* Header */}
            <div className="px-4 sm:px-5 py-3 bg-gradient-to-r from-blue-50 to-purple-50 dark:from-blue-900/20 dark:to-purple-900/20 border-b border-border">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
                  <Lightbulb className="w-4 h-4 text-white" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-bold text-foreground">{h.tag_id}</h3>
                  <p className="text-xs text-muted-foreground">{h.anomaly_type?.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</p>
                </div>
                <span className={`px-2.5 py-1 rounded-full text-xs font-bold shrink-0 ${h.confidence > 0.7 ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' : h.confidence > 0.5 ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300' : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'}`}>
                  {(h.confidence * 100).toFixed(0)}%
                </span>
              </div>
            </div>

            {/* Body */}
            <div className="p-4 sm:p-5 space-y-4">
              {/* Root Cause */}
              <div>
                <div className="flex items-center gap-1.5 mb-2">
                  <Target className="w-4 h-4 text-blue-600" />
                  <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Root Cause</span>
                </div>
                <p className="text-sm sm:text-base font-semibold text-foreground leading-relaxed">{h.root_cause}</p>
              </div>

              {/* Recommended Action */}
              <div>
                <div className="flex items-center gap-1.5 mb-2">
                  <ClipboardList className="w-4 h-4 text-emerald-600" />
                  <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Recommended Action</span>
                </div>
                <p className="text-sm text-foreground leading-relaxed">{h.recommended_action}</p>
              </div>

              {/* Alternative Causes */}
              {h.alternative_causes?.length > 0 && (
                <div>
                  <div className="flex items-center gap-1.5 mb-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 text-yellow-600" />
                    <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Alternatives</span>
                  </div>
                  <ul className="space-y-1">
                    {h.alternative_causes.map((cause, i) => (
                      <li key={i} className="text-xs text-muted-foreground flex items-start gap-2"><span className="text-muted-foreground/50 mt-0.5">·</span><span>{cause}</span></li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Pharma Impact */}
              {h.pharma_impact && (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 text-red-600 mt-0.5 shrink-0" />
                    <div><span className="text-[10px] font-bold text-red-900 dark:text-red-300 uppercase tracking-wider">Pharma Impact</span><p className="text-sm text-red-700 dark:text-red-400 mt-1">{h.pharma_impact}</p></div>
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        ))}
      </div>

      {hypotheses.length > 0 && (
        <div className="next-step">
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-orange-600" />
            <span className="text-sm font-medium text-foreground">Next: compliance reports</span>
          </div>
          <button onClick={() => navigate('/reports')} className="next-step-btn"><ArrowRight className="w-4 h-4" /></button>
        </div>
      )}
    </div>
  )
}