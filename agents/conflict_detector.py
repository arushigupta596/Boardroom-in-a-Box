"""
Conflict Detector - LLM-Powered Soft Signal Detection
======================================================
Detects conflicts between agent recommendations that hard rules might miss.

The LLM identifies:
- Contradictory recommendations
- Misaligned priorities
- Missing assumptions
- Implicit tensions

Hard rules (margin floor, discount caps) are still enforced deterministically.
The LLM provides advisory signals that the Evaluator can use.
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum

from .llm_client import LLMClient, LLMModel, get_llm_client
from .contract import AgentOutput, Recommendation


class ConflictSeverity(Enum):
    """Severity of detected conflict."""
    LOW = "low"          # Minor tension, can proceed
    MEDIUM = "medium"    # Notable conflict, needs review
    HIGH = "high"        # Significant conflict, requires resolution
    CRITICAL = "critical"  # Blocking conflict, cannot proceed


@dataclass
class DetectedConflict:
    """A detected conflict between agents."""
    conflict_id: str
    agents_involved: List[str]
    conflict_type: str
    description: str
    severity: ConflictSeverity
    evidence: Dict[str, str]  # Agent -> their position
    suggested_resolution: str
    confidence: float  # 0-1, how confident is the LLM


@dataclass
class ConflictReport:
    """Full conflict analysis report."""
    conflicts: List[DetectedConflict]
    tensions: List[str]  # Minor tensions that aren't full conflicts
    alignment_score: float  # 0-1, how aligned are the agents
    summary: str


CONFLICT_SYSTEM_PROMPT = """You are a conflict detector for a retail boardroom system.
You analyze recommendations from multiple agents and identify conflicts, tensions, and misalignments.

AGENTS AND THEIR PRIORITIES:
- CEO: Growth, market share, strategic positioning
- CFO: Profitability, margin protection, cost control, cash flow
- CMO: Sales volume, customer acquisition, market penetration, promotions

COMMON CONFLICT PATTERNS:
1. Margin vs Volume: CFO wants margin protection, CMO wants volume through discounts
2. Cost vs Growth: CFO wants to cut costs, CEO wants to invest in growth
3. Short-term vs Long-term: Different time horizon priorities
4. Risk appetite: Conservative CFO vs aggressive CMO
5. Inventory: CFO wants to reduce, CMO wants availability

HARD CONSTRAINTS (these are non-negotiable):
- Margin floor: 18% minimum gross margin
- Max discount: 15% maximum discount rate
- Inventory days: 30-90 days target range

Your job is to find SOFT conflicts - tensions that aren't captured by hard rules.

Analyze the recommendations and identify:
1. Direct contradictions (A says X, B says not-X)
2. Implicit tensions (goals that work against each other)
3. Missing assumptions (what each agent assumes that others don't)
4. Priority misalignments (different urgency levels)

Respond in JSON format:
{
  "conflicts": [
    {
      "conflict_id": "conflict_1",
      "agents_involved": ["CFO", "CMO"],
      "conflict_type": "margin_vs_volume",
      "description": "Brief description of the conflict",
      "severity": "low|medium|high|critical",
      "evidence": {
        "CFO": "CFO's position/recommendation",
        "CMO": "CMO's position/recommendation"
      },
      "suggested_resolution": "How to resolve this conflict",
      "confidence": 0.0-1.0
    }
  ],
  "tensions": ["Minor tension 1", "Minor tension 2"],
  "alignment_score": 0.0-1.0,
  "summary": "Overall assessment of agent alignment"
}
"""


class ConflictDetector:
    """
    LLM-powered conflict detector.

    Analyzes agent outputs to find soft conflicts that
    hard rules might miss.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client

    def _get_llm(self) -> LLMClient:
        """Get LLM client (lazy initialization)."""
        if self.llm is None:
            self.llm = get_llm_client()
        return self.llm

    def detect_conflicts(
        self,
        agent_outputs: Dict[str, AgentOutput],
        constraints: Optional[Dict[str, Any]] = None,
    ) -> ConflictReport:
        """
        Detect conflicts between agent recommendations.

        Args:
            agent_outputs: Dict of agent name -> AgentOutput
            constraints: Optional hard constraints for context

        Returns:
            ConflictReport with detected conflicts
        """
        # Format agent outputs for LLM
        agent_summary = self._format_agent_outputs(agent_outputs)

        # Format constraints
        constraints_text = self._format_constraints(constraints or {})

        prompt = f"""Analyze these agent outputs for conflicts:

{agent_summary}

Hard constraints in effect:
{constraints_text}

Identify any soft conflicts, tensions, or misalignments between agents."""

        try:
            llm = self._get_llm()
            result = llm.complete_json(
                prompt=prompt,
                system=CONFLICT_SYSTEM_PROMPT,
                model=LLMModel.CLAUDE_HAIKU,
                temperature=0.2,
            )

            return self._parse_result(result)

        except Exception as e:
            # Return empty report on error
            return ConflictReport(
                conflicts=[],
                tensions=[],
                alignment_score=0.8,
                summary=f"Conflict detection failed: {str(e)}",
            )

    def _format_agent_outputs(self, outputs: Dict[str, AgentOutput]) -> str:
        """Format agent outputs for LLM analysis."""
        lines = []

        for agent_name, output in outputs.items():
            lines.append(f"=== {agent_name} ===")

            # Add insights
            if output.insights:
                lines.append("Insights:")
                for insight in output.insights[:3]:
                    lines.append(f"  - {insight}")

            # Add risks
            if output.risks:
                lines.append("Risks identified:")
                for risk in output.risks[:3]:
                    lines.append(f"  - {risk}")

            # Add recommendations
            if output.recommendations:
                lines.append("Recommendations:")
                for rec in output.recommendations[:3]:
                    if isinstance(rec, Recommendation):
                        lines.append(f"  - {rec.action} (Priority: {rec.priority})")
                    else:
                        lines.append(f"  - {rec}")

            lines.append("")

        return "\n".join(lines)

    def _format_constraints(self, constraints: Dict[str, Any]) -> str:
        """Format constraints for context."""
        if not constraints:
            return "- Margin floor: 18%\n- Max discount: 15%\n- Inventory days: 30-90"

        lines = []
        for key, value in constraints.items():
            if isinstance(value, dict):
                lines.append(f"- {key}: {value.get('value', 'N/A')} {value.get('unit', '')}")
            else:
                lines.append(f"- {key}: {value}")

        return "\n".join(lines)

    def _parse_result(self, result: Dict) -> ConflictReport:
        """Parse LLM result into ConflictReport."""
        conflicts = []

        for i, c in enumerate(result.get("conflicts", [])):
            try:
                severity = ConflictSeverity(c.get("severity", "medium"))
            except ValueError:
                severity = ConflictSeverity.MEDIUM

            conflicts.append(DetectedConflict(
                conflict_id=c.get("conflict_id", f"conflict_{i+1}"),
                agents_involved=c.get("agents_involved", []),
                conflict_type=c.get("conflict_type", "unknown"),
                description=c.get("description", ""),
                severity=severity,
                evidence=c.get("evidence", {}),
                suggested_resolution=c.get("suggested_resolution", ""),
                confidence=c.get("confidence", 0.5),
            ))

        return ConflictReport(
            conflicts=conflicts,
            tensions=result.get("tensions", []),
            alignment_score=result.get("alignment_score", 0.8),
            summary=result.get("summary", ""),
        )

    def quick_check(
        self,
        cfo_recommendation: str,
        cmo_recommendation: str,
    ) -> Optional[DetectedConflict]:
        """
        Quick check for obvious CFO vs CMO conflicts.

        Example:
            CFO: "Cut promos"
            CMO: "Increase promos"
            → Conflict detected

        Args:
            cfo_recommendation: CFO's recommendation text
            cmo_recommendation: CMO's recommendation text

        Returns:
            DetectedConflict if found, None otherwise
        """
        prompt = f"""Check if these two recommendations conflict:

CFO says: "{cfo_recommendation}"
CMO says: "{cmo_recommendation}"

If they conflict, respond with JSON:
{{
  "conflicts": true,
  "conflict_type": "type of conflict",
  "description": "brief description",
  "severity": "low|medium|high",
  "resolution": "suggested resolution"
}}

If no conflict, respond with:
{{
  "conflicts": false
}}
"""

        try:
            llm = self._get_llm()
            result = llm.complete_json(
                prompt=prompt,
                system="You detect conflicts between CFO and CMO recommendations.",
                model=LLMModel.CLAUDE_HAIKU,
                temperature=0.1,
            )

            if result.get("conflicts"):
                return DetectedConflict(
                    conflict_id="quick_check_1",
                    agents_involved=["CFO", "CMO"],
                    conflict_type=result.get("conflict_type", "strategy_conflict"),
                    description=result.get("description", ""),
                    severity=ConflictSeverity(result.get("severity", "medium")),
                    evidence={
                        "CFO": cfo_recommendation,
                        "CMO": cmo_recommendation,
                    },
                    suggested_resolution=result.get("resolution", ""),
                    confidence=0.8,
                )

            return None

        except Exception:
            return None


# Convenience function
def detect_conflicts(
    agent_outputs: Dict[str, AgentOutput],
    constraints: Optional[Dict[str, Any]] = None,
) -> ConflictReport:
    """Detect conflicts between agent outputs."""
    detector = ConflictDetector()
    return detector.detect_conflicts(agent_outputs, constraints)
