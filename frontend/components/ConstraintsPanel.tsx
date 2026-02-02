'use client'

import { CheckCircle, XCircle, AlertCircle } from 'lucide-react'

interface Constraint {
  name: string
  operator: string
  value: any
  unit?: string
}

interface ConstraintsPanelProps {
  constraints: Record<string, Constraint>
  status: Record<string, string>
}

export function ConstraintsPanel({ constraints, status }: ConstraintsPanelProps) {
  const getStatusIcon = (key: string) => {
    const s = status[key]
    if (s === 'PASS') {
      return <CheckCircle className="w-5 h-5 text-green-500" />
    }
    if (s === 'VIOLATED') {
      return <XCircle className="w-5 h-5 text-red-500" />
    }
    return <AlertCircle className="w-5 h-5 text-gray-400" />
  }

  const formatValue = (constraint: Constraint) => {
    const val = constraint.value
    const unit = constraint.unit || ''

    if (Array.isArray(val)) {
      return `${val[0]}${unit} - ${val[1]}${unit}`
    }

    const op = constraint.operator
    if (op === '>=') return `≥ ${val}${unit}`
    if (op === '<=') return `≤ ${val}${unit}`
    if (op === '==') return `= ${val}${unit}`
    return `${val}${unit}`
  }

  const entries = Object.entries(constraints)

  if (entries.length === 0) {
    return null
  }

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">Decision Constraints</h3>
      <div className="flex flex-wrap gap-4">
        {entries.map(([key, constraint]) => (
          <div
            key={key}
            className={`
              flex items-center gap-2 px-3 py-2 rounded-lg border
              ${status[key] === 'PASS' ? 'border-green-200 bg-green-50' :
                status[key] === 'VIOLATED' ? 'border-red-200 bg-red-50' :
                'border-gray-200 bg-gray-50'}
            `}
          >
            {getStatusIcon(key)}
            <div>
              <p className="text-sm font-medium text-gray-900">
                {constraint.name}
              </p>
              <p className="text-xs text-gray-600">
                {formatValue(constraint)}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
