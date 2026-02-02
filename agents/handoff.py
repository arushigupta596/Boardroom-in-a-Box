"""
Handoff Objects - Agent Communication Protocol
==============================================
Defines the standard payload structure for agent-to-agent communication.
Makes the "baton passing" visible and consistent.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from enum import Enum
from datetime import datetime
import json


class RiskFlag(Enum):
    """Standard risk flags that agents can raise."""
    MARGIN_BELOW_FLOOR = "MARGIN_BELOW_FLOOR"
    MARGIN_CRITICAL = "MARGIN_CRITICAL"
    INVENTORY_HIGH = "INVENTORY_HIGH"
    INVENTORY_LOW = "INVENTORY_LOW"
    REVENUE_DECLINING = "REVENUE_DECLINING"
    PROMO_CANNIBALIZATION = "PROMO_CANNIBALIZATION"
    DATA_STALE = "DATA_STALE"
    DATA_QUALITY_ISSUE = "DATA_QUALITY_ISSUE"
    REGIONAL_CONCENTRATION = "REGIONAL_CONCENTRATION"
    CUSTOMER_CHURN_RISK = "CUSTOMER_CHURN_RISK"
    SSSG_NEGATIVE = "SSSG_NEGATIVE"
    DISCOUNT_EXCESSIVE = "DISCOUNT_EXCESSIVE"
    RETURNS_HIGH = "RETURNS_HIGH"


class Severity(Enum):
    """Severity levels for flags and conflicts."""
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


@dataclass
class FocusArea:
    """A specific area requiring attention."""
    category: Optional[str] = None
    stores: Optional[List[str]] = None
    skus: Optional[List[str]] = None
    region: Optional[str] = None
    segment: Optional[str] = None
    metric: Optional[str] = None
    value: Optional[float] = None
    threshold: Optional[float] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class EvidenceRef:
    """Reference to evidence used in analysis."""
    view: str
    query_id: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None
    row_count: Optional[int] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class KPISummary:
    """Summary of key metrics for handoff."""
    name: str
    value: float
    unit: str
    trend: str  # UP, DOWN, FLAT
    definition: Optional[str] = None
    source_view: Optional[str] = None
    window: Optional[str] = None
    confidence: str = "High"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DecisionConstraint:
    """A constraint that must be respected in decisions."""
    name: str
    operator: str  # >=, <=, ==, between
    value: Any
    unit: Optional[str] = None
    is_violated: bool = False
    current_value: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def check(self, actual_value: float) -> bool:
        """Check if constraint is violated."""
        self.current_value = actual_value
        if self.operator == ">=":
            self.is_violated = actual_value < self.value
        elif self.operator == "<=":
            self.is_violated = actual_value > self.value
        elif self.operator == "==":
            self.is_violated = actual_value != self.value
        elif self.operator == "between":
            low, high = self.value
            self.is_violated = actual_value < low or actual_value > high
        return not self.is_violated


@dataclass
class Signal:
    """A signal/observation passed between agents."""
    metric: str
    value: float
    direction: str  # UP, DOWN, FLAT
    severity: Severity = Severity.MEDIUM
    context: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d['severity'] = self.severity.value
        return d


@dataclass
class HandoffPayload:
    """
    Standard handoff payload between agents.

    This is the "baton" that gets passed from one agent to the next,
    containing all context needed for the receiving agent to continue.
    """
    handoff_from: str  # Agent name
    handoff_to: str  # Target agent name
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # Core content
    kpi_summary: List[KPISummary] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)  # RiskFlag values
    signals: List[Signal] = field(default_factory=list)

    # Focus and constraints
    focus_areas: List[FocusArea] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)

    # Evidence trail
    evidence: List[EvidenceRef] = field(default_factory=list)

    # Reason for handoff
    reason: Optional[str] = None
    priority: Severity = Severity.MEDIUM

    # Session context
    session_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "handoff_from": self.handoff_from,
            "handoff_to": self.handoff_to,
            "timestamp": self.timestamp,
            "reason": self.reason,
            "priority": self.priority.value,
            "kpi_summary": [k.to_dict() for k in self.kpi_summary],
            "flags": self.flags,
            "signals": [s.to_dict() for s in self.signals],
            "focus_areas": [f.to_dict() for f in self.focus_areas],
            "constraints": self.constraints,
            "evidence": [e.to_dict() for e in self.evidence],
            "session_id": self.session_id,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> 'HandoffPayload':
        """Reconstruct from dictionary."""
        return cls(
            handoff_from=data["handoff_from"],
            handoff_to=data["handoff_to"],
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            reason=data.get("reason"),
            priority=Severity(data.get("priority", "Medium")),
            kpi_summary=[KPISummary(**k) for k in data.get("kpi_summary", [])],
            flags=data.get("flags", []),
            signals=[Signal(**{**s, 'severity': Severity(s.get('severity', 'Medium'))})
                    for s in data.get("signals", [])],
            focus_areas=[FocusArea(**f) for f in data.get("focus_areas", [])],
            constraints=data.get("constraints", {}),
            evidence=[EvidenceRef(**e) for e in data.get("evidence", [])],
            session_id=data.get("session_id"),
        )

    def add_flag(self, flag: RiskFlag) -> None:
        """Add a risk flag."""
        if flag.value not in self.flags:
            self.flags.append(flag.value)

    def add_signal(self, metric: str, value: float, direction: str,
                   severity: Severity = Severity.MEDIUM, context: str = None) -> None:
        """Add a signal observation."""
        self.signals.append(Signal(
            metric=metric,
            value=value,
            direction=direction,
            severity=severity,
            context=context
        ))

    def add_focus_area(self, **kwargs) -> None:
        """Add a focus area."""
        self.focus_areas.append(FocusArea(**kwargs))

    def add_evidence(self, view: str, query_id: str = None,
                     filters: dict = None, row_count: int = None) -> None:
        """Add an evidence reference."""
        self.evidence.append(EvidenceRef(
            view=view,
            query_id=query_id,
            filters=filters,
            row_count=row_count
        ))

    def add_kpi(self, name: str, value: float, unit: str, trend: str,
                definition: str = None, source_view: str = None,
                window: str = None, confidence: str = "High") -> None:
        """Add a KPI to the summary."""
        self.kpi_summary.append(KPISummary(
            name=name,
            value=value,
            unit=unit,
            trend=trend,
            definition=definition,
            source_view=source_view,
            window=window,
            confidence=confidence
        ))


# Standard decision constraints (configurable)
DEFAULT_CONSTRAINTS = {
    "margin_floor": DecisionConstraint(
        name="Margin Floor",
        operator=">=",
        value=18.0,
        unit="%"
    ),
    "max_discount": DecisionConstraint(
        name="Max Discount Cap",
        operator="<=",
        value=12.0,
        unit="%"
    ),
    "inventory_days_min": DecisionConstraint(
        name="Inventory Days Min",
        operator=">=",
        value=45,
        unit="days"
    ),
    "inventory_days_max": DecisionConstraint(
        name="Inventory Days Max",
        operator="<=",
        value=60,
        unit="days"
    ),
    "data_freshness_sla": DecisionConstraint(
        name="Data Freshness SLA",
        operator="<=",
        value=30,
        unit="minutes"
    ),
}


def get_default_constraints() -> Dict[str, DecisionConstraint]:
    """Get copy of default constraints."""
    return {k: DecisionConstraint(**asdict(v)) for k, v in DEFAULT_CONSTRAINTS.items()}
