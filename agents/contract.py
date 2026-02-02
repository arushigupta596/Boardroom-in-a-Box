"""
Agent Interface Contract
========================
Standard I/O schema for all boardroom agents.
Every agent must produce output conforming to this structure.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Literal
from enum import Enum
import json
from datetime import date, datetime


class Trend(str, Enum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"


class Confidence(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class AgentRole(str, Enum):
    CEO = "CEO"
    CFO = "CFO"
    CMO = "CMO"
    CIO = "CIO"


@dataclass
class KPI:
    """A single KPI metric card."""
    name: str
    value: float
    unit: str  # e.g., "%", "$", "units", "days"
    trend: Trend
    window: str  # e.g., "Q1 2025", "Last 30 days"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "trend": self.trend.value,
            "window": self.window
        }


@dataclass
class Recommendation:
    """A recommended action with expected impact."""
    action: str
    impact: str
    priority: Optional[Literal["High", "Medium", "Low"]] = "Medium"

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "impact": self.impact,
            "priority": self.priority
        }


@dataclass
class Evidence:
    """Evidence source for agent findings."""
    view: str  # The view/table queried
    filters: str  # Filters applied
    query_id: Optional[str] = None  # Optional query identifier

    def to_dict(self) -> dict:
        d = {"view": self.view, "filters": self.filters}
        if self.query_id:
            d["query_id"] = self.query_id
        return d


@dataclass
class AgentOutput:
    """
    Standard output structure for all boardroom agents.
    UI can render this without parsing prose.
    Evaluator can score consistently.
    """
    agent: AgentRole
    kpis: List[KPI]
    insights: List[str]  # Max 3 short bullets
    risks: List[str]  # Max 3 bullets
    recommendations: List[Recommendation]  # Max 3 actions
    evidence: List[Evidence]
    confidence: Confidence
    open_questions: Optional[List[str]] = None  # What data is missing
    timestamp: Optional[str] = None

    def __post_init__(self):
        # Enforce limits
        if len(self.insights) > 3:
            self.insights = self.insights[:3]
        if len(self.risks) > 3:
            self.risks = self.risks[:3]
        if len(self.recommendations) > 3:
            self.recommendations = self.recommendations[:3]

        # Set timestamp if not provided
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "agent": self.agent.value,
            "kpis": [kpi.to_dict() for kpi in self.kpis],
            "insights": self.insights,
            "risks": self.risks,
            "recommendations": [rec.to_dict() for rec in self.recommendations],
            "evidence": [ev.to_dict() for ev in self.evidence],
            "confidence": self.confidence.value,
            "open_questions": self.open_questions,
            "timestamp": self.timestamp
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentOutput":
        """Deserialize from dictionary."""
        return cls(
            agent=AgentRole(data["agent"]),
            kpis=[KPI(
                name=k["name"],
                value=k["value"],
                unit=k["unit"],
                trend=Trend(k["trend"]),
                window=k["window"]
            ) for k in data["kpis"]],
            insights=data["insights"],
            risks=data["risks"],
            recommendations=[Recommendation(
                action=r["action"],
                impact=r["impact"],
                priority=r.get("priority", "Medium")
            ) for r in data["recommendations"]],
            evidence=[Evidence(
                view=e["view"],
                filters=e["filters"],
                query_id=e.get("query_id")
            ) for e in data["evidence"]],
            confidence=Confidence(data["confidence"]),
            open_questions=data.get("open_questions"),
            timestamp=data.get("timestamp")
        )

    @classmethod
    def from_json(cls, json_str: str) -> "AgentOutput":
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))


def validate_agent_output(output: AgentOutput) -> List[str]:
    """
    Validate agent output meets contract requirements.
    Returns list of validation errors (empty if valid).
    """
    errors = []

    # Check required fields
    if not output.agent:
        errors.append("Missing agent role")

    if not output.kpis:
        errors.append("At least one KPI required")

    if not output.insights:
        errors.append("At least one insight required")

    if not output.evidence:
        errors.append("At least one evidence source required")

    if not output.confidence:
        errors.append("Confidence level required")

    # Check limits
    if len(output.insights) > 3:
        errors.append("Maximum 3 insights allowed")

    if len(output.risks) > 3:
        errors.append("Maximum 3 risks allowed")

    if len(output.recommendations) > 3:
        errors.append("Maximum 3 recommendations allowed")

    # Validate KPI values
    for kpi in output.kpis:
        if kpi.value is None:
            errors.append(f"KPI '{kpi.name}' has no value")

    return errors


# Example usage and testing
if __name__ == "__main__":
    # Create example CFO output
    cfo_output = AgentOutput(
        agent=AgentRole.CFO,
        kpis=[
            KPI(name="Gross Margin %", value=17.6, unit="%", trend=Trend.DOWN, window="Q1 2025"),
            KPI(name="Net Revenue", value=32448691.78, unit="$", trend=Trend.UP, window="Q1 2025"),
        ],
        insights=[
            "Margin fell due to higher promo discount depth in 3 categories.",
            "Revenue grew 8% YoY despite margin pressure.",
            "Top 5 stores contribute 28% of total revenue."
        ],
        risks=[
            "Margin is below 18% floor for 2 consecutive weeks.",
            "Discount depth exceeding 15% in Electronics category."
        ],
        recommendations=[
            Recommendation(
                action="Cap discounts at 12% for low-margin SKUs",
                impact="Protect margin floor",
                priority="High"
            ),
            Recommendation(
                action="Review pricing strategy for Category 4",
                impact="Recover 2% margin",
                priority="Medium"
            )
        ],
        evidence=[
            Evidence(
                view="retail.v_margin_daily_store_sku",
                filters="sale_date between 2025-01-01 and 2025-03-31"
            ),
            Evidence(
                view="retail.v_sales_daily_store_category",
                filters="sale_date between 2025-01-01 and 2025-03-31"
            )
        ],
        confidence=Confidence.HIGH
    )

    # Validate
    errors = validate_agent_output(cfo_output)
    if errors:
        print("Validation errors:", errors)
    else:
        print("Output valid!")

    # Print JSON
    print("\nAgent Output JSON:")
    print(cfo_output.to_json())
