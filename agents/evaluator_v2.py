"""
Evaluator Agent v2 - Enhanced with Scoring & Conflict Detection
===============================================================
Deterministic and auditable evaluation of agent outputs.

Scoring Dimensions (weights):
- Profitability Safety: 30%
- Growth Impact: 25%
- Inventory Health: 20%
- Operational Risk: 15%
- Data Confidence: 10%

Conflict Detection Rules:
- CFO margin floor breached AND CMO recommends deeper promos → HIGH
- CIO data freshness FAIL → confidence = LOW, block decisions
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
import json
from datetime import datetime

from .base_agent import DatabaseConnection, create_db_connection
from .contract import AgentOutput, AgentRole, Confidence
from .handoff import (
    HandoffPayload, RiskFlag, Severity, DecisionConstraint,
    get_default_constraints, KPISummary
)


class ScoreDimension(Enum):
    """Scoring dimensions with weights."""
    PROFITABILITY_SAFETY = ("Profitability Safety", 0.30)
    GROWTH_IMPACT = ("Growth Impact", 0.25)
    INVENTORY_HEALTH = ("Inventory Health", 0.20)
    OPERATIONAL_RISK = ("Operational Risk", 0.15)
    DATA_CONFIDENCE = ("Data Confidence", 0.10)

    @property
    def label(self) -> str:
        return self.value[0]

    @property
    def weight(self) -> float:
        return self.value[1]


@dataclass
class DimensionScore:
    """Score for a single dimension."""
    dimension: str
    score: float  # 0-10
    weight: float
    weighted_score: float
    factors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Conflict:
    """A detected conflict between agents."""
    conflict_id: str
    between: List[str]
    issue: str
    severity: Severity
    details: Optional[str] = None
    resolution: Optional[str] = None
    constraint_violated: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "conflict_id": self.conflict_id,
            "between": self.between,
            "issue": self.issue,
            "severity": self.severity.value,
            "details": self.details,
            "resolution": self.resolution,
            "constraint_violated": self.constraint_violated,
        }


@dataclass
class EvaluatorDecision:
    """A recommended decision from the evaluator."""
    action: str
    impact: str
    confidence: str
    priority: str
    constraint_check: str = "PASS"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvaluatorOutput:
    """Complete evaluator output."""
    session_id: str
    timestamp: str
    overall_score: float  # 0-10
    risk_level: str  # Low/Medium/High/Critical
    confidence: str  # High/Medium/Low

    # Detailed scores
    dimension_scores: List[DimensionScore]

    # Conflicts
    conflicts: List[Conflict]
    has_blocking_conflicts: bool

    # Decisions
    decisions: List[EvaluatorDecision]

    # Constraints
    constraints_checked: Dict[str, Dict]
    constraints_violated: List[str]

    # Metadata
    agents_evaluated: List[str]
    data_freshness_ok: bool
    evaluation_reasons: List[str]

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "overall_score": round(self.overall_score, 2),
            "risk_level": self.risk_level,
            "confidence": self.confidence,
            "dimension_scores": [d.to_dict() for d in self.dimension_scores],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "has_blocking_conflicts": self.has_blocking_conflicts,
            "decisions": [d.to_dict() for d in self.decisions],
            "constraints_checked": self.constraints_checked,
            "constraints_violated": self.constraints_violated,
            "agents_evaluated": self.agents_evaluated,
            "data_freshness_ok": self.data_freshness_ok,
            "evaluation_reasons": self.evaluation_reasons,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class EvaluatorV2:
    """
    Enhanced Evaluator with deterministic scoring and conflict detection.
    """

    def __init__(self, db: DatabaseConnection = None):
        self.db = db or create_db_connection()
        self.constraints = get_default_constraints()
        self._conflict_counter = 0

    def evaluate(
        self,
        agent_outputs: Dict[str, AgentOutput],
        handoffs: List[HandoffPayload],
        session_id: str,
        constraints: Dict[str, DecisionConstraint] = None
    ) -> EvaluatorOutput:
        """
        Evaluate agent outputs and generate decisions.

        Args:
            agent_outputs: Dict mapping agent name to AgentOutput
            handoffs: List of handoff payloads from the flow
            session_id: Current session ID
            constraints: Optional custom constraints

        Returns:
            EvaluatorOutput with scores, conflicts, and decisions
        """
        if constraints:
            self.constraints.update(constraints)

        timestamp = datetime.now().isoformat()
        agents_evaluated = list(agent_outputs.keys())

        # 1. Check data confidence (CIO-driven)
        data_freshness_ok, confidence_reasons = self._check_data_confidence(
            agent_outputs.get("CIO")
        )

        # 2. Extract metrics for scoring
        metrics = self._extract_metrics(agent_outputs, handoffs)

        # 3. Check constraints
        constraints_checked, constraints_violated = self._check_constraints(metrics)

        # 4. Detect conflicts
        conflicts = self._detect_conflicts(agent_outputs, handoffs, metrics)
        has_blocking = any(c.severity in [Severity.HIGH, Severity.CRITICAL] for c in conflicts)

        # 5. Score each dimension
        dimension_scores = self._score_dimensions(metrics, data_freshness_ok, conflicts)

        # 6. Calculate overall score
        overall_score = sum(d.weighted_score for d in dimension_scores)

        # 7. Determine risk level
        risk_level = self._calculate_risk_level(overall_score, conflicts, constraints_violated)

        # 8. Determine confidence
        confidence = self._calculate_confidence(data_freshness_ok, metrics, conflicts)

        # 9. Generate decisions
        decisions = self._generate_decisions(
            metrics, conflicts, constraints_violated, agent_outputs
        )

        # 10. Compile evaluation reasons
        evaluation_reasons = confidence_reasons + [
            f"Evaluated {len(agents_evaluated)} agents",
            f"{len(conflicts)} conflicts detected",
            f"{len(constraints_violated)} constraints violated",
        ]

        return EvaluatorOutput(
            session_id=session_id,
            timestamp=timestamp,
            overall_score=overall_score,
            risk_level=risk_level,
            confidence=confidence,
            dimension_scores=dimension_scores,
            conflicts=conflicts,
            has_blocking_conflicts=has_blocking,
            decisions=decisions,
            constraints_checked=constraints_checked,
            constraints_violated=constraints_violated,
            agents_evaluated=agents_evaluated,
            data_freshness_ok=data_freshness_ok,
            evaluation_reasons=evaluation_reasons,
        )

    def _check_data_confidence(self, cio_output: Optional[AgentOutput]) -> Tuple[bool, List[str]]:
        """Check data freshness and quality from CIO agent."""
        reasons = []

        if not cio_output:
            reasons.append("CIO agent output not available - using database check")
            return self._check_data_freshness_direct(), reasons

        # Check CIO KPIs for data health
        for kpi in cio_output.kpis:
            if kpi.name == "Data Health Score":
                if kpi.value < 70:
                    reasons.append(f"Data health score low: {kpi.value}%")
                    return False, reasons
                reasons.append(f"Data health score: {kpi.value}%")

            if kpi.name == "Data Freshness":
                if kpi.value > 7:  # More than 7 days old
                    reasons.append(f"Data staleness warning: {kpi.value} days old")
                    return False, reasons

        # Check CIO risks
        for risk in cio_output.risks:
            if "FAIL" in risk.upper() or "STALE" in risk.upper():
                reasons.append(f"CIO risk flag: {risk[:50]}")
                return False, reasons

        reasons.append("Data freshness checks passed")
        return True, reasons

    def _check_data_freshness_direct(self) -> bool:
        """Direct database check for data freshness."""
        try:
            query = """
            SELECT
                MAX(CASE WHEN status = 'FAIL' THEN 1 ELSE 0 END) AS has_failures
            FROM cio_views.health_check_status
            """
            result = self.db.execute_query(query)
            return result[0]['has_failures'] == 0 if result else True
        except:
            return True

    def _extract_metrics(
        self,
        agent_outputs: Dict[str, AgentOutput],
        handoffs: List[HandoffPayload]
    ) -> Dict[str, Any]:
        """Extract key metrics from agent outputs and handoffs."""
        metrics = {
            "gross_margin_pct": None,
            "net_revenue": None,
            "inventory_days": None,
            "discount_rate": None,
            "repeat_rate": None,
            "data_health_score": None,
            "units_sold": None,
            "flags": set(),
        }

        # Extract from agent outputs
        for agent_name, output in agent_outputs.items():
            for kpi in output.kpis:
                name_lower = kpi.name.lower()
                if "margin" in name_lower and "gross" in name_lower:
                    metrics["gross_margin_pct"] = kpi.value
                elif "revenue" in name_lower and "net" in name_lower:
                    metrics["net_revenue"] = kpi.value
                elif "inventory" in name_lower and "day" in name_lower:
                    metrics["inventory_days"] = kpi.value
                elif "discount" in name_lower:
                    metrics["discount_rate"] = kpi.value
                elif "repeat" in name_lower:
                    metrics["repeat_rate"] = kpi.value
                elif "health" in name_lower:
                    metrics["data_health_score"] = kpi.value
                elif "units" in name_lower:
                    metrics["units_sold"] = kpi.value

        # Extract flags from handoffs
        for handoff in handoffs:
            metrics["flags"].update(handoff.flags)

        return metrics

    def _check_constraints(self, metrics: Dict) -> Tuple[Dict, List[str]]:
        """Check all constraints against current metrics."""
        checked = {}
        violated = []

        # Margin floor
        if metrics.get("gross_margin_pct") is not None:
            constraint = self.constraints["margin_floor"]
            passed = constraint.check(metrics["gross_margin_pct"])
            checked["margin_floor"] = {
                "name": constraint.name,
                "threshold": constraint.value,
                "actual": metrics["gross_margin_pct"],
                "status": "PASS" if passed else "VIOLATED",
            }
            if not passed:
                violated.append("margin_floor")

        # Max discount
        if metrics.get("discount_rate") is not None:
            constraint = self.constraints["max_discount"]
            passed = constraint.check(metrics["discount_rate"])
            checked["max_discount"] = {
                "name": constraint.name,
                "threshold": constraint.value,
                "actual": metrics["discount_rate"],
                "status": "PASS" if passed else "VIOLATED",
            }
            if not passed:
                violated.append("max_discount")

        # Inventory days
        if metrics.get("inventory_days") is not None:
            inv_days = metrics["inventory_days"]

            # Min check
            constraint_min = self.constraints["inventory_days_min"]
            passed_min = constraint_min.check(inv_days)

            # Max check
            constraint_max = self.constraints["inventory_days_max"]
            passed_max = constraint_max.check(inv_days)

            checked["inventory_days"] = {
                "name": "Inventory Days Target",
                "threshold": f"{constraint_min.value}-{constraint_max.value}",
                "actual": inv_days,
                "status": "PASS" if (passed_min and passed_max) else "VIOLATED",
            }
            if not passed_min:
                violated.append("inventory_days_min")
            if not passed_max:
                violated.append("inventory_days_max")

        return checked, violated

    def _detect_conflicts(
        self,
        agent_outputs: Dict[str, AgentOutput],
        handoffs: List[HandoffPayload],
        metrics: Dict
    ) -> List[Conflict]:
        """Detect conflicts between agent recommendations."""
        conflicts = []

        # Rule 1: CFO margin concern + CMO promo recommendation
        cfo_margin_concern = RiskFlag.MARGIN_BELOW_FLOOR.value in metrics["flags"]
        cmo_promo_push = False

        if "CMO" in agent_outputs:
            for rec in agent_outputs["CMO"].recommendations:
                if "promo" in rec.action.lower() or "discount" in rec.action.lower():
                    if "increase" in rec.action.lower() or "expand" in rec.action.lower():
                        cmo_promo_push = True

        if cfo_margin_concern and cmo_promo_push:
            conflicts.append(Conflict(
                conflict_id=self._next_conflict_id(),
                between=["CFO", "CMO"],
                issue="Promo depth violates margin floor",
                severity=Severity.HIGH,
                details=f"Margin at {metrics.get('gross_margin_pct', 'N/A')}% (floor: 18%)",
                resolution="Restrict promos to top-margin SKUs; Cap discount at 12%",
                constraint_violated="margin_floor",
            ))

        # Rule 2: High discount + low margin
        if metrics.get("discount_rate") and metrics.get("gross_margin_pct"):
            if metrics["discount_rate"] > 10 and metrics["gross_margin_pct"] < 20:
                conflicts.append(Conflict(
                    conflict_id=self._next_conflict_id(),
                    between=["CFO", "CMO"],
                    issue="Excessive discounting eroding margins",
                    severity=Severity.MEDIUM,
                    details=f"Discount {metrics['discount_rate']}%, Margin {metrics['gross_margin_pct']}%",
                    resolution="Review discount strategy; prioritize margin recovery",
                ))

        # Rule 3: Inventory out of range
        if metrics.get("inventory_days"):
            inv_days = metrics["inventory_days"]
            if inv_days < 30:
                conflicts.append(Conflict(
                    conflict_id=self._next_conflict_id(),
                    between=["CFO", "CEO"],
                    issue="Inventory critically low - stockout risk",
                    severity=Severity.HIGH,
                    details=f"Inventory days: {inv_days} (target: 45-60)",
                    resolution="Expedite purchase orders; review demand forecast",
                    constraint_violated="inventory_days_min",
                ))
            elif inv_days > 90:
                conflicts.append(Conflict(
                    conflict_id=self._next_conflict_id(),
                    between=["CFO", "CEO"],
                    issue="Inventory excess - cash flow concern",
                    severity=Severity.MEDIUM,
                    details=f"Inventory days: {inv_days} (target: 45-60)",
                    resolution="Run clearance promotions on slow movers",
                    constraint_violated="inventory_days_max",
                ))

        # Rule 4: Data quality issues
        if RiskFlag.DATA_STALE.value in metrics["flags"]:
            conflicts.append(Conflict(
                conflict_id=self._next_conflict_id(),
                between=["CIO", "ALL"],
                issue="Data freshness SLA breach - decisions may be unreliable",
                severity=Severity.CRITICAL,
                details="Data staleness detected by CIO agent",
                resolution="Block decisions until data pipeline restored",
            ))

        return conflicts

    def _next_conflict_id(self) -> str:
        """Generate next conflict ID."""
        self._conflict_counter += 1
        return f"C{self._conflict_counter:03d}"

    def _score_dimensions(
        self,
        metrics: Dict,
        data_freshness_ok: bool,
        conflicts: List[Conflict]
    ) -> List[DimensionScore]:
        """Score each dimension (0-10 scale)."""
        scores = []

        # 1. Profitability Safety (30%)
        dim = ScoreDimension.PROFITABILITY_SAFETY
        profit_score = 10.0
        profit_factors = []
        profit_warnings = []

        margin = metrics.get("gross_margin_pct")
        if margin is not None:
            if margin >= 25:
                profit_score = 10.0
                profit_factors.append(f"Strong margin: {margin:.1f}%")
            elif margin >= 20:
                profit_score = 8.0
                profit_factors.append(f"Healthy margin: {margin:.1f}%")
            elif margin >= 18:
                profit_score = 6.0
                profit_warnings.append(f"Margin near floor: {margin:.1f}%")
            else:
                profit_score = 3.0
                profit_warnings.append(f"Margin below floor: {margin:.1f}%")

        scores.append(DimensionScore(
            dimension=dim.label,
            score=profit_score,
            weight=dim.weight,
            weighted_score=profit_score * dim.weight,
            factors=profit_factors,
            warnings=profit_warnings,
        ))

        # 2. Growth Impact (25%)
        dim = ScoreDimension.GROWTH_IMPACT
        growth_score = 7.0  # Default neutral
        growth_factors = []
        growth_warnings = []

        revenue = metrics.get("net_revenue")
        if revenue is not None:
            growth_factors.append(f"Revenue: ${revenue:,.0f}")
            # Would compare to previous period if available
            growth_score = 7.5

        repeat_rate = metrics.get("repeat_rate")
        if repeat_rate is not None:
            if repeat_rate >= 50:
                growth_score += 1.0
                growth_factors.append(f"Strong retention: {repeat_rate:.1f}%")
            elif repeat_rate < 30:
                growth_score -= 1.0
                growth_warnings.append(f"Low retention: {repeat_rate:.1f}%")

        scores.append(DimensionScore(
            dimension=dim.label,
            score=min(10, growth_score),
            weight=dim.weight,
            weighted_score=min(10, growth_score) * dim.weight,
            factors=growth_factors,
            warnings=growth_warnings,
        ))

        # 3. Inventory Health (20%)
        dim = ScoreDimension.INVENTORY_HEALTH
        inv_score = 7.0
        inv_factors = []
        inv_warnings = []

        inv_days = metrics.get("inventory_days")
        if inv_days is not None:
            if 45 <= inv_days <= 60:
                inv_score = 10.0
                inv_factors.append(f"Optimal inventory: {inv_days:.0f} days")
            elif 30 <= inv_days < 45 or 60 < inv_days <= 75:
                inv_score = 7.0
                inv_warnings.append(f"Inventory outside target: {inv_days:.0f} days")
            else:
                inv_score = 4.0
                inv_warnings.append(f"Inventory critical: {inv_days:.0f} days")

        scores.append(DimensionScore(
            dimension=dim.label,
            score=inv_score,
            weight=dim.weight,
            weighted_score=inv_score * dim.weight,
            factors=inv_factors,
            warnings=inv_warnings,
        ))

        # 4. Operational Risk (15%)
        dim = ScoreDimension.OPERATIONAL_RISK
        ops_score = 8.0
        ops_factors = []
        ops_warnings = []

        # Deduct for conflicts
        high_conflicts = sum(1 for c in conflicts if c.severity in [Severity.HIGH, Severity.CRITICAL])
        med_conflicts = sum(1 for c in conflicts if c.severity == Severity.MEDIUM)

        if high_conflicts > 0:
            ops_score -= high_conflicts * 2
            ops_warnings.append(f"{high_conflicts} high-severity conflicts")
        if med_conflicts > 0:
            ops_score -= med_conflicts * 0.5
            ops_warnings.append(f"{med_conflicts} medium-severity conflicts")

        if ops_score >= 7:
            ops_factors.append("Operations stable")

        scores.append(DimensionScore(
            dimension=dim.label,
            score=max(0, ops_score),
            weight=dim.weight,
            weighted_score=max(0, ops_score) * dim.weight,
            factors=ops_factors,
            warnings=ops_warnings,
        ))

        # 5. Data Confidence (10%)
        dim = ScoreDimension.DATA_CONFIDENCE
        data_score = 10.0 if data_freshness_ok else 3.0
        data_factors = []
        data_warnings = []

        health_score = metrics.get("data_health_score")
        if health_score is not None:
            if health_score >= 90:
                data_factors.append(f"Data health excellent: {health_score}%")
            elif health_score >= 70:
                data_score = 7.0
                data_factors.append(f"Data health acceptable: {health_score}%")
            else:
                data_score = 4.0
                data_warnings.append(f"Data health concerns: {health_score}%")

        if not data_freshness_ok:
            data_warnings.append("Data freshness SLA breach")

        scores.append(DimensionScore(
            dimension=dim.label,
            score=data_score,
            weight=dim.weight,
            weighted_score=data_score * dim.weight,
            factors=data_factors,
            warnings=data_warnings,
        ))

        return scores

    def _calculate_risk_level(
        self,
        overall_score: float,
        conflicts: List[Conflict],
        constraints_violated: List[str]
    ) -> str:
        """Calculate overall risk level."""
        # Check for critical conflicts
        if any(c.severity == Severity.CRITICAL for c in conflicts):
            return "Critical"

        # Check for multiple high conflicts
        high_count = sum(1 for c in conflicts if c.severity == Severity.HIGH)
        if high_count >= 2:
            return "High"

        # Check score + constraints
        if overall_score < 5.0 or len(constraints_violated) >= 2:
            return "High"
        elif overall_score < 6.5 or len(constraints_violated) >= 1:
            return "Medium"
        else:
            return "Low"

    def _calculate_confidence(
        self,
        data_freshness_ok: bool,
        metrics: Dict,
        conflicts: List[Conflict]
    ) -> str:
        """Calculate confidence level."""
        if not data_freshness_ok:
            return "Low"

        if any(c.severity == Severity.CRITICAL for c in conflicts):
            return "Low"

        health_score = metrics.get("data_health_score")
        if health_score and health_score < 70:
            return "Low"

        if len(conflicts) > 2:
            return "Medium"

        return "High"

    def _generate_decisions(
        self,
        metrics: Dict,
        conflicts: List[Conflict],
        constraints_violated: List[str],
        agent_outputs: Dict[str, AgentOutput]
    ) -> List[EvaluatorDecision]:
        """Generate actionable decisions."""
        decisions = []

        # Address margin constraint
        if "margin_floor" in constraints_violated:
            decisions.append(EvaluatorDecision(
                action="Review category-level pricing to restore margin above 18%",
                impact="+1-2 margin points",
                confidence="High",
                priority="High",
                constraint_check="margin_floor VIOLATED",
            ))

        # Address discount issues
        if "max_discount" in constraints_violated:
            decisions.append(EvaluatorDecision(
                action="Cap promotional discounts at 12% maximum",
                impact="Protect 0.5-1.0 margin points",
                confidence="High",
                priority="High",
                constraint_check="max_discount VIOLATED",
            ))

        # Address conflicts
        for conflict in conflicts:
            if conflict.resolution and conflict.severity in [Severity.HIGH, Severity.CRITICAL]:
                decisions.append(EvaluatorDecision(
                    action=conflict.resolution,
                    impact=f"Resolve {conflict.severity.value} conflict: {conflict.issue}",
                    confidence="Medium",
                    priority="High" if conflict.severity == Severity.CRITICAL else "Medium",
                ))

        # Add top agent recommendations that don't conflict
        for agent_name, output in agent_outputs.items():
            for rec in output.recommendations[:1]:  # Top recommendation only
                # Skip if conflicts with constraints
                skip = False
                if "promo" in rec.action.lower() and "margin_floor" in constraints_violated:
                    skip = True
                if "discount" in rec.action.lower() and "max_discount" in constraints_violated:
                    skip = True

                if not skip:
                    decisions.append(EvaluatorDecision(
                        action=f"[{agent_name}] {rec.action}",
                        impact=rec.impact,
                        confidence="Medium",
                        priority=rec.priority,
                    ))

        # Limit to top 5 decisions
        return decisions[:5]


# Helper function for quick evaluation
def evaluate_boardroom(
    agent_outputs: Dict[str, AgentOutput],
    handoffs: List[HandoffPayload] = None,
    session_id: str = None
) -> EvaluatorOutput:
    """Quick evaluation of boardroom outputs."""
    import uuid
    evaluator = EvaluatorV2()
    return evaluator.evaluate(
        agent_outputs=agent_outputs,
        handoffs=handoffs or [],
        session_id=session_id or str(uuid.uuid4())[:8],
    )
