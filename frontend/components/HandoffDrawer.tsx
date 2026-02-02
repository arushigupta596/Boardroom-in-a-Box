'use client'

import { X, ArrowRight, AlertCircle, FileText } from 'lucide-react'

interface HandoffDrawerProps {
  handoff: any
  onClose: () => void
}

export function HandoffDrawer({ handoff, onClose }: HandoffDrawerProps) {
  if (!handoff) return null

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black bg-opacity-50"
        onClick={onClose}
      />

      {/* Drawer */}
      <div className="absolute right-0 top-0 h-full w-full max-w-md bg-white shadow-xl">
        <div className="flex flex-col h-full">
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold">Handoff Details</h2>
            </div>
            <button
              onClick={onClose}
              className="p-2 hover:bg-gray-100 rounded-full"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-4 space-y-6">
            {/* Flow */}
            <div className="flex items-center justify-center gap-4 py-4 bg-gray-50 rounded-lg">
              <span className="px-4 py-2 bg-blue-100 text-blue-800 rounded-lg font-semibold">
                {handoff.handoff_from}
              </span>
              <ArrowRight className="w-6 h-6 text-gray-400" />
              <span className="px-4 py-2 bg-green-100 text-green-800 rounded-lg font-semibold">
                {handoff.handoff_to}
              </span>
            </div>

            {/* Reason */}
            {handoff.reason && (
              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
                <p className="text-sm font-medium text-yellow-800">
                  Reason: {handoff.reason}
                </p>
              </div>
            )}

            {/* Flags */}
            {handoff.flags?.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 text-orange-500" />
                  Risk Flags
                </h3>
                <div className="flex flex-wrap gap-2">
                  {handoff.flags.map((flag: string, idx: number) => (
                    <span
                      key={idx}
                      className="px-2 py-1 bg-orange-100 text-orange-800 text-xs rounded font-medium"
                    >
                      {flag}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Signals */}
            {handoff.signals?.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-2">Signals</h3>
                <div className="space-y-2">
                  {handoff.signals.map((signal: any, idx: number) => (
                    <div
                      key={idx}
                      className="flex justify-between items-center p-2 bg-gray-50 rounded"
                    >
                      <span className="text-sm text-gray-700">{signal.metric}</span>
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{signal.value}</span>
                        <span className={`text-xs ${
                          signal.direction === 'UP' ? 'text-green-600' :
                          signal.direction === 'DOWN' ? 'text-red-600' :
                          'text-gray-500'
                        }`}>
                          {signal.direction === 'UP' ? '↑' :
                           signal.direction === 'DOWN' ? '↓' : '→'}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* KPIs */}
            {handoff.kpi_summary?.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-2">KPIs Passed</h3>
                <div className="space-y-2">
                  {handoff.kpi_summary.map((kpi: any, idx: number) => (
                    <div
                      key={idx}
                      className="flex justify-between items-center p-2 bg-gray-50 rounded"
                    >
                      <span className="text-sm text-gray-700">{kpi.name}</span>
                      <span className="font-medium">
                        {kpi.value}{kpi.unit === '%' ? '%' : ` ${kpi.unit}`}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Focus Areas */}
            {handoff.focus_areas?.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-2">Focus Areas</h3>
                <div className="space-y-2">
                  {handoff.focus_areas.map((area: any, idx: number) => (
                    <div key={idx} className="p-2 bg-blue-50 rounded text-sm">
                      {area.category && <p>Category: <strong>{area.category}</strong></p>}
                      {area.stores && <p>Stores: {area.stores.join(', ')}</p>}
                      {area.region && <p>Region: {area.region}</p>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Evidence */}
            {handoff.evidence?.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
                  <FileText className="w-4 h-4" />
                  Evidence
                </h3>
                <div className="space-y-2">
                  {handoff.evidence.map((ev: any, idx: number) => (
                    <div
                      key={idx}
                      className="p-2 bg-gray-50 rounded text-sm font-mono"
                    >
                      {ev.view}
                      {ev.query_id && (
                        <span className="text-gray-400 ml-2">({ev.query_id})</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Timestamp */}
            <div className="text-xs text-gray-400 pt-4 border-t">
              Timestamp: {handoff.timestamp}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
