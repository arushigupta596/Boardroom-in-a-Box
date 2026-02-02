'use client'

import { AlertTriangle, AlertCircle, XCircle } from 'lucide-react'

interface Conflict {
  conflict_id: string
  between: string[]
  issue: string
  severity: string
  details?: string
  resolution?: string
  constraint_violated?: string
}

interface ConflictPanelProps {
  conflicts: Conflict[]
}

export function ConflictPanel({ conflicts }: ConflictPanelProps) {
  const getSeverityIcon = (severity: string) => {
    if (severity === 'Critical') {
      return <XCircle className="w-6 h-6 text-red-600" />
    }
    if (severity === 'High') {
      return <AlertTriangle className="w-6 h-6 text-orange-500" />
    }
    return <AlertCircle className="w-6 h-6 text-yellow-500" />
  }

  const getSeverityColor = (severity: string) => {
    if (severity === 'Critical') return 'border-red-500 bg-red-50'
    if (severity === 'High') return 'border-orange-500 bg-orange-50'
    return 'border-yellow-500 bg-yellow-50'
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
        <AlertTriangle className="w-6 h-6 text-orange-500" />
        Conflicts Detected ({conflicts.length})
      </h2>

      <div className="space-y-4">
        {conflicts.map((conflict) => (
          <div
            key={conflict.conflict_id}
            className={`border-l-4 p-4 rounded-r-lg ${getSeverityColor(conflict.severity)}`}
          >
            <div className="flex items-start gap-3">
              {getSeverityIcon(conflict.severity)}
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <h3 className="font-semibold text-gray-900">{conflict.issue}</h3>
                  <span className={`
                    text-xs px-2 py-1 rounded font-medium
                    ${conflict.severity === 'Critical' ? 'bg-red-200 text-red-800' :
                      conflict.severity === 'High' ? 'bg-orange-200 text-orange-800' :
                      'bg-yellow-200 text-yellow-800'}
                  `}>
                    {conflict.severity}
                  </span>
                </div>

                <p className="text-sm text-gray-600 mt-1">
                  Between: <span className="font-medium">{conflict.between.join(' ↔ ')}</span>
                </p>

                {conflict.details && (
                  <p className="text-sm text-gray-700 mt-2">{conflict.details}</p>
                )}

                {conflict.resolution && (
                  <div className="mt-3 p-2 bg-white bg-opacity-60 rounded">
                    <p className="text-sm">
                      <strong className="text-green-700">Resolution:</strong>{' '}
                      {conflict.resolution}
                    </p>
                  </div>
                )}

                {conflict.constraint_violated && (
                  <p className="text-xs text-gray-500 mt-2">
                    Constraint violated: {conflict.constraint_violated}
                  </p>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
