"""
Flow Orchestrator - Visible Agent Handoffs
==========================================
Orchestrates agent execution with visible handoff tracking.
Creates audit trail and UI-bindable artifacts.

Flows:
- KPI Review: CEO → CFO → CMO → CIO → Evaluator
- Trade-off: [CFO || CMO] → Evaluator (parallel debate)
- Scenario: CFO → CMO → Evaluator (with parameters)
- Root Cause: CIO → CFO → CMO → Evaluator
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from enum import Enum
from datetime import datetime
import uuid
import json

from .base_agent import DatabaseConnection
from .contract import AgentOutput, AgentRole
from .handoff import HandoffPayload, RiskFlag, Severity, FocusArea, get_default_constraints
from .evaluator_v2 import EvaluatorV2, EvaluatorOutput
from .confidence_engine import ConfidenceEngine, ConfidenceReport

# Import v2 agents
from .ceo_agent_v2 import CEOAgentV2
from .cfo_agent_v2 import CFOAgentV2
from .cmo_agent_v2 import CMOAgentV2
from .cio_agent_v2 import CIOAgentV2


class FlowType(Enum):
    """Available flow types."""
    KPI_REVIEW = "kpi_review"
    TRADE_OFF = "trade_off"
    SCENARIO = "scenario"
    ROOT_CAUSE = "root_cause"
    BOARD_MEMO = "board_memo"
    ASK = "ask"


class BoardMode(Enum):
    """UI display modes."""
    SUMMARY = "summary"      # Short, calm, no debate
    DEBATE = "debate"        # Side-by-side CFO vs CMO
    OPERATOR = "operator"    # Drill down to store/SKU
    AUDIT = "audit"          # Show SQL/evidence/logs


@dataclass
class FlowNode:
    """A node in the flow graph."""
    agent: str
    status: str = "pending"  # pending/active/completed/failed
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    output: Optional[AgentOutput] = None
    handoff_out: Optional[HandoffPayload] = None

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "status": self.status,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "output": self.output.to_dict() if self.output else None,
            "handoff_out": self.handoff_out.to_dict() if self.handoff_out else None,
        }


@dataclass
class FlowEdge:
    """An edge connecting flow nodes."""
    from_agent: str
    to_agent: str
    handoff: Optional[HandoffPayload] = None

    def to_dict(self) -> dict:
        return {
            "from": self.from_agent,
            "to": self.to_agent,
            "handoff": self.handoff.to_dict() if self.handoff else None,
        }


@dataclass
class FlowSpec:
    """Specification for a flow."""
    flow_id: str
    flow_type: FlowType
    name: str
    description: str
    nodes: List[str]  # Agent names in order
    parallel_nodes: List[List[str]] = field(default_factory=list)  # Groups of parallel agents

    def to_dict(self) -> dict:
        return {
            "flow_id": self.flow_id,
            "flow_type": self.flow_type.value,
            "name": self.name,
            "description": self.description,
            "nodes": self.nodes,
            "parallel_nodes": self.parallel_nodes,
        }


@dataclass
class SessionState:
    """Current state of a decision session."""
    session_id: str
    flow_spec: FlowSpec
    mode: BoardMode
    started_at: str
    ended_at: Optional[str] = None

    # Date range
    period_start: Optional[str] = None
    period_end: Optional[str] = None

    # Flow state
    nodes: Dict[str, FlowNode] = field(default_factory=dict)
    edges: List[FlowEdge] = field(default_factory=list)
    current_node: Optional[str] = None
    handoffs: List[HandoffPayload] = field(default_factory=list)

    # Outputs
    agent_outputs: Dict[str, AgentOutput] = field(default_factory=dict)
    evaluation: Optional[EvaluatorOutput] = None
    confidence: Optional[ConfidenceReport] = None

    # Constraints
    constraints: Dict[str, Any] = field(default_factory=dict)
    constraints_status: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "flow_spec": self.flow_spec.to_dict(),
            "mode": self.mode.value,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "current_node": self.current_node,
            "handoffs": [h.to_dict() for h in self.handoffs],
            "agent_outputs": {k: v.to_dict() for k, v in self.agent_outputs.items()},
            "evaluation": self.evaluation.to_dict() if self.evaluation else None,
            "confidence": self.confidence.to_dict() if self.confidence else None,
            "constraints": self.constraints,
            "constraints_status": self.constraints_status,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# Predefined flow specifications
FLOW_SPECS = {
    FlowType.KPI_REVIEW: FlowSpec(
        flow_id="kpi_review",
        flow_type=FlowType.KPI_REVIEW,
        name="KPI Review",
        description="Sequential review: CEO → CFO → CMO → CIO → Evaluator",
        nodes=["CEO", "CFO", "CMO", "CIO", "Evaluator"],
    ),
    FlowType.TRADE_OFF: FlowSpec(
        flow_id="trade_off",
        flow_type=FlowType.TRADE_OFF,
        name="Trade-off Analysis",
        description="Parallel debate: [CFO || CMO] → Evaluator",
        nodes=["CFO", "CMO", "Evaluator"],
        parallel_nodes=[["CFO", "CMO"]],
    ),
    FlowType.SCENARIO: FlowSpec(
        flow_id="scenario",
        flow_type=FlowType.SCENARIO,
        name="Scenario Simulation",
        description="What-if analysis: CFO → CMO → Evaluator",
        nodes=["CFO", "CMO", "Evaluator"],
    ),
    FlowType.ROOT_CAUSE: FlowSpec(
        flow_id="root_cause",
        flow_type=FlowType.ROOT_CAUSE,
        name="Root Cause Analysis",
        description="Diagnostic flow: CIO → CFO → CMO → Evaluator",
        nodes=["CIO", "CFO", "CMO", "Evaluator"],
    ),
    FlowType.BOARD_MEMO: FlowSpec(
        flow_id="board_memo",
        flow_type=FlowType.BOARD_MEMO,
        name="Board Memo",
        description="Executive summary: CEO → Evaluator",
        nodes=["CEO", "Evaluator"],
    ),
}


class FlowOrchestrator:
    """
    Orchestrates agent flows with visible handoffs.
    """

    def __init__(self, db: DatabaseConnection = None):
        self.db = db or DatabaseConnection()

        # Initialize agents
        self.agents = {
            "CEO": CEOAgentV2(),
            "CFO": CFOAgentV2(),
            "CMO": CMOAgentV2(),
            "CIO": CIOAgentV2(),
        }

        self.evaluator = EvaluatorV2(self.db)
        self.confidence_engine = ConfidenceEngine(self.db)

    def start_session(
        self,
        flow_type: FlowType,
        mode: BoardMode = BoardMode.SUMMARY,
        period_start: str = None,
        period_end: str = None,
        constraints: Dict[str, Any] = None,
    ) -> SessionState:
        """
        Start a new decision session.

        Args:
            flow_type: Type of flow to execute
            mode: UI display mode
            period_start: Start date (YYYY-MM-DD)
            period_end: End date (YYYY-MM-DD)
            constraints: Custom constraints to apply

        Returns:
            SessionState with initialized flow
        """
        session_id = str(uuid.uuid4())[:8]
        flow_spec = FLOW_SPECS[flow_type]

        # Initialize nodes
        nodes = {}
        for agent_name in flow_spec.nodes:
            nodes[agent_name] = FlowNode(agent=agent_name)

        # Get default constraints
        default_constraints = get_default_constraints()
        applied_constraints = {
            k: {"name": v.name, "operator": v.operator, "value": v.value, "unit": v.unit}
            for k, v in default_constraints.items()
        }
        if constraints:
            applied_constraints.update(constraints)

        return SessionState(
            session_id=session_id,
            flow_spec=flow_spec,
            mode=mode,
            started_at=datetime.now().isoformat(),
            period_start=period_start,
            period_end=period_end,
            nodes=nodes,
            constraints=applied_constraints,
        )

    def run_flow(self, session: SessionState) -> SessionState:
        """
        Execute the complete flow.

        Args:
            session: Session state to execute

        Returns:
            Updated session state with all outputs
        """
        # 1. Check confidence first
        session.confidence = self.confidence_engine.assess()

        if not session.confidence.can_proceed:
            # Log but continue with warning
            pass

        # 2. Execute agents based on flow spec
        flow_spec = session.flow_spec

        if flow_spec.parallel_nodes:
            # Handle parallel execution (e.g., Trade-off)
            session = self._run_parallel_flow(session)
        else:
            # Sequential execution
            session = self._run_sequential_flow(session)

        # 3. Run evaluator
        session = self._run_evaluator(session)

        # 4. Record to database
        self._persist_session(session)

        session.ended_at = datetime.now().isoformat()
        return session

    def _run_sequential_flow(self, session: SessionState) -> SessionState:
        """Execute agents sequentially."""
        previous_handoff = None

        for agent_name in session.flow_spec.nodes:
            if agent_name == "Evaluator":
                continue  # Evaluator runs separately

            session.current_node = agent_name
            node = session.nodes[agent_name]

            # Update status
            node.status = "active"
            node.started_at = datetime.now().isoformat()

            try:
                # Run agent
                agent = self.agents[agent_name]
                output = agent.analyze(session.period_start, session.period_end)

                # Store output
                session.agent_outputs[agent_name] = output
                node.output = output
                node.status = "completed"

                # Create handoff for next agent
                handoff = self._create_handoff(
                    agent_name,
                    output,
                    session,
                    previous_handoff
                )
                node.handoff_out = handoff
                session.handoffs.append(handoff)

                # Create edge
                next_idx = session.flow_spec.nodes.index(agent_name) + 1
                if next_idx < len(session.flow_spec.nodes):
                    next_agent = session.flow_spec.nodes[next_idx]
                    session.edges.append(FlowEdge(
                        from_agent=agent_name,
                        to_agent=next_agent,
                        handoff=handoff,
                    ))

                previous_handoff = handoff

            except Exception as e:
                node.status = "failed"
                # Continue with other agents

            node.ended_at = datetime.now().isoformat()

        return session

    def _run_parallel_flow(self, session: SessionState) -> SessionState:
        """Execute agents with parallel groups."""
        previous_handoff = None

        for item in session.flow_spec.nodes:
            if item == "Evaluator":
                continue

            # Check if this is part of a parallel group
            parallel_group = None
            for group in session.flow_spec.parallel_nodes:
                if item in group:
                    parallel_group = group
                    break

            if parallel_group and item == parallel_group[0]:
                # Execute parallel group
                for agent_name in parallel_group:
                    session.current_node = agent_name
                    node = session.nodes[agent_name]
                    node.status = "active"
                    node.started_at = datetime.now().isoformat()

                    try:
                        agent = self.agents[agent_name]
                        output = agent.analyze(session.period_start, session.period_end)
                        session.agent_outputs[agent_name] = output
                        node.output = output
                        node.status = "completed"

                        handoff = self._create_handoff(agent_name, output, session, previous_handoff)
                        node.handoff_out = handoff
                        session.handoffs.append(handoff)

                        # Edge to evaluator
                        session.edges.append(FlowEdge(
                            from_agent=agent_name,
                            to_agent="Evaluator",
                            handoff=handoff,
                        ))

                    except Exception as e:
                        node.status = "failed"

                    node.ended_at = datetime.now().isoformat()

            elif parallel_group is None:
                # Regular sequential node
                session.current_node = item
                node = session.nodes[item]
                node.status = "active"
                node.started_at = datetime.now().isoformat()

                try:
                    agent = self.agents[item]
                    output = agent.analyze(session.period_start, session.period_end)
                    session.agent_outputs[item] = output
                    node.output = output
                    node.status = "completed"

                    handoff = self._create_handoff(item, output, session, previous_handoff)
                    node.handoff_out = handoff
                    session.handoffs.append(handoff)
                    previous_handoff = handoff

                except Exception as e:
                    node.status = "failed"

                node.ended_at = datetime.now().isoformat()

        return session

    def _create_handoff(
        self,
        agent_name: str,
        output: AgentOutput,
        session: SessionState,
        previous: Optional[HandoffPayload]
    ) -> HandoffPayload:
        """Create a handoff payload from agent output."""
        # Determine next agent
        nodes = session.flow_spec.nodes
        idx = nodes.index(agent_name)
        next_agent = nodes[idx + 1] if idx + 1 < len(nodes) else "Evaluator"

        handoff = HandoffPayload(
            handoff_from=agent_name,
            handoff_to=next_agent,
            session_id=session.session_id,
        )

        # Add KPIs
        for kpi in output.kpis:
            handoff.add_kpi(
                name=kpi.name,
                value=kpi.value,
                unit=kpi.unit,
                trend=kpi.trend.value,
                window=kpi.window,
            )

        # Add flags based on output
        for risk in output.risks:
            risk_lower = risk.lower()
            if "margin" in risk_lower and ("below" in risk_lower or "low" in risk_lower):
                handoff.add_flag(RiskFlag.MARGIN_BELOW_FLOOR)
            if "inventory" in risk_lower and "high" in risk_lower:
                handoff.add_flag(RiskFlag.INVENTORY_HIGH)
            if "inventory" in risk_lower and "low" in risk_lower:
                handoff.add_flag(RiskFlag.INVENTORY_LOW)
            if "stale" in risk_lower or "freshness" in risk_lower:
                handoff.add_flag(RiskFlag.DATA_STALE)

        # Add evidence
        for ev in output.evidence:
            handoff.add_evidence(
                view=ev.view,
                query_id=ev.query_id,
                filters={"filter": ev.filters} if ev.filters else None,
            )

        # Determine reason for handoff
        if handoff.flags:
            handoff.reason = f"Flagged issues: {', '.join(handoff.flags)}"
            handoff.priority = Severity.HIGH
        else:
            handoff.reason = f"Analysis complete, passing to {next_agent}"
            handoff.priority = Severity.MEDIUM

        return handoff

    def _run_evaluator(self, session: SessionState) -> SessionState:
        """Run the evaluator on collected outputs."""
        node = session.nodes.get("Evaluator")
        if node:
            node.status = "active"
            node.started_at = datetime.now().isoformat()

        try:
            evaluation = self.evaluator.evaluate(
                agent_outputs=session.agent_outputs,
                handoffs=session.handoffs,
                session_id=session.session_id,
            )
            session.evaluation = evaluation

            # Update constraints status
            session.constraints_status = {
                k: v.get("status", "UNKNOWN")
                for k, v in evaluation.constraints_checked.items()
            }

            if node:
                node.status = "completed"

        except Exception as e:
            if node:
                node.status = "failed"

        if node:
            node.ended_at = datetime.now().isoformat()

        return session

    def _persist_session(self, session: SessionState) -> None:
        """Persist session to database."""
        try:
            # Insert decision_session
            query = """
            INSERT INTO retail.decision_session
            (session_id, flow_id, flow_name, started_at, ended_at,
             period_start, period_end, data_confidence, overall_score,
             risk_level, final_decision, constraints_used, mode)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (session_id) DO UPDATE SET
                ended_at = EXCLUDED.ended_at,
                overall_score = EXCLUDED.overall_score,
                risk_level = EXCLUDED.risk_level,
                final_decision = EXCLUDED.final_decision
            """
            conn = self.db.connect()
            with conn.cursor() as cur:
                cur.execute(query, (
                    session.session_id,
                    session.flow_spec.flow_id,
                    session.flow_spec.name,
                    session.started_at,
                    session.ended_at,
                    session.period_start,
                    session.period_end,
                    session.confidence.level.value if session.confidence else None,
                    session.evaluation.overall_score if session.evaluation else None,
                    session.evaluation.risk_level if session.evaluation else None,
                    json.dumps(session.evaluation.to_dict()) if session.evaluation else None,
                    json.dumps(session.constraints),
                    session.mode.value,
                ))
                conn.commit()

            # Insert agent runs
            for agent_name, node in session.nodes.items():
                if agent_name == "Evaluator":
                    continue

                query = """
                INSERT INTO retail.agent_run
                (session_id, agent_name, run_order, started_at, ended_at,
                 status, output_payload, handoff_payload, confidence)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (session_id, agent_name, run_order) DO NOTHING
                """
                output = session.agent_outputs.get(agent_name)
                with conn.cursor() as cur:
                    cur.execute(query, (
                        session.session_id,
                        agent_name,
                        1,
                        node.started_at,
                        node.ended_at,
                        node.status.upper(),
                        json.dumps(output.to_dict()) if output else None,
                        json.dumps(node.handoff_out.to_dict()) if node.handoff_out else None,
                        output.confidence.value if output else None,
                    ))
                    conn.commit()

        except Exception as e:
            # Log but don't fail
            print(f"Warning: Could not persist session: {e}")


# Convenience functions
def run_kpi_review(
    period_start: str = None,
    period_end: str = None,
    mode: BoardMode = BoardMode.SUMMARY
) -> SessionState:
    """Run a KPI review flow."""
    orchestrator = FlowOrchestrator()
    session = orchestrator.start_session(
        FlowType.KPI_REVIEW,
        mode=mode,
        period_start=period_start,
        period_end=period_end,
    )
    return orchestrator.run_flow(session)


def run_trade_off(
    period_start: str = None,
    period_end: str = None,
) -> SessionState:
    """Run a trade-off (debate) flow."""
    orchestrator = FlowOrchestrator()
    session = orchestrator.start_session(
        FlowType.TRADE_OFF,
        mode=BoardMode.DEBATE,
        period_start=period_start,
        period_end=period_end,
    )
    return orchestrator.run_flow(session)


def run_scenario(
    period_start: str = None,
    period_end: str = None,
    scenario_params: Dict[str, Any] = None,
) -> SessionState:
    """Run a scenario simulation flow."""
    orchestrator = FlowOrchestrator()
    session = orchestrator.start_session(
        FlowType.SCENARIO,
        mode=BoardMode.SUMMARY,
        period_start=period_start,
        period_end=period_end,
        constraints=scenario_params,
    )
    return orchestrator.run_flow(session)
