'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { FlowTimeline } from '../components/FlowTimeline'
import { KPICard } from '../components/KPICard'
import { ConstraintsPanel } from '../components/ConstraintsPanel'
import { ConflictPanel } from '../components/ConflictPanel'
import { EvaluatorScore } from '../components/EvaluatorScore'
import { HandoffDrawer } from '../components/HandoffDrawer'
import { ConfidenceBadge } from '../components/ConfidenceBadge'
import { FlowSelector } from '../components/FlowSelector'
import { ModeSelector } from '../components/ModeSelector'

interface FlowNode {
  agent: string
  status: string
  started_at?: string
  ended_at?: string
}

interface AgentOutput {
  kpis: any[]
  insights: string[]
}

export default function Home() {
  const [session, setSession] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [selectedFlow, setSelectedFlow] = useState('kpi_review')
  const [selectedMode, setSelectedMode] = useState('summary')
  const [selectedHandoff, setSelectedHandoff] = useState<any>(null)

  // Realtime state
  const [nodes, setNodes] = useState<Record<string, FlowNode>>({})
  const [currentNode, setCurrentNode] = useState<string | null>(null)
  const [confidence, setConfidence] = useState<any>(null)
  const [agentOutputs, setAgentOutputs] = useState<Record<string, AgentOutput>>({})
  const [handoffs, setHandoffs] = useState<any[]>([])
  const [evaluation, setEvaluation] = useState<any>(null)
  const [constraintsStatus, setConstraintsStatus] = useState<Record<string, string>>({})
  const [streamStatus, setStreamStatus] = useState<string>('')

  // Question-based flow
  const [question, setQuestion] = useState<string>('')
  const [flowReasoning, setFlowReasoning] = useState<string>('')
  const [decisionSummary, setDecisionSummary] = useState<any>(null)

  const eventSourceRef = useRef<EventSource | null>(null)

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }
    }
  }, [])

  const runFlowWithStreaming = useCallback(async () => {
    // Reset state
    setLoading(true)
    setSession(null)
    setNodes({})
    setCurrentNode(null)
    setConfidence(null)
    setAgentOutputs({})
    setHandoffs([])
    setEvaluation(null)
    setConstraintsStatus({})
    setStreamStatus('Starting...')

    // Close existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }

    const flowType = selectedFlow.replace('_', '-')
    const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    const url = `${apiBase}/api/flows/stream/${flowType}?mode=${selectedMode}&period_start=2025-11-01&period_end=2026-01-30`

    console.log('Connecting to:', url)
    const eventSource = new EventSource(url)
    eventSourceRef.current = eventSource

    eventSource.onopen = () => {
      console.log('SSE connection opened')
      setStreamStatus('Connected...')
    }

    eventSource.addEventListener('session_start', (e) => {
      console.log('session_start:', e.data)
      const data = JSON.parse(e.data)
      setStreamStatus(`Session ${data.session_id} started`)

      // Initialize nodes from flow spec
      const initialNodes: Record<string, FlowNode> = {}
      data.flow.nodes.forEach((nodeName: string) => {
        initialNodes[nodeName] = { agent: nodeName, status: 'pending' }
      })
      setNodes(initialNodes)
    })

    eventSource.addEventListener('confidence', (e) => {
      const data = JSON.parse(e.data)
      setConfidence(data)
      setStreamStatus(`Confidence: ${data.level}`)
    })

    eventSource.addEventListener('agent_start', (e) => {
      const data = JSON.parse(e.data)
      setCurrentNode(data.agent)
      setStreamStatus(`Running ${data.agent}...`)

      setNodes(prev => ({
        ...prev,
        [data.agent]: {
          ...prev[data.agent],
          status: 'active',
          started_at: data.started_at,
        }
      }))
    })

    eventSource.addEventListener('agent_complete', (e) => {
      const data = JSON.parse(e.data)
      setStreamStatus(`${data.agent} complete`)

      setNodes(prev => ({
        ...prev,
        [data.agent]: {
          ...prev[data.agent],
          status: 'completed',
          ended_at: data.ended_at,
        }
      }))

      // Store agent output if present
      if (data.kpis || data.insights) {
        setAgentOutputs(prev => ({
          ...prev,
          [data.agent]: {
            kpis: data.kpis || [],
            insights: data.insights || [],
          }
        }))
      }
    })

    eventSource.addEventListener('handoff', (e) => {
      const data = JSON.parse(e.data)
      setHandoffs(prev => [...prev, data])
    })

    eventSource.addEventListener('evaluation', (e) => {
      const data = JSON.parse(e.data)
      setEvaluation(data)
      setStreamStatus('Evaluation complete')
    })

    eventSource.addEventListener('session_complete', (e) => {
      const data = JSON.parse(e.data)
      setCurrentNode(null)
      setConstraintsStatus(data.constraints_status || {})
      setStreamStatus('Complete')
      setLoading(false)

      // Build full session object for exports
      setSession({
        session_id: data.session_id,
        ended_at: data.ended_at,
        constraints_status: data.constraints_status,
      })

      eventSource.close()
    })

    eventSource.addEventListener('agent_error', (e) => {
      const data = JSON.parse(e.data)
      setStreamStatus(`Error: ${data.error}`)

      setNodes(prev => ({
        ...prev,
        [data.agent]: {
          ...prev[data.agent],
          status: 'failed',
        }
      }))
    })

    eventSource.onerror = (err) => {
      console.error('SSE error:', err)
      setStreamStatus('Connection error - check console')
      setLoading(false)
      eventSource.close()
    }

    // Debug: log all messages
    eventSource.onmessage = (e) => {
      console.log('SSE message:', e.data)
    }
  }, [selectedFlow, selectedMode])

  // Run flow from natural language question
  const runFlowFromQuestion = useCallback(async () => {
    if (!question.trim()) return

    // Reset state
    setLoading(true)
    setSession(null)
    setNodes({})
    setCurrentNode(null)
    setConfidence(null)
    setAgentOutputs({})
    setHandoffs([])
    setEvaluation(null)
    setConstraintsStatus({})
    setDecisionSummary(null)
    setFlowReasoning('')
    setStreamStatus('Analyzing question...')

    const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

    try {
      const response = await fetch(`${apiBase}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: question })
      })

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail || 'Failed to process question')
      }

      // Update flow selector to match what was used
      setSelectedFlow(data.flow_used)
      setFlowReasoning(data.flow_reasoning)

      // Store the decision summary
      setDecisionSummary({
        summary: data.message,
        key_findings: data.key_findings || [],
        recommendations: data.recommendations || [],
        risks: data.risks || [],
        confidence_level: data.confidence_level,
        next_steps: data.next_steps || []
      })

      // Build nodes from agents involved
      const nodeData: Record<string, FlowNode> = {}
      data.agents_involved?.forEach((agent: string) => {
        nodeData[agent] = { agent, status: 'completed' }
      })
      setNodes(nodeData)

      // Use real agent outputs if available from full flow
      if (data.agent_outputs) {
        setAgentOutputs(data.agent_outputs)
      }

      // Use real handoffs if available
      if (data.handoffs) {
        setHandoffs(data.handoffs)
      }

      // Use real evaluation if available, otherwise build from response
      if (data.evaluation) {
        setEvaluation(data.evaluation)
      } else if (data.overall_score !== undefined) {
        setEvaluation({
          overall_score: data.overall_score,
          risk_level: data.confidence_level === 'High' ? 'Low' : data.confidence_level === 'Low' ? 'High' : 'Medium',
          confidence: data.confidence_level || 'Medium',
          has_blocking_conflicts: false,
          dimension_scores: [
            { dimension: 'Strategic Alignment', score: data.overall_score, weight: 0.3, weighted_score: data.overall_score * 0.3, factors: [], warnings: [] },
            { dimension: 'Financial Impact', score: data.overall_score * 0.9, weight: 0.25, weighted_score: data.overall_score * 0.9 * 0.25, factors: [], warnings: [] },
            { dimension: 'Market Analysis', score: data.overall_score * 0.95, weight: 0.25, weighted_score: data.overall_score * 0.95 * 0.25, factors: [], warnings: [] },
            { dimension: 'Data Quality', score: data.overall_score * 0.85, weight: 0.2, weighted_score: data.overall_score * 0.85 * 0.2, factors: [], warnings: [] }
          ],
          decisions: data.recommendations?.map((rec: string, idx: number) => ({
            action: rec,
            impact: 'See details',
            priority: idx === 0 ? 'High' : 'Medium'
          })) || [],
          conflicts: data.risks?.map((risk: string, idx: number) => ({
            issue: risk,
            severity: 'Medium',
            between: ['Analysis']
          })) || []
        })
      }

      // Set confidence
      setConfidence({
        level: data.confidence_level || 'Medium',
        score: data.confidence || 0.8
      })

      setSession({
        session_id: data.session_id,
        ended_at: new Date().toISOString()
      })

      setStreamStatus('Complete')
    } catch (error: any) {
      setStreamStatus(`Error: ${error.message}`)
    } finally {
      setLoading(false)
    }
  }, [question])

  // Get all KPIs from CEO output
  const ceoKpis = agentOutputs['CEO']?.kpis || []

  return (
    <main className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Boardroom-in-a-Box</h1>
          <p className="text-gray-600">AI-powered retail decision system</p>
        </div>
        <div className="flex gap-4 items-center">
          {confidence && (
            <ConfidenceBadge confidence={confidence} />
          )}
        </div>
      </div>

      {/* Controls */}
      <div className="bg-white rounded-lg shadow p-6 mb-8">
        {/* Question Input */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Ask the Boardroom
          </label>
          <div className="flex gap-3">
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && runFlowFromQuestion()}
              placeholder="e.g., How is the business performing? Why are sales declining? Should we increase marketing spend?"
              className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-gray-900"
            />
            <button
              onClick={runFlowFromQuestion}
              disabled={loading || !question.trim()}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 flex items-center gap-2 whitespace-nowrap"
            >
              {loading && (
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
              )}
              {loading ? streamStatus : 'Ask'}
            </button>
          </div>
          {flowReasoning && (
            <p className="mt-2 text-sm text-gray-600">
              <span className="font-medium">AI selected:</span> {selectedFlow.replace('_', ' ')} flow — {flowReasoning}
            </p>
          )}
        </div>

        {/* Divider */}
        <div className="relative mb-6">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-gray-200"></div>
          </div>
          <div className="relative flex justify-center text-sm">
            <span className="px-3 bg-white text-gray-500">or select flow manually</span>
          </div>
        </div>

        {/* Manual Flow Selection */}
        <div className="flex gap-6 items-end">
          <FlowSelector
            selected={selectedFlow}
            onSelect={setSelectedFlow}
          />
          <ModeSelector
            selected={selectedMode}
            onSelect={setSelectedMode}
          />
          <button
            onClick={runFlowWithStreaming}
            disabled={loading}
            className="px-6 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:bg-gray-400 flex items-center gap-2"
          >
            {loading && (
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
            )}
            {loading ? streamStatus : 'Run Flow'}
          </button>
        </div>
      </div>

      {/* Decision Summary (from question-based flow) */}
      {decisionSummary && (
        <div className="bg-white rounded-lg shadow p-6 mb-8">
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <svg className="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            Executive Summary
          </h2>
          <p className="text-gray-700 mb-6 leading-relaxed">{decisionSummary.summary}</p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Key Findings */}
            {decisionSummary.key_findings?.length > 0 && (
              <div>
                <h3 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
                  <span className="w-2 h-2 bg-blue-500 rounded-full"></span>
                  Key Findings
                </h3>
                <ul className="space-y-2">
                  {decisionSummary.key_findings.map((finding: string, idx: number) => (
                    <li key={idx} className="text-sm text-gray-600 pl-4 border-l-2 border-blue-200">
                      {finding}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Recommendations */}
            {decisionSummary.recommendations?.length > 0 && (
              <div>
                <h3 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
                  <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                  Recommendations
                </h3>
                <ul className="space-y-2">
                  {decisionSummary.recommendations.map((rec: string, idx: number) => (
                    <li key={idx} className="text-sm text-gray-600 pl-4 border-l-2 border-green-200">
                      {rec}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Risks */}
            {decisionSummary.risks?.length > 0 && (
              <div>
                <h3 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
                  <span className="w-2 h-2 bg-red-500 rounded-full"></span>
                  Risks & Concerns
                </h3>
                <ul className="space-y-2">
                  {decisionSummary.risks.map((risk: string, idx: number) => (
                    <li key={idx} className="text-sm text-gray-600 pl-4 border-l-2 border-red-200">
                      {risk}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Next Steps */}
            {decisionSummary.next_steps?.length > 0 && (
              <div>
                <h3 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
                  <span className="w-2 h-2 bg-purple-500 rounded-full"></span>
                  Next Steps
                </h3>
                <ul className="space-y-2">
                  {decisionSummary.next_steps.map((step: string, idx: number) => (
                    <li key={idx} className="text-sm text-gray-600 pl-4 border-l-2 border-purple-200">
                      {step}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Confidence Badge */}
          {decisionSummary.confidence_level && (
            <div className="mt-6 pt-4 border-t border-gray-200">
              <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${
                decisionSummary.confidence_level === 'High' ? 'bg-green-100 text-green-800' :
                decisionSummary.confidence_level === 'Medium' ? 'bg-yellow-100 text-yellow-800' :
                'bg-red-100 text-red-800'
              }`}>
                Confidence: {decisionSummary.confidence_level}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Constraints Panel */}
      {Object.keys(constraintsStatus).length > 0 && (
        <div className="mb-8">
          <ConstraintsPanel
            constraints={{}}
            status={constraintsStatus}
          />
        </div>
      )}

      {/* Flow Timeline - Always show if nodes exist */}
      {Object.keys(nodes).length > 0 && (
        <div className="bg-white rounded-lg shadow p-6 mb-8">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-semibold">Flow Timeline</h2>
            {loading && (
              <span className="text-sm text-blue-600 animate-pulse">{streamStatus}</span>
            )}
          </div>
          <FlowTimeline
            nodes={nodes}
            edges={[]}
            currentNode={currentNode}
            agentOutputs={agentOutputs}
            handoffs={handoffs}
            onNodeClick={(node: any) => {
              const handoff = handoffs.find(
                (h: any) => h.from === node.agent
              )
              setSelectedHandoff(handoff)
            }}
          />
        </div>
      )}

      {/* Main Content Grid - Show as data arrives */}
      {(ceoKpis.length > 0 || evaluation) && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* KPIs */}
          <div className="lg:col-span-2">
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-xl font-semibold mb-4">Key Metrics</h2>
              <div className="grid grid-cols-2 gap-4">
                {ceoKpis.map((kpi: any, idx: number) => (
                  <KPICard key={idx} kpi={kpi} />
                ))}
              </div>
            </div>
          </div>

          {/* Evaluator Score */}
          <div>
            {evaluation ? (
              <EvaluatorScore evaluation={evaluation} />
            ) : (
              <div className="bg-white rounded-lg shadow p-6 animate-pulse">
                <div className="h-6 bg-gray-200 rounded w-1/2 mb-4"></div>
                <div className="h-32 bg-gray-200 rounded"></div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Agent Insights */}
      {Object.keys(agentOutputs).length > 0 && (
        <div className="mt-8 bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold mb-4">Agent Insights</h2>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {Object.entries(agentOutputs).map(([agent, output]) => (
              <div key={agent} className="border rounded-lg p-4">
                <h3 className="font-semibold text-gray-900 mb-2">{agent}</h3>
                <ul className="text-sm text-gray-600 space-y-1">
                  {output.insights.slice(0, 2).map((insight, idx) => (
                    <li key={idx} className="truncate" title={insight}>• {insight}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Conflicts */}
      {evaluation?.conflicts?.length > 0 && (
        <div className="mt-8">
          <ConflictPanel conflicts={evaluation.conflicts} />
        </div>
      )}

      {/* Decisions */}
      {evaluation?.decisions?.length > 0 && (
        <div className="mt-8 bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold mb-4">Recommended Actions</h2>
          <div className="space-y-4">
            {evaluation.decisions.map((decision: any, idx: number) => (
              <div key={idx} className="border-l-4 border-blue-500 pl-4 py-2">
                <p className="font-medium">{decision.action}</p>
                <p className="text-sm text-gray-600">Impact: {decision.impact}</p>
                <div className="flex gap-2 mt-1">
                  <span className={`text-xs px-2 py-1 rounded ${
                    decision.priority === 'High' ? 'bg-red-100 text-red-800' :
                    decision.priority === 'Medium' ? 'bg-yellow-100 text-yellow-800' :
                    'bg-green-100 text-green-800'
                  }`}>
                    {decision.priority}
                  </span>
                  {decision.confidence && (
                    <span className="text-xs px-2 py-1 rounded bg-gray-100 text-gray-800">
                      {decision.confidence}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Export Buttons */}
      {session?.session_id && (
        <div className="mt-8 flex gap-4">
          <a
            href={`/api/sessions/${session.session_id}/memo`}
            target="_blank"
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
          >
            Download Board Memo
          </a>
          <a
            href={`/api/sessions/${session.session_id}/evidence`}
            target="_blank"
            className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700"
          >
            Download Evidence Pack
          </a>
          <button
            onClick={() => {
              fetch(`/api/sessions/${session.session_id}/email-summary`)
                .then(r => r.text())
                .then(text => navigator.clipboard.writeText(text))
            }}
            className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700"
          >
            Copy Summary
          </button>
        </div>
      )}

      {/* Handoff Drawer */}
      {selectedHandoff && (
        <HandoffDrawer
          handoff={selectedHandoff}
          onClose={() => setSelectedHandoff(null)}
        />
      )}
    </main>
  )
}
