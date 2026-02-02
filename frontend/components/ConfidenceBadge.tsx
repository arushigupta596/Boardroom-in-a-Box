'use client'

import { ShieldCheck, ShieldAlert, ShieldX } from 'lucide-react'

interface ConfidenceReport {
  level: string
  score: number
  can_proceed: boolean
  summary: string
  blocking_issues: string[]
}

interface ConfidenceBadgeProps {
  confidence: ConfidenceReport
}

export function ConfidenceBadge({ confidence }: ConfidenceBadgeProps) {
  const getIcon = () => {
    if (confidence.level === 'High') {
      return <ShieldCheck className="w-5 h-5 text-green-600" />
    }
    if (confidence.level === 'Medium') {
      return <ShieldAlert className="w-5 h-5 text-yellow-600" />
    }
    return <ShieldX className="w-5 h-5 text-red-600" />
  }

  const getColor = () => {
    if (confidence.level === 'High') return 'bg-green-100 border-green-200 text-green-800'
    if (confidence.level === 'Medium') return 'bg-yellow-100 border-yellow-200 text-yellow-800'
    return 'bg-red-100 border-red-200 text-red-800'
  }

  return (
    <div className={`flex items-center gap-2 px-3 py-2 rounded-lg border ${getColor()}`}>
      {getIcon()}
      <div>
        <p className="text-sm font-medium">
          Data Confidence: {confidence.level}
        </p>
        <p className="text-xs opacity-80">
          {confidence.can_proceed ? 'Ready to proceed' : 'Issues detected'}
        </p>
      </div>
    </div>
  )
}
