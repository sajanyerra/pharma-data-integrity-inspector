import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Eye, EyeOff, ChevronDown, ChevronRight, Activity, Database, Brain, FileText, Search, Filter } from 'lucide-react'
import axios from 'axios'

import API_BASE from '../api'

const AGENT_ICONS = {
  DetectionEngine: Database,
  InvestigationAgent: Search,
  HypothesisAgent: Activity,
  ReportGenerator: FileText,
}

const AGENT_COLORS = {
  DetectionEngine: 'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-900/30 dark:text-blue-300 dark:border-blue-800',
  InvestigationAgent: 'bg-purple-100 text-purple-700 border-purple-200 dark:bg-purple-900/30 dark:text-purple-300 dark:border-purple-800',
  HypothesisAgent: 'bg-green-100 text-green-700 border-green-200 dark:bg-green-900/30 dark:text-green-300 dark:border-green-800',
  ReportGenerator: 'bg-orange-100 text-orange-700 border-orange-200 dark:bg-orange-900/30 dark:text-orange-300 dark:border-orange-800',
}

const AGENT_DESCRIPTIONS = {
  DetectionEngine: { title: 'Stage 1: Detection Engine', what: '9 deterministic rule checks. No LLM.', why: 'Deterministic-first ensures 100% coverage and auditability.' },
  InvestigationAgent: { title: 'Stage 2: Investigation Agent (ReAct)', what: 'Investigates anomalies with 4 tools: query_historian, query_events, query_maintenance, query_lab_results. Different anomalies lead to different tool calls.', why: 'Genuine agent reasoning — decides which external systems to query based on anomaly type.' },
  HypothesisAgent: { title: 'Stage 4: Hypothesis Agent', what: 'Single LLM call with investigation findings and domain knowledge base.', why: 'Focused reasoning from collected evidence. Guardrail validates output.' },
  ReportGenerator: { title: 'Stage 5: Report Generator', what: 'Compiles findings into PDF, HTML, JSON. AI writes executive narrative.', why: 'Audit-ready docs for FDA 21 CFR Part 11.' },
}

export default function TraceView() {
  const [traces, setTraces] = useState([])
  const [loading, setLoading] = useState(true)
  const [expandedTraces, setExpandedTraces] = useState({})
  const [agentFilter, setAgentFilter] = useState('all')
  const [traceMode, setTraceMode] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('traceMode') || 'full'
    }
    return 'full'
  })

  useEffect(() => {
    localStorage.setItem('traceMode', traceMode)
  }, [traceMode])

  useEffect(() => {
    const fetchTraces = async () => {
      try {
        const r = await axios.get(`${API_BASE}/trace?limit=50`)
        setTraces(r.data)
        setLoading(false)
      } catch { setLoading(false) }
    }
    fetchTraces()
  }, [])

  const toggleExpand = (id) => { setExpandedTraces(prev => ({ ...prev, [id]: !prev[id] })) }

  const formatJSON = (obj) => {
    try { return JSON.stringify(typeof obj === 'string' ? JSON.parse(obj) : obj, null, 2) }
    catch { return String(obj) }
  }

  const getAgentSummary = (trace) => {
    const out = trace.output || {}
    if (trace.agent_name === 'DetectionEngine') {
      const count = out.tag_profiles ? Object.keys(out.tag_profiles).length : '?'
      const total = out.summary?.total_anomalies || out.anomalies?.length || 0
      return `Profiled ${count} tags, detected ${total} anomalies`
    }
    if (trace.agent_name === 'InvestigationAgent') {
      const tools = out.tools_used || out.tool_calls?.length || 0
      return `Investigated with ${tools} tool calls`
    }
    if (trace.agent_name === 'HypothesisAgent') {
      const total = out.summary?.total_hypotheses || out.hypotheses?.length || 0
      return `Generated ${total} hypotheses`
    }
    if (trace.agent_name === 'ReportGenerator') {
      const formats = [out.pdf_path && 'PDF', out.html_path && 'HTML', out.json_path && 'JSON'].filter(Boolean).join(', ')
      return `Generated ${formats || 'multi-format'} reports`
    }
    return 'Completed'
  }

  const filteredTraces = agentFilter === 'all' ? traces : traces.filter(t => t.agent_name === agentFilter)
  const uniqueAgents = [...new Set(traces.map(t => t.agent_name))]

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Pipeline Trace</h1>
          <p className="text-muted-foreground text-sm mt-0.5">
            {traceMode === 'minimal' ? 'Minimal view — toggle Full for I/O details' : 'Every stage decision logged — expand for I/O'}
          </p>
        </div>
        <div className="flex items-center gap-0.5 bg-secondary rounded-lg p-0.5">
          <button
            onClick={() => setTraceMode('minimal')}
            className={`flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs font-medium transition-colors ${
              traceMode === 'minimal' ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <EyeOff className="w-3 h-3" />Min
          </button>
          <button
            onClick={() => setTraceMode('full')}
            className={`flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs font-medium transition-colors ${
              traceMode === 'full' ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Eye className="w-3 h-3" />Full
          </button>
        </div>
      </div>

      <div className="hint">
        <Search className="w-3.5 h-3.5" />
        <span>Every stage logs inputs, outputs, and reasoning — required for FDA 21 CFR Part 11 auditability.</span>
      </div>

      {traceMode === 'minimal' ? (
        <div className="card p-5">
          <div className="flex items-center gap-1.5 text-muted-foreground mb-4">
            <EyeOff className="w-4 h-4" />
            <span className="text-xs font-medium">Minimal View</span>
          </div>
          <div className="space-y-3">
            {filteredTraces.slice(0, 5).map((trace, index) => {
              const Icon = AGENT_ICONS[trace.agent_name] || Activity
              const colorClass = AGENT_COLORS[trace.agent_name] || 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300'
              const desc = AGENT_DESCRIPTIONS[trace.agent_name]
              return (
                <div key={trace.id} className="flex items-center gap-3 p-2.5 bg-secondary rounded-lg">
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${colorClass}`}><Icon className="w-4 h-4" /></div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-foreground">{desc?.title || trace.agent_name}</span>
                      <span className="text-[10px] text-muted-foreground">#{traces.length - index}</span>
                    </div>
                    <p className="text-xs text-muted-foreground">{getAgentSummary(trace)}</p>
                  </div>
                  <span className="text-[10px] text-muted-foreground">{new Date(trace.created_at).toLocaleTimeString()}</span>
                </div>
              )
            })}
          </div>
          <div className="mt-4 p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
            <p className="text-xs text-blue-800 dark:text-blue-300">Switch to <strong>Full Trace</strong> for complete stage I/O details.</p>
          </div>
        </div>
      ) : (
        <>
          <div className="card p-3">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {Object.entries(AGENT_DESCRIPTIONS).map(([name, desc]) => {
                const Icon = AGENT_ICONS[name]
                const colorClass = AGENT_COLORS[name]
                return (
                  <div key={name} className={`flex items-center gap-2 p-2 rounded-lg border ${colorClass}`}>
                    <Icon className="w-4 h-4 shrink-0" />
                    <div><p className="text-xs font-semibold">{desc.title.split(': ')[1]}</p></div>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="card p-3"><p className="text-xs text-muted-foreground">Runs</p><p className="text-xl font-bold text-foreground">{traces.length}</p></div>
            <div className="card p-3"><p className="text-xs text-muted-foreground">Stages</p><p className="text-xl font-bold text-foreground">{uniqueAgents.length}</p></div>
            <div className="card p-3"><p className="text-xs text-muted-foreground">Latest</p><p className="text-xl font-bold text-foreground">{traces.length > 0 ? `#${traces.length}` : '-'}</p></div>
            <div className="card p-3"><p className="text-xs text-muted-foreground">LangSmith</p><p className="text-[10px] text-muted-foreground mt-1">Dev-only external trace viewer. Your users see this local trace log above. <a href="https://smith.langchain.com" target="_blank" rel="noopener noreferrer" className="text-blue-600 dark:text-blue-400 underline">smith.langchain.com</a> (login required)</p></div>
          </div>

          <div className="flex gap-1.5 items-center flex-wrap">
            <Filter className="w-3.5 h-3.5 text-muted-foreground" />
            <button onClick={() => setAgentFilter('all')} className={`px-2 py-1 rounded-full text-xs font-medium transition-colors ${agentFilter === 'all' ? 'bg-blue-600 text-white' : 'bg-secondary text-muted-foreground'}`}>
              All ({traces.length})
            </button>
            {uniqueAgents.map(name => {
              const count = traces.filter(t => t.agent_name === name).length
              const desc = AGENT_DESCRIPTIONS[name]
              return (
                <button key={name} onClick={() => setAgentFilter(name)} className={`px-2 py-1 rounded-full text-xs font-medium transition-colors ${agentFilter === name ? 'bg-blue-600 text-white' : 'bg-secondary text-muted-foreground'}`}>
                  {desc?.title.split(': ')[1]} ({count})
                </button>
              )
            })}
          </div>

          <div className="card overflow-hidden">
            <div className="px-5 py-3 border-b border-border bg-secondary">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-foreground">Execution Log</h2>
                <div className="flex items-center gap-1.5 text-muted-foreground"><Eye className="w-3.5 h-3.5" /><span className="text-xs">Full Detail</span></div>
              </div>
            </div>

            {loading ? (
              <div className="p-6 space-y-3">{Array(3).fill(0).map((_, i) => <div key={i} className="animate-pulse h-14 bg-secondary rounded-lg" />)}</div>
            ) : filteredTraces.length === 0 ? (
              <div className="p-10 text-center">
                <Activity className="w-12 h-12 text-muted-foreground mx-auto mb-3" />
                <h3 className="text-sm font-semibold text-foreground">No traces yet</h3>
              </div>
            ) : (
              <div className="divide-y divide-border">
                {filteredTraces.map((trace, index) => {
                  const Icon = AGENT_ICONS[trace.agent_name] || Activity
                  const colorClass = AGENT_COLORS[trace.agent_name] || 'bg-gray-100 text-gray-700'
                  const isExpanded = expandedTraces[trace.id]
                  const desc = AGENT_DESCRIPTIONS[trace.agent_name]

                  return (
                    <div key={trace.id} className="p-3">
                      <div onClick={() => toggleExpand(trace.id)} className="flex items-center gap-3 cursor-pointer hover:bg-secondary/50 -mx-3 px-3 py-2 rounded-lg transition-colors">
                        {isExpanded ? <ChevronDown className="w-4 h-4 text-muted-foreground" /> : <ChevronRight className="w-4 h-4 text-muted-foreground" />}
                        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${colorClass}`}><Icon className="w-4 h-4" /></div>
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold text-foreground">{desc?.title || trace.agent_name}</span>
                            <span className="text-[10px] text-muted-foreground">#{traces.length - traces.indexOf(trace)}</span>
                          </div>
                          <p className="text-xs text-muted-foreground">{getAgentSummary(trace)}</p>
                        </div>
                        <span className="text-[10px] text-muted-foreground">{new Date(trace.created_at).toLocaleTimeString()}</span>
                      </div>

                      <AnimatePresence>
                        {isExpanded && (
                          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="mt-3 ml-7 space-y-3">
                            {desc && (
                              <div className={`p-2.5 rounded-lg border ${colorClass}`}>
                                <p className="text-[10px] font-semibold mb-0.5">Why this stage exists:</p>
                                <p className="text-xs opacity-80">{desc.why}</p>
                              </div>
                            )}
                            <div>
                              <h4 className="text-[10px] font-semibold text-muted-foreground uppercase mb-1">Input</h4>
                              <pre className="bg-secondary border border-border rounded-lg p-2.5 text-[10px] text-foreground overflow-x-auto max-h-48 overflow-y-auto">{formatJSON(trace.input)}</pre>
                            </div>
                            <div>
                              <h4 className="text-[10px] font-semibold text-muted-foreground uppercase mb-1">Output</h4>
                              <pre className="bg-secondary border border-border rounded-lg p-2.5 text-[10px] text-foreground overflow-x-auto max-h-48 overflow-y-auto">{formatJSON(trace.output)}</pre>
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}