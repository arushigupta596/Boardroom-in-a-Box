"""
Evaluator Agent
===============
Scores and validates agent outputs for quality, consistency, and actionability.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import json

from .contract import (
    AgentOutput, AgentRole, KPI, Recommendation, Evidence,
    Trend, Confidence, validate_agent_output
)
from .base_agent import DatabaseConnection


@dataclass
class EvaluationScore:
    """Score for a single evaluation dimension."""
    dimension: str
    score: float  # 0-100
    max_score: float
    details: str


@dataclass
class AgentEvaluation:
    """Complete evaluation of an agent's output."""
    agent: str
    overall_score: float
    grade: str  # A, B, C, D, F
    scores: List[EvaluationScore]
    passed: bool
    feedback: List[str]
    timestamp: str

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "overall_score": self.overall_score,
            "grade": self.grade,
            "scores": [
                {
                    "dimension": s.dimension,
                    "score": s.score,
                    "max_score": s.max_score,
                    "details": s.details
                }
                for s in self.scores
            ],
            "passed": self.passed,
            "feedback": self.feedback,
            "timestamp": self.timestamp
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


@dataclass
class BoardroomEvaluation:
    """Evaluation of the entire boardroom (all agents)."""
    overall_score: float
    grade: str
    agent_evaluations: List[AgentEvaluation]
    cross_agent_consistency: float
    data_health_status: str
    timestamp: str
    summary: str

    def to_dict(self) -> dict:
        return {
            "overall_score": self.overall_score,
            "grade": self.grade,
            "agent_evaluations": [e.to_dict() for e in self.agent_evaluations],
            "cross_agent_consistency": self.cross_agent_consistency,
            "data_health_status": self.data_health_status,
            "timestamp": self.timestamp,
            "summary": self.summary
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


class EvaluatorAgent:
    """
    Evaluator Agent scores agent outputs on multiple dimensions:

    1. Completeness (20%): Are all required fields present?
    2. Evidence Quality (25%): Are claims backed by proper evidence?
    3. Actionability (20%): Are recommendations specific and actionable?
    4. Insight Quality (20%): Are insights non-obvious and valuable?
    5. Consistency (15%): Does output align with data reality?

    Scoring: 0-100, with letter grades:
    - A: 90-100 (Excellent)
    - B: 80-89 (Good)
    - C: 70-79 (Acceptable)
    - D: 60-69 (Needs Improvement)
    - F: <60 (Failing)
    """

    # Weights for each evaluation dimension
    WEIGHTS = {
        'completeness': 0.20,
        'evidence_quality': 0.25,
        'actionability': 0.20,
        'insight_quality': 0.20,
        'consistency': 0.15
    }

    # Minimum passing score
    PASSING_SCORE = 70

    def __init__(self, db: DatabaseConnection = None):
        self.db = db or DatabaseConnection()

    def evaluate_agent(self, output: AgentOutput) -> AgentEvaluation:
        """Evaluate a single agent's output."""
        scores = []

        # 1. Completeness check
        completeness_score = self._evaluate_completeness(output)
        scores.append(completeness_score)

        # 2. Evidence quality
        evidence_score = self._evaluate_evidence(output)
        scores.append(evidence_score)

        # 3. Actionability of recommendations
        actionability_score = self._evaluate_actionability(output)
        scores.append(actionability_score)

        # 4. Insight quality
        insight_score = self._evaluate_insights(output)
        scores.append(insight_score)

        # 5. Consistency with data
        consistency_score = self._evaluate_consistency(output)
        scores.append(consistency_score)

        # Calculate weighted overall score
        overall_score = sum(
            s.score * self.WEIGHTS.get(s.dimension, 0)
            for s in scores
        )

        # Determine grade
        grade = self._score_to_grade(overall_score)

        # Generate feedback
        feedback = self._generate_feedback(scores, output)

        return AgentEvaluation(
            agent=output.agent.value,
            overall_score=round(overall_score, 1),
            grade=grade,
            scores=scores,
            passed=overall_score >= self.PASSING_SCORE,
            feedback=feedback,
            timestamp=datetime.now().isoformat()
        )

    def evaluate_boardroom(self, outputs: List[AgentOutput]) -> BoardroomEvaluation:
        """Evaluate all agent outputs together."""
        agent_evaluations = [self.evaluate_agent(o) for o in outputs]

        # Calculate overall boardroom score
        overall_score = sum(e.overall_score for e in agent_evaluations) / len(agent_evaluations)

        # Check cross-agent consistency
        consistency_score = self._evaluate_cross_agent_consistency(outputs)

        # Check data health
        data_health = self._get_data_health_status()

        # Generate summary
        summary = self._generate_boardroom_summary(
            agent_evaluations, consistency_score, data_health
        )

        return BoardroomEvaluation(
            overall_score=round(overall_score, 1),
            grade=self._score_to_grade(overall_score),
            agent_evaluations=agent_evaluations,
            cross_agent_consistency=consistency_score,
            data_health_status=data_health,
            timestamp=datetime.now().isoformat(),
            summary=summary
        )

    def _evaluate_completeness(self, output: AgentOutput) -> EvaluationScore:
        """Check if all required fields are present and populated."""
        score = 100.0
        issues = []

        # Check required fields
        validation_errors = validate_agent_output(output)
        if validation_errors:
            score -= len(validation_errors) * 10
            issues.extend(validation_errors)

        # Check KPI quality
        if len(output.kpis) < 2:
            score -= 15
            issues.append("Fewer than 2 KPIs provided")

        for kpi in output.kpis:
            if kpi.value is None or kpi.value == 0:
                score -= 5
                issues.append(f"KPI '{kpi.name}' has zero/null value")

        # Check insights depth
        if not output.insights:
            score -= 20
            issues.append("No insights provided")
        elif all(len(i) < 20 for i in output.insights):
            score -= 10
            issues.append("Insights too brief")

        # Check recommendations
        if not output.recommendations:
            score -= 15
            issues.append("No recommendations provided")

        score = max(0, score)
        details = "; ".join(issues) if issues else "All required fields present"

        return EvaluationScore(
            dimension="completeness",
            score=score,
            max_score=100,
            details=details
        )

    def _evaluate_evidence(self, output: AgentOutput) -> EvaluationScore:
        """Check quality and relevance of evidence cited."""
        score = 100.0
        issues = []

        if not output.evidence:
            return EvaluationScore(
                dimension="evidence_quality",
                score=0,
                max_score=100,
                details="No evidence provided"
            )

        # Check each evidence entry
        valid_views = self._get_valid_views()

        for ev in output.evidence:
            # Check if view exists
            if ev.view.split('+')[0].strip() not in valid_views:
                # Allow joined views
                base_view = ev.view.split('+')[0].strip()
                if base_view not in valid_views and 'retail.' + base_view not in valid_views:
                    score -= 10
                    issues.append(f"Unknown view: {ev.view}")

            # Check if filters are specified
            if not ev.filters or ev.filters == "":
                score -= 5
                issues.append(f"No filters specified for {ev.view}")

        # Bonus for multiple evidence sources
        if len(output.evidence) >= 3:
            score = min(100, score + 5)

        score = max(0, score)
        details = "; ".join(issues) if issues else f"Evidence quality good ({len(output.evidence)} sources)"

        return EvaluationScore(
            dimension="evidence_quality",
            score=score,
            max_score=100,
            details=details
        )

    def _evaluate_actionability(self, output: AgentOutput) -> EvaluationScore:
        """Check if recommendations are specific and actionable."""
        score = 100.0
        issues = []

        if not output.recommendations:
            return EvaluationScore(
                dimension="actionability",
                score=30,
                max_score=100,
                details="No recommendations to evaluate"
            )

        for rec in output.recommendations:
            # Check action specificity
            if len(rec.action) < 20:
                score -= 10
                issues.append(f"Recommendation too vague: '{rec.action[:30]}...'")

            # Check impact is quantified or specific
            if not rec.impact or len(rec.impact) < 10:
                score -= 10
                issues.append("Impact not specified")

            # Check for actionable verbs
            action_verbs = ['implement', 'launch', 'review', 'cap', 'increase',
                          'reduce', 'analyze', 'expand', 'optimize', 'schedule']
            if not any(verb in rec.action.lower() for verb in action_verbs):
                score -= 5
                issues.append(f"Recommendation lacks action verb: '{rec.action[:30]}...'")

        score = max(0, score)
        details = "; ".join(issues) if issues else "Recommendations are actionable"

        return EvaluationScore(
            dimension="actionability",
            score=score,
            max_score=100,
            details=details
        )

    def _evaluate_insights(self, output: AgentOutput) -> EvaluationScore:
        """Check if insights are valuable and non-obvious."""
        score = 100.0
        issues = []

        if not output.insights:
            return EvaluationScore(
                dimension="insight_quality",
                score=20,
                max_score=100,
                details="No insights to evaluate"
            )

        for insight in output.insights:
            # Check for specificity (numbers, percentages, names)
            has_numbers = any(c.isdigit() for c in insight)
            has_specifics = any(term in insight.lower() for term in
                              ['%', '$', 'category', 'store', 'sku', 'margin', 'revenue'])

            if not has_numbers and not has_specifics:
                score -= 15
                issues.append(f"Insight lacks specifics: '{insight[:40]}...'")

            # Check minimum length for substance
            if len(insight) < 30:
                score -= 10
                issues.append(f"Insight too brief: '{insight}'")

        # Penalize generic insights
        generic_phrases = ['is important', 'should be considered', 'needs attention']
        for insight in output.insights:
            if any(phrase in insight.lower() for phrase in generic_phrases):
                score -= 10
                issues.append("Contains generic phrasing")

        score = max(0, score)
        details = "; ".join(issues) if issues else "Insights are specific and valuable"

        return EvaluationScore(
            dimension="insight_quality",
            score=score,
            max_score=100,
            details=details
        )

    def _evaluate_consistency(self, output: AgentOutput) -> EvaluationScore:
        """Check if output is consistent with actual data."""
        score = 100.0
        issues = []

        # Verify KPI values against actual data
        try:
            actual_data = self._get_actual_metrics()

            for kpi in output.kpis:
                if kpi.name == "Net Revenue" and actual_data.get('net_revenue'):
                    expected = actual_data['net_revenue']
                    if abs(kpi.value - expected) / max(expected, 1) > 0.1:
                        score -= 20
                        issues.append(f"Net Revenue mismatch: reported {kpi.value}, actual {expected}")

                if kpi.name == "Units Sold" and actual_data.get('units_sold'):
                    expected = actual_data['units_sold']
                    if abs(kpi.value - expected) / max(expected, 1) > 0.1:
                        score -= 20
                        issues.append(f"Units Sold mismatch: reported {kpi.value}, actual {expected}")

        except Exception as e:
            score -= 10
            issues.append(f"Could not verify data consistency: {str(e)}")

        score = max(0, score)
        details = "; ".join(issues) if issues else "Output consistent with data"

        return EvaluationScore(
            dimension="consistency",
            score=score,
            max_score=100,
            details=details
        )

    def _evaluate_cross_agent_consistency(self, outputs: List[AgentOutput]) -> float:
        """Check consistency across multiple agents' outputs."""
        if len(outputs) < 2:
            return 100.0

        score = 100.0

        # Extract revenue figures from all agents
        revenues = []
        for output in outputs:
            for kpi in output.kpis:
                if 'revenue' in kpi.name.lower():
                    revenues.append(kpi.value)

        # Check if revenue figures are consistent
        if len(revenues) >= 2:
            max_rev = max(revenues)
            min_rev = min(revenues)
            if max_rev > 0 and (max_rev - min_rev) / max_rev > 0.05:
                score -= 20  # More than 5% difference

        # Check confidence alignment
        confidences = [o.confidence.value for o in outputs]
        if len(set(confidences)) > 2:
            score -= 10  # Too much confidence variation

        return max(0, score)

    def _get_data_health_status(self) -> str:
        """Get current data health status."""
        try:
            query = """
            SELECT
                COUNT(*) FILTER (WHERE status = 'PASS') as passed,
                COUNT(*) FILTER (WHERE status = 'WARN') as warned,
                COUNT(*) FILTER (WHERE status = 'FAIL') as failed,
                COUNT(*) as total
            FROM retail.data_health_checks
            WHERE run_ts = (SELECT MAX(run_ts) FROM retail.data_health_checks)
            """
            result = self.db.execute_query(query)
            if result:
                data = result[0]
                if data['failed'] > 0:
                    return "FAIL"
                elif data['warned'] > 0:
                    return "WARN"
                else:
                    return "PASS"
        except:
            pass
        return "UNKNOWN"

    def _get_valid_views(self) -> set:
        """Get list of valid views/tables in all allowed schemas."""
        try:
            query = """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema IN ('retail', 'ceo_views', 'cfo_views', 'cmo_views', 'cio_views')
            UNION
            SELECT table_schema, table_name
            FROM information_schema.views
            WHERE table_schema IN ('retail', 'ceo_views', 'cfo_views', 'cmo_views', 'cio_views')
            """
            result = self.db.execute_query(query)
            views = set()
            for r in result:
                views.add(f"{r['table_schema']}.{r['table_name']}")
                views.add(r['table_name'])
            return views
        except:
            return set()

    def _get_actual_metrics(self) -> dict:
        """Get actual metrics from the database for verification."""
        try:
            query = "SELECT * FROM retail.v_board_summary"
            result = self.db.execute_query(query)
            if result:
                return {
                    'net_revenue': result[0].get('net_revenue', 0),
                    'units_sold': result[0].get('units_sold', 0)
                }
        except:
            pass
        return {}

    def _score_to_grade(self, score: float) -> str:
        """Convert numeric score to letter grade."""
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"

    def _generate_feedback(self, scores: List[EvaluationScore], output: AgentOutput) -> List[str]:
        """Generate actionable feedback for the agent."""
        feedback = []

        for s in scores:
            if s.score < 70:
                feedback.append(f"Improve {s.dimension}: {s.details}")

        if not feedback:
            feedback.append(f"{output.agent.value} output meets quality standards.")

        return feedback[:5]  # Limit to 5 items

    def _generate_boardroom_summary(
        self,
        evaluations: List[AgentEvaluation],
        consistency: float,
        data_health: str
    ) -> str:
        """Generate executive summary of boardroom evaluation."""
        passed = sum(1 for e in evaluations if e.passed)
        total = len(evaluations)

        grades = [e.grade for e in evaluations]
        agents_by_grade = {g: [e.agent for e in evaluations if e.grade == g] for g in set(grades)}

        summary_parts = [
            f"Boardroom Evaluation: {passed}/{total} agents passing.",
            f"Data Health: {data_health}.",
            f"Cross-Agent Consistency: {consistency:.0f}%."
        ]

        if 'A' in agents_by_grade:
            summary_parts.append(f"Top performers: {', '.join(agents_by_grade['A'])}.")

        if 'F' in agents_by_grade:
            summary_parts.append(f"Needs attention: {', '.join(agents_by_grade['F'])}.")

        return " ".join(summary_parts)


# CLI interface
if __name__ == "__main__":
    import sys
    from .ceo_agent import CEOAgent
    from .cfo_agent import CFOAgent
    from .cmo_agent import CMOAgent
    from .cio_agent import CIOAgent

    # Run all agents and evaluate
    agents = [CEOAgent(), CFOAgent(), CMOAgent(), CIOAgent()]
    outputs = []

    print("Running all agents...")
    for agent in agents:
        output = agent.analyze()
        outputs.append(output)
        print(f"  {agent.role.value}: Complete")

    print("\nEvaluating boardroom...")
    evaluator = EvaluatorAgent()
    evaluation = evaluator.evaluate_boardroom(outputs)

    print("\n" + "=" * 60)
    print("BOARDROOM EVALUATION REPORT")
    print("=" * 60)
    print(evaluation.to_json())
