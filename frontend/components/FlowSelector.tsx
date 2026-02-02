'use client'

const FLOWS = [
  { id: 'kpi_review', name: 'KPI Review', description: 'CEO → CFO → CMO → CIO → Evaluator' },
  { id: 'trade_off', name: 'Trade-off', description: '[CFO || CMO] → Evaluator' },
  { id: 'scenario', name: 'Scenario', description: 'CFO → CMO → Evaluator' },
  { id: 'root_cause', name: 'Root Cause', description: 'CIO → CFO → CMO → Evaluator' },
]

interface FlowSelectorProps {
  selected: string
  onSelect: (flow: string) => void
}

export function FlowSelector({ selected, onSelect }: FlowSelectorProps) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        Flow Type
      </label>
      <select
        value={selected}
        onChange={(e) => onSelect(e.target.value)}
        className="block w-48 px-3 py-2 border border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"
      >
        {FLOWS.map((flow) => (
          <option key={flow.id} value={flow.id}>
            {flow.name}
          </option>
        ))}
      </select>
      <p className="text-xs text-gray-500 mt-1">
        {FLOWS.find(f => f.id === selected)?.description}
      </p>
    </div>
  )
}
