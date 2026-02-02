'use client'

interface DimensionScore {
  dimension: string
  score: number
  weight: number
  weighted_score: number
  factors: string[]
  warnings: string[]
}

interface Evaluation {
  overall_score: number
  risk_level: string
  confidence: string
  dimension_scores: DimensionScore[]
  has_blocking_conflicts: boolean
}

interface EvaluatorScoreProps {
  evaluation?: Evaluation
}

export function EvaluatorScore({ evaluation }: EvaluatorScoreProps) {
  if (!evaluation) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-xl font-semibold mb-4">Evaluator Score</h2>
        <p className="text-gray-500">No evaluation available</p>
      </div>
    )
  }

  const getRiskColor = (risk: string) => {
    if (risk === 'Low') return 'text-green-600 bg-green-100'
    if (risk === 'Medium') return 'text-yellow-600 bg-yellow-100'
    if (risk === 'High') return 'text-orange-600 bg-orange-100'
    return 'text-red-600 bg-red-100'
  }

  const getScoreColor = (score: number) => {
    if (score >= 8) return 'text-green-600'
    if (score >= 6) return 'text-yellow-600'
    if (score >= 4) return 'text-orange-600'
    return 'text-red-600'
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-xl font-semibold mb-4">Evaluator Score</h2>

      {/* Main Score */}
      <div className="text-center mb-6">
        <div className={`text-5xl font-bold ${getScoreColor(evaluation.overall_score)}`}>
          {evaluation.overall_score.toFixed(1)}
        </div>
        <p className="text-gray-500 text-sm">out of 10</p>

        <div className="flex justify-center gap-2 mt-3">
          <span className={`px-3 py-1 rounded-full text-sm font-medium ${getRiskColor(evaluation.risk_level)}`}>
            {evaluation.risk_level} Risk
          </span>
          <span className={`px-3 py-1 rounded-full text-sm font-medium ${
            evaluation.confidence === 'High' ? 'bg-green-100 text-green-700' :
            evaluation.confidence === 'Medium' ? 'bg-yellow-100 text-yellow-700' :
            'bg-red-100 text-red-700'
          }`}>
            {evaluation.confidence} Confidence
          </span>
        </div>
      </div>

      {/* Blocking Warning */}
      {evaluation.has_blocking_conflicts && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4">
          <p className="text-sm text-red-700 font-medium">
            ⚠️ Blocking conflicts detected - resolve before proceeding
          </p>
        </div>
      )}

      {/* Dimension Breakdown */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-gray-700">Score Breakdown</h3>
        {evaluation.dimension_scores.map((dim) => (
          <div key={dim.dimension} className="relative">
            <div className="flex justify-between items-center mb-1">
              <span className="text-sm text-gray-700">{dim.dimension}</span>
              <span className={`text-sm font-medium ${getScoreColor(dim.score)}`}>
                {dim.score.toFixed(1)} × {(dim.weight * 100).toFixed(0)}%
              </span>
            </div>
            <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full ${
                  dim.score >= 8 ? 'bg-green-500' :
                  dim.score >= 6 ? 'bg-yellow-500' :
                  dim.score >= 4 ? 'bg-orange-500' :
                  'bg-red-500'
                }`}
                style={{ width: `${dim.score * 10}%` }}
              />
            </div>
            {dim.warnings.length > 0 && (
              <p className="text-xs text-orange-600 mt-1">
                ⚠️ {dim.warnings[0]}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
