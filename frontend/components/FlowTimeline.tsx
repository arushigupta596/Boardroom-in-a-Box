'use client'

import { CheckCircle, Circle, XCircle, Loader2, ChevronDown, ChevronUp, MessageSquare } from 'lucide-react'
import { useEffect, useState } from 'react'

interface KPI {
  name: string
  value: number
  unit: string
  trend?: string
}

interface AgentOutput {
  kpis: KPI[]
  insights: string[]
}

interface FlowNode {
  agent: string
  status: string
  started_at?: string
  ended_at?: string
}

interface FlowTimelineProps {
  nodes: Record<string, FlowNode>
  edges: any[]
  currentNode?: string | null
  agentOutputs?: Record<string, AgentOutput>
  handoffs?: any[]
  onNodeClick?: (node: FlowNode) => void
}

// Agent role colors and descriptions
const AGENT_CONFIG: Record<string, {
  bg: string;
  border: string;
  text: string;
  ring: string;
  role: string;
  avatar: string;
}> = {
  CEO: {
    bg: 'bg-purple-50',
    border: 'border-purple-500',
    text: 'text-purple-700',
    ring: 'ring-purple-400',
    role: 'Chief Executive Officer',
    avatar: '👔'
  },
  CFO: {
    bg: 'bg-emerald-50',
    border: 'border-emerald-500',
    text: 'text-emerald-700',
    ring: 'ring-emerald-400',
    role: 'Chief Financial Officer',
    avatar: '💰'
  },
  CMO: {
    bg: 'bg-orange-50',
    border: 'border-orange-500',
    text: 'text-orange-700',
    ring: 'ring-orange-400',
    role: 'Chief Marketing Officer',
    avatar: '📊'
  },
  CIO: {
    bg: 'bg-blue-50',
    border: 'border-blue-500',
    text: 'text-blue-700',
    ring: 'ring-blue-400',
    role: 'Chief Information Officer',
    avatar: '🔧'
  },
  Evaluator: {
    bg: 'bg-slate-50',
    border: 'border-slate-500',
    text: 'text-slate-700',
    ring: 'ring-slate-400',
    role: 'Board Evaluator',
    avatar: '⚖️'
  },
}

export function FlowTimeline({
  nodes,
  edges,
  currentNode,
  agentOutputs = {},
  handoffs = [],
  onNodeClick
}: FlowTimelineProps) {
  const [animatedNodes, setAnimatedNodes] = useState<Set<string>>(new Set())
  const [expandedNode, setExpandedNode] = useState<string | null>(null)

  // Track when nodes complete to trigger animation
  useEffect(() => {
    Object.entries(nodes).forEach(([name, node]) => {
      if (node.status === 'completed' && !animatedNodes.has(name)) {
        setAnimatedNodes(prev => new Set([...prev, name]))
      }
    })
  }, [nodes, animatedNodes])

  // Auto-expand the current active node
  useEffect(() => {
    if (currentNode) {
      setExpandedNode(currentNode)
    }
  }, [currentNode])

  // Fixed order for display
  const nodeOrder = ['CEO', 'CFO', 'CMO', 'CIO', 'Evaluator']
  const orderedNodes = nodeOrder
    .filter(name => name in nodes)
    .map(name => [name, nodes[name]] as [string, FlowNode])

  const getStatusIcon = (name: string, status: string, isCurrent: boolean) => {
    const config = AGENT_CONFIG[name] || AGENT_CONFIG.Evaluator

    if (status === 'completed') {
      return (
        <div className={`relative ${animatedNodes.has(name) ? 'animate-bounce-once' : ''}`}>
          <CheckCircle className={`w-8 h-8 text-green-500`} />
        </div>
      )
    }
    if (status === 'failed') {
      return <XCircle className="w-8 h-8 text-red-500" />
    }
    if (isCurrent || status === 'active') {
      return (
        <div className="relative">
          <Loader2 className={`w-8 h-8 ${config.text} animate-spin`} />
        </div>
      )
    }
    return <Circle className="w-8 h-8 text-gray-300" />
  }

  const getHandoffForAgent = (agentName: string) => {
    return handoffs.find(h => h.from === agentName)
  }

  const formatKPIValue = (kpi: KPI) => {
    if (kpi.unit === '$') {
      return `$${kpi.value.toLocaleString()}`
    }
    if (kpi.unit === '%') {
      return `${kpi.value}%`
    }
    return `${kpi.value.toLocaleString()} ${kpi.unit}`
  }

  return (
    <div className="space-y-4">
      {/* Timeline nodes */}
      <div className="relative">
        {/* Progress bar background */}
        <div className="absolute top-6 left-0 right-0 h-1 bg-gray-200 mx-20" />

        {/* Animated progress fill */}
        <div
          className="absolute top-6 left-0 h-1 bg-green-400 mx-20 transition-all duration-500 ease-out"
          style={{
            width: `${(orderedNodes.filter(([_, n]) => n.status === 'completed').length / orderedNodes.length) * 100}%`
          }}
        />

        <div className="relative flex items-start justify-between px-4">
          {orderedNodes.map(([name, node], index) => {
            const isCurrent = name === currentNode
            const config = AGENT_CONFIG[name] || AGENT_CONFIG.Evaluator
            const output = agentOutputs[name]
            const handoff = getHandoffForAgent(name)
            const isExpanded = expandedNode === name

            return (
              <div key={name} className="flex flex-col items-center flex-1">
                {/* Node circle */}
                <div
                  className={`
                    relative flex flex-col items-center cursor-pointer
                    transition-all duration-300 ease-out z-10
                  `}
                  onClick={() => setExpandedNode(isExpanded ? null : name)}
                >
                  {/* Avatar + Status */}
                  <div className={`
                    w-12 h-12 rounded-full flex items-center justify-center text-2xl
                    border-2 transition-all
                    ${node.status === 'completed' ? 'border-green-500 bg-green-50' :
                      node.status === 'active' ? `${config.border} ${config.bg} ring-2 ${config.ring}` :
                      node.status === 'failed' ? 'border-red-500 bg-red-50' :
                      'border-gray-200 bg-white'}
                  `}>
                    {node.status === 'active' ? (
                      <Loader2 className={`w-6 h-6 ${config.text} animate-spin`} />
                    ) : (
                      config.avatar
                    )}
                  </div>

                  {/* Status indicator */}
                  <div className="absolute -bottom-1 -right-1">
                    {getStatusIcon(name, node.status, isCurrent)}
                  </div>
                </div>

                {/* Agent name */}
                <span className={`mt-2 font-semibold text-sm ${
                  node.status === 'active' ? config.text : 'text-gray-900'
                }`}>
                  {name}
                </span>

                {/* Status badge */}
                <span className={`
                  text-xs px-2 py-0.5 rounded-full mt-1
                  ${node.status === 'completed' ? 'bg-green-100 text-green-700' :
                    node.status === 'active' ? 'bg-blue-100 text-blue-700' :
                    node.status === 'failed' ? 'bg-red-100 text-red-700' :
                    'bg-gray-100 text-gray-500'}
                `}>
                  {node.status === 'active' ? 'Analyzing...' :
                   node.status === 'completed' ? 'Done' :
                   node.status === 'failed' ? 'Failed' : 'Waiting'}
                </span>

                {/* Expand indicator */}
                {output && node.status === 'completed' && (
                  <button
                    className="mt-1 text-gray-400 hover:text-gray-600"
                    onClick={(e) => {
                      e.stopPropagation()
                      setExpandedNode(isExpanded ? null : name)
                    }}
                  >
                    {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </button>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Expanded conversation panel */}
      {expandedNode && (
        <div className={`
          mt-4 rounded-xl border-2 overflow-hidden transition-all
          ${AGENT_CONFIG[expandedNode]?.border || 'border-gray-200'}
          ${AGENT_CONFIG[expandedNode]?.bg || 'bg-gray-50'}
        `}>
          {/* Header */}
          <div className={`
            px-4 py-3 border-b flex items-center gap-3
            ${AGENT_CONFIG[expandedNode]?.bg || 'bg-gray-50'}
          `}>
            <span className="text-2xl">{AGENT_CONFIG[expandedNode]?.avatar}</span>
            <div>
              <h3 className="font-bold text-gray-900">{expandedNode}</h3>
              <p className="text-sm text-gray-500">{AGENT_CONFIG[expandedNode]?.role}</p>
            </div>
            <button
              className="ml-auto text-gray-400 hover:text-gray-600"
              onClick={() => setExpandedNode(null)}
            >
              <XCircle size={20} />
            </button>
          </div>

          {/* Content */}
          <div className="p-4 bg-white">
            {agentOutputs[expandedNode] ? (
              <div className="space-y-4">
                {/* KPIs */}
                {agentOutputs[expandedNode].kpis?.length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-gray-500 mb-2">Key Metrics</h4>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      {agentOutputs[expandedNode].kpis.map((kpi, idx) => (
                        <div key={idx} className="bg-gray-50 rounded-lg p-3">
                          <p className="text-xs text-gray-500">{kpi.name}</p>
                          <p className="text-lg font-bold text-gray-900">{formatKPIValue(kpi)}</p>
                          {kpi.trend && (
                            <span className={`text-xs ${
                              kpi.trend === 'up' ? 'text-green-600' :
                              kpi.trend === 'down' ? 'text-red-600' : 'text-gray-500'
                            }`}>
                              {kpi.trend === 'up' ? '↑' : kpi.trend === 'down' ? '↓' : '→'} {kpi.trend}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Insights as conversation */}
                {agentOutputs[expandedNode].insights?.length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-gray-500 mb-2 flex items-center gap-1">
                      <MessageSquare size={14} /> Analysis
                    </h4>
                    <div className="space-y-2">
                      {agentOutputs[expandedNode].insights.map((insight, idx) => (
                        <div key={idx} className={`
                          flex gap-3 items-start
                        `}>
                          <span className="text-lg flex-shrink-0">{AGENT_CONFIG[expandedNode]?.avatar}</span>
                          <div className={`
                            px-4 py-2 rounded-2xl rounded-tl-none
                            ${AGENT_CONFIG[expandedNode]?.bg || 'bg-gray-100'}
                          `}>
                            <p className="text-sm text-gray-800">{insight}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Handoff message */}
                {getHandoffForAgent(expandedNode) && (
                  <div className="border-t pt-3 mt-3">
                    <p className="text-sm text-gray-500 flex items-center gap-2">
                      <span>→</span>
                      <span>
                        Handed off to <strong>{getHandoffForAgent(expandedNode).to}</strong>
                        {getHandoffForAgent(expandedNode).flags?.length > 0 && (
                          <span className="ml-2 px-2 py-0.5 bg-yellow-100 text-yellow-800 rounded text-xs">
                            {getHandoffForAgent(expandedNode).flags.join(', ')}
                          </span>
                        )}
                      </span>
                    </p>
                    {getHandoffForAgent(expandedNode).reason && (
                      <p className="text-xs text-gray-400 mt-1 ml-6">
                        {getHandoffForAgent(expandedNode).reason}
                      </p>
                    )}
                  </div>
                )}
              </div>
            ) : nodes[expandedNode]?.status === 'active' ? (
              <div className="flex items-center gap-3 text-gray-500">
                <Loader2 className="w-5 h-5 animate-spin" />
                <span>Analyzing data...</span>
              </div>
            ) : (
              <p className="text-gray-400 text-sm">Waiting to start...</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
