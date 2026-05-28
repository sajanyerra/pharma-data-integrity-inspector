import { useState, useEffect, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ChevronDown, ChevronRight, Brain, Shield, Cpu, Database,
  AlertTriangle, BarChart3, Zap, BookOpen, Eye, Layers,
  Link2, Activity, FileText, Lock, Unlock
} from 'lucide-react'
import axios from 'axios'

import API_BASE from '../api'

const SECTION_ICON = {
  checks: Shield,
  correlations: Link2,
  causal: Layers,
  pipeline: Cpu,
  techstack: Zap,
  silentlie: Eye,
  guardrail: Lock,
  hitl: Unlock,
  faq: BookOpen,
}

const CELL_COLORS = [
  { bg: 'bg-blue-900', text: 'text-blue-100' },
  { bg: 'bg-blue-700', text: 'text-blue-100' },
  { bg: 'bg-blue-500', text: 'text-white' },
  { bg: 'bg-blue-300', text: 'text-blue-900' },
  { bg: 'bg-blue-100', text: 'text-blue-900' },
  { bg: 'bg-gray-100 dark:bg-gray-800', text: 'text-gray-400' },
  { bg: 'bg-red-100', text: 'text-red-900' },
  { bg: 'bg-red-300', text: 'text-red-900' },
  { bg: 'bg-red-500', text: 'text-white' },
  { bg: 'bg-red-700', text: 'text-red-100' },
  { bg: 'bg-red-900', text: 'text-red-100' },
]

function correlationToColor(r) {
  if (r === null || r === undefined) return { bg: 'bg-gray-100 dark:bg-gray-800', text: 'text-gray-400 dark:text-gray-500' }
  const abs = Math.abs(r)
  if (r >= 0) {
    if (abs >= 0.9) return { bg: 'bg-blue-800 dark:bg-blue-900', text: 'text-blue-100' }
    if (abs >= 0.7) return { bg: 'bg-blue-600 dark:bg-blue-700', text: 'text-white' }
    if (abs >= 0.5) return { bg: 'bg-blue-400 dark:bg-blue-500', text: 'text-white' }
    if (abs >= 0.3) return { bg: 'bg-blue-200 dark:bg-blue-400/60', text: 'text-blue-900 dark:text-blue-100' }
    return { bg: 'bg-blue-50 dark:bg-blue-900/30', text: 'text-blue-900 dark:text-blue-200' }
  } else {
    const a = Math.abs(r)
    if (a >= 0.9) return { bg: 'bg-red-800 dark:bg-red-900', text: 'text-red-100' }
    if (a >= 0.7) return { bg: 'bg-red-600 dark:bg-red-700', text: 'text-white' }
    if (a >= 0.5) return { bg: 'bg-red-400 dark:bg-red-500', text: 'text-white' }
    if (a >= 0.3) return { bg: 'bg-red-200 dark:bg-red-400/60', text: 'text-red-900 dark:text-red-100' }
    return { bg: 'bg-red-50 dark:bg-red-900/30', text: 'text-red-900 dark:text-red-200' }
  }
}

function CorrelationMatrix({ correlations }) {
  const allTags = useMemo(() => {
    const tagSet = new Set()
    correlations.forEach(c => { tagSet.add(c.tag_a); tagSet.add(c.tag_b) })
    return [...tagSet].sort()
  }, [correlations])

  const matrix = useMemo(() => {
    const lookup = {}
    correlations.forEach(c => {
      lookup[`${c.tag_a}|${c.tag_b}`] = c
      lookup[`${c.tag_b}|${c.tag_a}`] = c
    })
    const m = {}
    allTags.forEach(a => {
      m[a] = {}
      allTags.forEach(b => {
        if (a === b) { m[a][b] = { correlation: 1.0, p_value: 0, n: 0 } }
        else { m[a][b] = lookup[`${a}|${b}`] || null }
      })
    })
    return m
  }, [correlations, allTags])

  const tagShort = (t) => t

  return (
    <div className="overflow-x-auto">
      <div className="min-w-fit">
        <div className="flex items-center gap-1 mb-2 justify-end">
          <span className="text-[10px] text-muted-foreground">Correlation</span>
          <div className="flex gap-0.5">
            {[
              { label: '-1', bg: 'bg-red-700', text: 'text-red-100' },
              { label: '0', bg: 'bg-gray-200 dark:bg-gray-700', text: 'text-gray-600 dark:text-gray-300' },
              { label: '+1', bg: 'bg-blue-700', text: 'text-blue-100' },
            ].map(s => (
              <div key={s.label} className={`w-6 h-4 ${s.bg} ${s.text} flex items-center justify-center text-[8px] font-bold rounded-sm`}>{s.label}</div>
            ))}
          </div>
        </div>
        <table className="border-collapse text-[10px]">
          <thead>
            <tr>
              <th className="p-0.5 text-left text-[10px] font-mono text-muted-foreground"></th>
              {allTags.map(t => (
                <th key={t} className="p-0.5 text-center font-mono text-muted-foreground whitespace-nowrap" style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)', height: '60px' }}>
                  <span className="text-[9px]">{tagShort(t)}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {allTags.map(rowTag => (
              <tr key={rowTag}>
                <td className="p-0.5 text-right font-mono text-muted-foreground whitespace-nowrap pr-1">{tagShort(rowTag)}</td>
                {allTags.map(colTag => {
                  const cell = matrix[rowTag]?.[colTag]
                  const r = cell?.correlation
                  const isDiag = rowTag === colTag
                  const isData = cell !== null && cell !== undefined
                  const colors = isDiag ? { bg: 'bg-gray-300 dark:bg-gray-600', text: 'text-gray-700 dark:text-gray-300' } : correlationToColor(r)
                  return (
                    <td
                      key={colTag}
                      className={`p-0.5 ${colors.bg} ${colors.text} text-center font-mono rounded-sm border border-white dark:border-gray-900`}
                      title={isData && !isDiag ? `${tagShort(rowTag)} ↔ ${tagShort(colTag)}\nr = ${r !== null ? r.toFixed(4) : 'N/A'}${cell?.p_value !== null && cell?.p_value !== undefined ? `\np = ${cell.p_value < 0.001 ? '<0.001' : cell.p_value.toFixed(4)}` : ''}\nn = ${cell?.n || 'N/A'}` : (isDiag ? 'Diagonal (r=1.0)' : 'No data')}
                    >
                      <div className="w-8 h-6 flex items-center justify-center text-[10px] font-semibold">
                        {isDiag ? '—' : (r !== null && r !== undefined ? r.toFixed(2) : '·')}
                      </div>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <div className="flex items-center gap-3 mt-3 text-[10px] text-muted-foreground">
          <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm bg-blue-600 dark:bg-blue-700 inline-block" /> Strong positive (r &gt; 0.7)</span>
          <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm bg-red-600 dark:bg-red-700 inline-block" /> Strong negative (r &lt; -0.7)</span>
          <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm bg-gray-200 dark:bg-gray-700 inline-block" /> No data</span>
        </div>
        <p className="text-[10px] text-muted-foreground mt-2">Pearson r computed from last 24h of stored tag_readings (LIMIT 2000 per pair). Hover cells for p-value and sample size.</p>
      </div>
    </div>
  )
}

export default function StatsForNerds() {
  const [checks, setChecks] = useState([])
  const [correlations, setCorrelations] = useState([])
  const [causalGroups, setCausalGroups] = useState(null)
  const [pipeline, setPipeline] = useState(null)
  const [techStack, setTechStack] = useState([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState({})

  useEffect(() => {
    const fetch = async () => {
      try {
        const [checksRes, corrRes, causalRes, pipelineRes, techRes] = await Promise.all([
          axios.get(`${API_BASE}/stats/integrity-checks`),
          axios.get(`${API_BASE}/stats/correlations`),
          axios.get(`${API_BASE}/stats/causal-groups`),
          axios.get(`${API_BASE}/stats/pipeline`),
          axios.get(`${API_BASE}/stats/tech-stack`),
        ])
        setChecks(checksRes.data)
        setCorrelations(corrRes.data)
        setCausalGroups(causalRes.data)
        setPipeline(pipelineRes.data)
        setTechStack(techRes.data)
      } catch {}
      setLoading(false)
    }
    fetch()
  }, [])

  const toggle = (key) => setExpanded(prev => ({ ...prev, [key]: !prev[key] }))

  if (loading) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-foreground">Stats for Nerds</h1>
        <div className="space-y-3">{Array(5).fill(0).map((_, i) => <div key={i} className="animate-pulse h-24 bg-secondary rounded-xl" />)}</div>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Stats for Nerds</h1>
        <p className="text-muted-foreground text-sm mt-0.5">How it works — under the hood</p>
      </div>

      {/* SILENT LIE — hero section */}
      <div className="card p-5 border-2 border-indigo-300 dark:border-indigo-700 relative overflow-hidden">
        <div className="absolute top-0 left-0 w-1.5 h-full bg-indigo-500" />
        <div className="pl-3">
          <div className="flex items-center gap-2 mb-3">
            <Eye className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
            <h2 className="text-base font-bold text-foreground">Cross-Sensor Corroboration</h2>
            <span className="text-[10px] font-bold uppercase tracking-wider bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-300 px-1.5 py-0.5 rounded">Novel</span>
          </div>
          <div className="bg-white dark:bg-slate-800 p-3 rounded-lg mb-3 text-xs space-y-1.5">
            <p className="text-foreground font-semibold">Your temp sensor reads 172°C. Normal range, Good quality code, passes every check. But the pressure and flow sensors contradict it — the real temperature is 175°C.</p>
            <p className="text-amber-700 dark:text-amber-400 font-semibold">The sensor is wrong by 3°C. Cross-sensor corroboration catches what threshold checks miss.</p>
          </div>
          <div className="bg-secondary p-3 rounded-lg mb-3 text-xs text-muted-foreground space-y-1.5">
            <p><strong className="text-foreground">Why this is dangerous:</strong> You released a batch based on temperature data that was wrong. The actual process was 3°C hotter. In pharma, that difference can invalidate a batch.</p>
            <p><strong className="text-foreground">Why tools miss this:</strong> Historians check each sensor in isolation (thresholds, quality codes). Analytics tools assume data is correct. Nobody cross-references physically coupled sensors to ask: "Does this reading make sense given what the other sensors show?"</p>
            <p><strong className="text-foreground">How we catch it:</strong> Check 9 segments the correlation timeline between a suspect tag and its physically-coupled witnesses. When the correlation pattern changes and trends contradict the expected physical relationship, we flag it — even though the reading itself looks perfectly normal.</p>
          </div>
          {causalGroups?.silent_lie && (
            <div className="text-xs text-muted-foreground">
              <span className="font-semibold text-foreground">Injected in this demo:</span> {causalGroups.silent_lie.tag_id} miscalibrated by {causalGroups.silent_lie.offset}°C from {String(causalGroups.silent_lie.start_hour).padStart(2, '0')}:{String(causalGroups.silent_lie.start_minute).padStart(2, '0')} for {Math.round(causalGroups.silent_lie.duration_hours)}h. {causalGroups.silent_lie.desc}
            </div>
          )}
        </div>
      </div>

      {/* 11 Integrity Checks */}
      <div className="card overflow-hidden">
        <button onClick={() => toggle('checks')} className="w-full px-5 py-4 flex items-center justify-between hover:bg-secondary/50 transition-colors">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            <h2 className="text-sm font-bold text-foreground">9 Integrity Checks</h2>
            <span className="text-[10px] text-muted-foreground">({checks.length} checks)</span>
          </div>
          {expanded.checks ? <ChevronDown className="w-4 h-4 text-muted-foreground" /> : <ChevronRight className="w-4 h-4 text-muted-foreground" />}
        </button>
        <AnimatePresence>
          {expanded.checks && (
            <motion.div initial={{ height: 0 }} animate={{ height: 'auto' }} exit={{ height: 0 }} className="overflow-hidden">
              <div className="px-5 pb-4 space-y-2">
          {checks.map(c => (
              <div key={c.id} className={`p-3 rounded-lg border ${c.is_novel ? 'border-indigo-300 dark:border-indigo-700 bg-indigo-50 dark:bg-indigo-900/10' : 'border-border bg-secondary'}`}>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[10px] font-bold text-muted-foreground w-5">#{c.id}</span>
                  <span className="text-xs font-semibold text-foreground">{c.name}</span>
                  {c.is_novel && <span className="text-[9px] font-bold uppercase tracking-wider bg-indigo-200 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-300 px-1 py-0.5 rounded">Novel</span>}
                </div>
                <p className="text-[11px] text-muted-foreground mb-0.5"><strong className="text-foreground">Detects:</strong> {c.detects}</p>
                <p className="text-[11px] text-muted-foreground mb-0.5"><strong className="text-foreground">Method:</strong> {c.method}</p>
                <p className="text-[11px] text-muted-foreground"><strong className="text-foreground">Threshold:</strong> {c.threshold}</p>
                {c.is_novel && <p className="text-[11px] text-indigo-700 dark:text-indigo-300 mt-1">{c.why_novel}</p>}
              </div>
            ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Correlation Matrix — proper NxN grid */}
      <div className="card overflow-hidden">
        <button onClick={() => toggle('correlations')} className="w-full px-5 py-4 flex items-center justify-between hover:bg-secondary/50 transition-colors">
          <div className="flex items-center gap-2">
            <Link2 className="w-4 h-4 text-purple-600 dark:text-purple-400" />
            <h2 className="text-sm font-bold text-foreground">Live Correlation Matrix</h2>
            <span className="text-[10px] text-muted-foreground">({correlations.length} pairs)</span>
          </div>
          {expanded.correlations ? <ChevronDown className="w-4 h-4 text-muted-foreground" /> : <ChevronRight className="w-4 h-4 text-muted-foreground" />}
        </button>
        <AnimatePresence>
          {expanded.correlations && (
            <motion.div initial={{ height: 0 }} animate={{ height: 'auto' }} exit={{ height: 0 }} className="overflow-hidden">
              <div className="px-5 pb-4">
                <CorrelationMatrix correlations={correlations} />
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Causal Groups */}
      <div className="card overflow-hidden">
        <button onClick={() => toggle('causal')} className="w-full px-5 py-4 flex items-center justify-between hover:bg-secondary/50 transition-colors">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-green-600 dark:text-green-400" />
            <h2 className="text-sm font-bold text-foreground">Causal Group Model</h2>
            <span className="text-[10px] text-muted-foreground">({causalGroups ? Object.keys(causalGroups.causal_groups).length : '?'} groups)</span>
          </div>
          {expanded.causal ? <ChevronDown className="w-4 h-4 text-muted-foreground" /> : <ChevronRight className="w-4 h-4 text-muted-foreground" />}
        </button>
        <AnimatePresence>
          {expanded.causal && causalGroups && (
            <motion.div initial={{ height: 0 }} animate={{ height: 'auto' }} exit={{ height: 0 }} className="overflow-hidden">
              <div className="px-5 pb-4 space-y-3">
                <p className="text-xs text-muted-foreground mb-2">Tags within the same equipment unit are causally coupled. When one deviates, the others respond according to physics. The coupling coefficients determine the strength and direction of the response.</p>
                {Object.entries(causalGroups.causal_groups).filter(([k]) => k !== '_cross_group').map(([name, group]) => (
                  <div key={name} className="p-3 rounded-lg border border-border bg-secondary">
                    <h3 className="text-xs font-bold text-foreground mb-2">{name}</h3>
                    <div className="flex flex-wrap gap-1.5 mb-2">
                      {group.tags.map(t => (
                        <span key={t} className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-card border border-border text-foreground">{t}</span>
                      ))}
                    </div>
                    {Object.entries(group.couplings).map(([key, coupling]) => (
                      <div key={key} className="ml-2 mb-1.5 flex items-start gap-2">
                        <span className="text-[10px] font-mono text-muted-foreground">{key}</span>
                        <span className="text-[11px] text-foreground">coeff={coupling.coeff}</span>
                        <span className="text-[10px] text-muted-foreground italic">{coupling.desc}</span>
                      </div>
                    ))}
                  </div>
                ))}
                {causalGroups.causal_groups._cross_groups && Object.keys(causalGroups.causal_groups._cross_groups).length > 0 && (
                  <div className="p-3 rounded-lg border border-dashed border-border bg-secondary">
                    <h3 className="text-xs font-bold text-foreground mb-2">Cross-Group Couplings</h3>
                    {Object.entries(causalGroups.causal_groups._cross_groups).map(([key, coupling]) => (
                      <div key={key} className="ml-2 mb-1.5 flex items-start gap-2">
                        <span className="text-[10px] font-mono text-muted-foreground">{key}</span>
                        <span className="text-[11px] text-foreground">coeff={coupling.coeff}</span>
                        <span className="text-[10px] text-muted-foreground italic">{coupling.desc}</span>
                        <span className="text-[9px] text-muted-foreground">({coupling.source_group} → {coupling.target_group})</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Tech Stack */}
      <div className="card overflow-hidden">
        <button onClick={() => toggle('techstack')} className="w-full px-5 py-4 flex items-center justify-between hover:bg-secondary/50 transition-colors">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-amber-600 dark:text-amber-400" />
            <h2 className="text-sm font-bold text-foreground">Tech Stack</h2>
            <span className="text-[10px] text-muted-foreground">{techStack.length} categories</span>
          </div>
          {expanded.techstack ? <ChevronDown className="w-4 h-4 text-muted-foreground" /> : <ChevronRight className="w-4 h-4 text-muted-foreground" />}
        </button>
        <AnimatePresence>
          {expanded.techstack && (
            <motion.div initial={{ height: 0 }} animate={{ height: 'auto' }} exit={{ height: 0 }} className="overflow-hidden">
              <div className="px-5 pb-4 space-y-4">
                <p className="text-xs text-muted-foreground">Every technology that makes this work — from LLM orchestration to the output guardrail. No black boxes.</p>
                {techStack.map((category) => (
                  <div key={category.category}>
                    <h3 className="text-xs font-bold text-foreground mb-2">{category.category}</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      {category.items.map((item) => (
                        <div key={item.name} className="p-2.5 rounded-lg border border-border bg-secondary">
                          <p className="text-xs font-semibold text-foreground">{item.name}</p>
                          <p className="text-[11px] text-muted-foreground mt-0.5">{item.role}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Pipeline Architecture */}
      <div className="card overflow-hidden">
        <button onClick={() => toggle('pipeline')} className="w-full px-5 py-4 flex items-center justify-between hover:bg-secondary/50 transition-colors">
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-orange-600 dark:text-orange-400" />
            <h2 className="text-sm font-bold text-foreground">Pipeline Architecture</h2>
          </div>
          {expanded.pipeline ? <ChevronDown className="w-4 h-4 text-muted-foreground" /> : <ChevronRight className="w-4 h-4 text-muted-foreground" />}
        </button>
        <AnimatePresence>
          {expanded.pipeline && pipeline && (
            <motion.div initial={{ height: 0 }} animate={{ height: 'auto' }} exit={{ height: 0 }} className="overflow-hidden">
              <div className="px-5 pb-4 space-y-3">
                <div className="p-3 rounded-lg bg-secondary">
                  <p className="text-[10px] font-bold text-muted-foreground uppercase mb-1">Orchestration</p>
                  <p className="text-xs text-foreground">{pipeline.orchestration}</p>
                </div>
                <div className="space-y-2">
                  <p className="text-[10px] font-bold text-muted-foreground uppercase">5 Stages</p>
                  {(pipeline.stages || pipeline.agents || []).map(a => (
                    <div key={a.id} className="p-3 rounded-lg border border-border">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-bold text-foreground">Stage {a.id}: {a.name}</span>
                      </div>
                      <p className="text-[10px] text-muted-foreground mb-1"><strong className="text-foreground">Engine:</strong> {a.engine}</p>
                      <p className="text-[10px] text-muted-foreground"><strong className="text-foreground">Flow:</strong> {a.flow}</p>
                    </div>
                  ))}
                </div>

                <div className="p-3 rounded-lg border border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-900/10">
                  <div className="flex items-center gap-2 mb-2">
                    <Lock className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                    <p className="text-xs font-bold text-foreground">Output Guardrail</p>
                  </div>
                  <ul className="space-y-0.5">
                    {pipeline.guardrail.checks.map((c, i) => (
                      <li key={i} className="text-[10px] text-muted-foreground">&#8226; {c}</li>
                    ))}
                  </ul>
                  <p className="text-[10px] text-muted-foreground mt-1">Applied to: {pipeline.guardrail.applied_to.join(', ')}</p>
                </div>

                <div className="p-3 rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/10">
                  <div className="flex items-center gap-2 mb-2">
                    <Unlock className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
                    <p className="text-xs font-bold text-foreground">Human-in-the-Loop Gate</p>
                  </div>
                  <p className="text-[10px] text-muted-foreground mb-1">{pipeline.hitl.purpose}</p>
                  <p className="text-[10px] text-muted-foreground">Position: {pipeline.hitl.position}</p>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* FAQ */}
      <div className="card overflow-hidden">
        <button onClick={() => toggle('faq')} className="w-full px-5 py-4 flex items-center justify-between hover:bg-secondary/50 transition-colors">
          <div className="flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
            <h2 className="text-sm font-bold text-foreground">FAQ</h2>
          </div>
          {expanded.faq ? <ChevronDown className="w-4 h-4 text-muted-foreground" /> : <ChevronRight className="w-4 h-4 text-muted-foreground" />}
        </button>
        <AnimatePresence>
          {expanded.faq && (
            <motion.div initial={{ height: 0 }} animate={{ height: 'auto' }} exit={{ height: 0 }} className="overflow-hidden">
              <div className="px-5 pb-4 space-y-3">
                {[
                   { q: "What is Cross-Sensor Corroboration?", a: "Check 9. It catches sensors that read within normal range, pass quality codes, and pass every threshold check — but are wrong. A temp sensor reads 172°C but its correlated pressure and flow sensors say 175°C. No historian catches this." },
                   { q: "Why call some components 'agents' and others not?", a: "Only 2 components are genuine AI agents. The Investigation Agent selects and calls tools based on anomaly type — different anomalies lead to different tool sequences (Historian, MES, CMMS, LIMS). The Hypothesis Agent is a single LLM call. The Detection Engine is deterministic code (no LLM, no tools) — it runs 9 rule checks with 100% coverage and full auditability. Calling the Detection Engine an 'agent' would be misleading since it has no autonomy." },
                  { q: "How is this different from Seeq?", a: "Seeq assumes your data is trustworthy and analyzes the process. We question whether the data is trustworthy in the first place. Seeq tells you 'reactor temp is trending up.' We tell you 'the temp sensor is lying — don't trust that Seeq alert.'" },
                  { q: "How is this different from AVEVA PI quality codes?", a: "PI quality codes are per-sensor, per-reading. They flag broken communication, out-of-range, etc. They cannot detect a sensor that's wrong-but-plausible (within range, Good quality code, but contradicted by other sensors). That's what Cross-Sensor Corroboration catches." },
                  { q: "What's cross-sensor corroboration?", a: "A sensor reading that is within normal range, has Good quality code, passes all threshold checks — but is wrong. The sensor is miscalibrated by a few degrees. No individual check catches it. Only cross-referencing correlated sensors catches it." },
                  { q: "Why is HITL (Human-in-the-Loop) important?", a: "AI can hallucinate or over-flag. Before AI generates root causes and remediation steps, a human reviews and approves or rejects them. This prevents AI from recommending actions based on false alarms — critical in pharma where wrong actions have real consequences." },
                  { q: "What is the Output Guardrail?", a: "A safety layer that scrubs AI outputs for PII (SSN, email, phone), pharma-sensitive data (batch numbers, patient references), credentials, and dangerous recommendations (e.g., 'bypass audit trail'). It runs before any AI output reaches the user." },
                  { q: "Is this FDA 21 CFR Part 11 compliant?", a: "This is a prototype. But the architecture is designed for it: complete audit trail (every agent decision logged), HITL gate, output guardrails, and traceability from finding to recommendation. A production system would add electronic signatures and validation protocols." },
                  { q: "Can I use this with real AVEVA PI data?", a: "The architecture is historian-agnostic. In production, TagSimulator would be replaced by a PI API connector (PI Web API or PI SDK). The TagSimulator exists because we can't ship real plant data with a demo." },
                  { q: "What does the correlation matrix show?", a: "Pearson r values for all correlated tag pairs, computed from the last 24h of data. Blue cells = positive correlation (tags move together), red cells = negative correlation (tags move in opposite directions). Strong correlation (|r| > 0.7) is expected for physically coupled sensors. A sudden drop is evidence of a sensor fault." },
                  { q: "Is the TagSimulator realistic?", a: "It models 5 equipment units with physics-based causal couplings: temperature affects pressure (Clausius-Clapeyron), flow affects level (mass balance), pump pressure relates to flow (pump curve). Readings have autocorrelation (AR(1)), Gaussian noise, and diurnal variation. It's not a full process simulator, but it's realistic enough to demonstrate cross-sensor reasoning." },
                ].map((item, i) => (
                  <div key={i} className="p-3 rounded-lg border border-border">
                    <p className="text-xs font-semibold text-foreground mb-1">{item.q}</p>
                    <p className="text-[11px] text-muted-foreground">{item.a}</p>
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}