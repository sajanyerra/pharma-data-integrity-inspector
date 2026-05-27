import { useState } from 'react'
import { motion } from 'framer-motion'
import { FileText, Download, FileJson, FileCode, Eye, CheckCircle, Bot, Home } from 'lucide-react'
import axios from 'axios'
import { useNavigate } from 'react-router-dom'

import API_BASE from '../api'

export default function ReportPreview() {
  const [generating, setGenerating] = useState(false)
  const [generated, setGenerated] = useState(false)
  const [reports, setReports] = useState(null)
  const navigate = useNavigate()

  const generateReports = async () => {
    setGenerating(true)
    try {
      const startRes = await axios.post(`${API_BASE}/generate-reports`)
      const jobId = startRes.data.job_id
      if (!jobId) { setGenerating(false); alert('Failed to start report generation.'); return }
      let pollAttempts = 0
      const poll = setInterval(async () => {
        pollAttempts++
        if (pollAttempts > 60) { clearInterval(poll); setGenerating(false); alert('Timed out.'); return }
        try {
          const statusRes = await axios.get(`${API_BASE}/analyze/status/${jobId}`)
          const { status, result, error } = statusRes.data
          if (status === 'completed') {
            clearInterval(poll)
            setGenerating(false)
            if (result && result.reports) {
              setReports(result.reports)
              setGenerated(true)
            }
          } else if (status === 'failed') {
            clearInterval(poll)
            setGenerating(false)
            alert('Report generation failed: ' + (error || 'Unknown error'))
          }
        } catch (err) { clearInterval(poll); setGenerating(false); alert('Polling error: ' + (err.message || 'Network error')) }
      }, 3000)
    } catch (err) { setGenerating(false); alert('Failed to start: ' + (err.message || 'Network error')) }
  }

  const downloadReport = async (type) => {
    try {
      const r = await axios.get(`${API_BASE}/reports/download/${type}`, { responseType: 'blob' })
      const url = window.URL.createObjectURL(new Blob([r.data]))
      const link = document.createElement('a')
      link.href = url
      const cd = r.headers['content-disposition']
      const filename = cd ? cd.split('filename=')[1] : `report.${type}`
      link.setAttribute('download', filename.replace(/"/g, ''))
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch {}
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Reports</h1>
        <p className="text-muted-foreground text-sm mt-0.5">Audit-ready compliance documentation</p>
      </div>

      <div className="hint">
        <Bot className="w-3.5 h-3.5" />
        <span>Agent 3 packages findings into 3 formats for FDA 21 CFR Part 11 compliance.</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <motion.div whileHover={{ scale: 1.02 }} className="card p-5 cursor-pointer hover:shadow-lg transition-shadow" onClick={() => generated && downloadReport('pdf')}>
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 bg-red-100 dark:bg-red-900/30 rounded-lg flex items-center justify-center">
              <FileText className="w-5 h-5 text-red-600" />
            </div>
            <div>
              <h3 className="font-semibold text-foreground text-sm">Executive Summary</h3>
              <p className="text-xs text-muted-foreground">PDF</p>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">One-page overview for plant managers and executives.</p>
          {generated && <div className="mt-3 flex items-center gap-1.5 text-emerald-600 text-xs"><Download className="w-3.5 h-3.5" />Click to download</div>}
        </motion.div>

        <motion.div whileHover={{ scale: 1.02 }} className="card p-5 cursor-pointer hover:shadow-lg transition-shadow" onClick={() => generated && downloadReport('html')}>
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 bg-blue-100 dark:bg-blue-900/30 rounded-lg flex items-center justify-center">
              <Eye className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <h3 className="font-semibold text-foreground text-sm">Detailed Report</h3>
              <p className="text-xs text-muted-foreground">HTML</p>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">Full technical details for engineering teams.</p>
          {generated && <div className="mt-3 flex items-center gap-1.5 text-emerald-600 text-xs"><Download className="w-3.5 h-3.5" />Click to download</div>}
        </motion.div>

        <motion.div whileHover={{ scale: 1.02 }} className="card p-5 cursor-pointer hover:shadow-lg transition-shadow" onClick={() => generated && downloadReport('json')}>
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 bg-purple-100 dark:bg-purple-900/30 rounded-lg flex items-center justify-center">
              <FileCode className="w-5 h-5 text-purple-600" />
            </div>
            <div>
              <h3 className="font-semibold text-foreground text-sm">Raw Data Export</h3>
              <p className="text-xs text-muted-foreground">JSON</p>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">Machine-readable for integration and archival.</p>
          {generated && <div className="mt-3 flex items-center gap-1.5 text-emerald-600 text-xs"><Download className="w-3.5 h-3.5" />Click to download</div>}
        </motion.div>
      </div>

      <div className="card p-4 bg-secondary">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-foreground">Generate All Reports</h3>
            <p className="text-xs text-muted-foreground mt-0.5">Creates PDF, HTML, and JSON from current data</p>
          </div>
          <button onClick={generateReports} disabled={generating} className="btn-primary flex items-center gap-2 disabled:opacity-50">
            <FileJson className="w-4 h-4" />
            {generating ? 'Generating...' : 'Generate Reports'}
          </button>
        </div>
      </div>

      {generated && reports && (
        <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} className="card overflow-hidden">
          <div className="px-5 py-3 border-b border-border bg-emerald-50 dark:bg-emerald-900/20">
            <div className="flex items-center gap-2">
              <CheckCircle className="w-4 h-4 text-emerald-600" />
              <h2 className="text-sm font-semibold text-emerald-900 dark:text-emerald-300">Reports Generated</h2>
            </div>
          </div>
          <div className="p-5 space-y-2">
            {reports.pdf && (
              <div className="flex items-center justify-between p-2.5 bg-secondary rounded-lg">
                <div className="flex items-center gap-2.5"><FileText className="w-4 h-4 text-red-600" /><span className="text-sm font-medium text-foreground">{reports.pdf.split('/').pop()}</span></div>
                <button onClick={() => downloadReport('pdf')} className="btn-secondary text-xs">PDF</button>
              </div>
            )}
            {reports.html && (
              <div className="flex items-center justify-between p-2.5 bg-secondary rounded-lg">
                <div className="flex items-center gap-2.5"><Eye className="w-4 h-4 text-blue-600" /><span className="text-sm font-medium text-foreground">{reports.html.split('/').pop()}</span></div>
                <button onClick={() => downloadReport('html')} className="btn-secondary text-xs">HTML</button>
              </div>
            )}
            {reports.json && (
              <div className="flex items-center justify-between p-2.5 bg-secondary rounded-lg">
                <div className="flex items-center gap-2.5"><FileCode className="w-4 h-4 text-purple-600" /><span className="text-sm font-medium text-foreground">{reports.json.split('/').pop()}</span></div>
                <button onClick={() => downloadReport('json')} className="btn-secondary text-xs">JSON</button>
              </div>
            )}
          </div>
        </motion.div>
      )}

      <div className="next-step">
        <div className="flex items-center gap-2">
          <Home className="w-5 h-5 text-blue-600" />
          <span className="text-sm font-medium text-foreground">Pipeline complete — return to dashboard</span>
        </div>
        <button onClick={() => navigate('/')} className="next-step-btn"><Home className="w-4 h-4" /></button>
      </div>
    </div>
  )
}