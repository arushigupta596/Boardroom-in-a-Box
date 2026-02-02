'use client'

const MODES = [
  { id: 'summary', name: 'Summary', description: 'Short, calm overview' },
  { id: 'debate', name: 'Debate', description: 'Side-by-side CFO vs CMO' },
  { id: 'operator', name: 'Operator', description: 'Drill down to store/SKU' },
  { id: 'audit', name: 'Audit', description: 'Show SQL/evidence/logs' },
]

interface ModeSelectorProps {
  selected: string
  onSelect: (mode: string) => void
}

export function ModeSelector({ selected, onSelect }: ModeSelectorProps) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        Display Mode
      </label>
      <div className="flex gap-1 p-1 bg-gray-100 rounded-lg">
        {MODES.map((mode) => (
          <button
            key={mode.id}
            onClick={() => onSelect(mode.id)}
            className={`
              px-3 py-1.5 text-sm rounded-md transition-all
              ${selected === mode.id
                ? 'bg-white shadow text-blue-600 font-medium'
                : 'text-gray-600 hover:text-gray-900'}
            `}
            title={mode.description}
          >
            {mode.name}
          </button>
        ))}
      </div>
    </div>
  )
}
