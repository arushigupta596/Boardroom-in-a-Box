'use client'

import { TrendingUp, TrendingDown, Minus, Info } from 'lucide-react'
import { useState } from 'react'

interface KPI {
  name: string
  value: number
  unit: string
  trend: string
  window?: string
  definition?: string
  source_view?: string
  confidence?: string
}

interface KPICardProps {
  kpi: KPI
}

export function KPICard({ kpi }: KPICardProps) {
  const [showEvidence, setShowEvidence] = useState(false)

  const getTrendIcon = () => {
    if (kpi.trend === 'UP') {
      return <TrendingUp className="w-5 h-5 text-green-500" />
    }
    if (kpi.trend === 'DOWN') {
      return <TrendingDown className="w-5 h-5 text-red-500" />
    }
    return <Minus className="w-5 h-5 text-gray-400" />
  }

  const formatValue = () => {
    if (kpi.unit === '$') {
      return `$${kpi.value.toLocaleString()}`
    }
    if (kpi.unit === '%') {
      return `${kpi.value}%`
    }
    return `${kpi.value.toLocaleString()} ${kpi.unit}`
  }

  return (
    <div className="bg-gray-50 rounded-lg p-4 border border-gray-200 hover:shadow-md transition-shadow">
      <div className="flex justify-between items-start">
        <div>
          <p className="text-sm text-gray-600 font-medium">{kpi.name}</p>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-2xl font-bold text-gray-900">
              {formatValue()}
            </span>
            {getTrendIcon()}
          </div>
        </div>
        <button
          onClick={() => setShowEvidence(!showEvidence)}
          className="text-gray-400 hover:text-blue-500"
          title="Show Evidence"
        >
          <Info className="w-5 h-5" />
        </button>
      </div>

      {kpi.window && (
        <p className="text-xs text-gray-500 mt-2">Window: {kpi.window}</p>
      )}

      {kpi.confidence && (
        <span className={`
          inline-block mt-2 text-xs px-2 py-0.5 rounded
          ${kpi.confidence === 'High' ? 'bg-green-100 text-green-800' :
            kpi.confidence === 'Medium' ? 'bg-yellow-100 text-yellow-800' :
            'bg-red-100 text-red-800'}
        `}>
          {kpi.confidence} Confidence
        </span>
      )}

      {/* Evidence Drawer */}
      {showEvidence && (
        <div className="mt-3 pt-3 border-t border-gray-200 text-sm">
          {kpi.definition && (
            <p className="text-gray-600 mb-1">
              <strong>Definition:</strong> {kpi.definition}
            </p>
          )}
          {kpi.source_view && (
            <p className="text-gray-500 font-mono text-xs">
              Source: {kpi.source_view}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
