"""
Boardroom API - FastAPI Backend for Vercel Deployment
=====================================================
REST API for the Boardroom-in-a-Box system.

Endpoints:
- POST /api/flows/kpi-review - Run KPI review flow
- POST /api/flows/trade-off - Run trade-off (debate) flow
- POST /api/flows/scenario - Run scenario simulation
- GET /api/sessions/{session_id} - Get session details
- GET /api/sessions/{session_id}/memo - Get board memo
- GET /api/sessions/{session_id}/evidence - Get evidence pack
- GET /api/confidence - Get current data confidence
- GET /api/constraints - Get active constraints
"""

import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
import asyncio
import json

from agents.flow_orchestrator import (
    FlowOrchestrator, FlowType, BoardMode, SessionState, FlowEdge,
    run_kpi_review, run_trade_off, run_scenario, FLOW_SPECS
)
from agents.confidence_engine import ConfidenceEngine, assess_confidence
from agents.export_artifacts import (
    export_memo, export_evidence, export_decision_log, export_email
)
from agents.handoff import get_default_constraints
from agents.base_agent import DatabaseConnection


# Initialize FastAPI
app = FastAPI(
    title="Boardroom-in-a-Box API",
    description="AI-powered retail boardroom decision system",
    version="2.0.0",
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store (use Redis in production)
sessions: Dict[str, SessionState] = {}

# Active streaming sessions for realtime updates
streaming_sessions: Dict[str, asyncio.Queue] = {}


# Request/Response Models
class FlowRequest(BaseModel):
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    mode: Optional[str] = "summary"
    constraints: Optional[Dict[str, Any]] = None


class ScenarioRequest(FlowRequest):
    scenario_params: Optional[Dict[str, Any]] = None


class ConstraintUpdate(BaseModel):
    margin_floor: Optional[float] = None
    max_discount: Optional[float] = None
    inventory_days_min: Optional[int] = None
    inventory_days_max: Optional[int] = None


# Health Check
@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
    }


# Flow Endpoints
@app.post("/api/flows/kpi-review")
async def run_kpi_review_flow(request: FlowRequest):
    """
    Run a KPI Review flow.

    Sequential: CEO → CFO → CMO → CIO → Evaluator
    """
    try:
        mode = BoardMode(request.mode) if request.mode else BoardMode.SUMMARY

        orchestrator = FlowOrchestrator()
        session = orchestrator.start_session(
            FlowType.KPI_REVIEW,
            mode=mode,
            period_start=request.period_start,
            period_end=request.period_end,
            constraints=request.constraints,
        )
        session = orchestrator.run_flow(session)

        # Store session
        sessions[session.session_id] = session

        return {
            "success": True,
            "session_id": session.session_id,
            "flow": session.flow_spec.to_dict(),
            "evaluation": session.evaluation.to_dict() if session.evaluation else None,
            "confidence": session.confidence.to_dict() if session.confidence else None,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/flows/trade-off")
async def run_trade_off_flow(request: FlowRequest):
    """
    Run a Trade-off (Debate) flow.

    Parallel: [CFO || CMO] → Evaluator
    """
    try:
        orchestrator = FlowOrchestrator()
        session = orchestrator.start_session(
            FlowType.TRADE_OFF,
            mode=BoardMode.DEBATE,
            period_start=request.period_start,
            period_end=request.period_end,
            constraints=request.constraints,
        )
        session = orchestrator.run_flow(session)

        sessions[session.session_id] = session

        return {
            "success": True,
            "session_id": session.session_id,
            "flow": session.flow_spec.to_dict(),
            "evaluation": session.evaluation.to_dict() if session.evaluation else None,
            "agents": {
                name: output.to_dict()
                for name, output in session.agent_outputs.items()
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/flows/scenario")
async def run_scenario_flow(request: ScenarioRequest):
    """
    Run a Scenario Simulation flow.

    What-if: CFO → CMO → Evaluator with parameters
    """
    try:
        orchestrator = FlowOrchestrator()

        # Merge scenario params into constraints
        constraints = request.constraints or {}
        if request.scenario_params:
            constraints.update(request.scenario_params)

        session = orchestrator.start_session(
            FlowType.SCENARIO,
            mode=BoardMode.SUMMARY,
            period_start=request.period_start,
            period_end=request.period_end,
            constraints=constraints,
        )
        session = orchestrator.run_flow(session)

        sessions[session.session_id] = session

        return {
            "success": True,
            "session_id": session.session_id,
            "scenario_params": request.scenario_params,
            "evaluation": session.evaluation.to_dict() if session.evaluation else None,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/flows/root-cause")
async def run_root_cause_flow(request: FlowRequest):
    """
    Run a Root Cause Analysis flow.

    Diagnostic: CIO → CFO → CMO → Evaluator
    """
    try:
        orchestrator = FlowOrchestrator()
        session = orchestrator.start_session(
            FlowType.ROOT_CAUSE,
            mode=BoardMode(request.mode) if request.mode else BoardMode.OPERATOR,
            period_start=request.period_start,
            period_end=request.period_end,
        )
        session = orchestrator.run_flow(session)

        sessions[session.session_id] = session

        return {
            "success": True,
            "session_id": session.session_id,
            "flow": session.flow_spec.to_dict(),
            "evaluation": session.evaluation.to_dict() if session.evaluation else None,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Streaming Flow Endpoint (Server-Sent Events)
@app.get("/api/flows/stream/{flow_type}")
async def stream_flow(
    flow_type: str,
    mode: str = "summary",
    period_start: str = "2025-11-01",
    period_end: str = "2026-01-30",
):
    """
    Stream flow execution in realtime using Server-Sent Events.

    Events emitted:
    - session_start: Flow started with session_id
    - confidence: Data confidence check result
    - agent_start: Agent started processing
    - agent_complete: Agent finished with output
    - handoff: Handoff created between agents
    - evaluation: Evaluator results
    - session_complete: Flow finished
    """
    flow_map = {
        'kpi-review': FlowType.KPI_REVIEW,
        'trade-off': FlowType.TRADE_OFF,
        'scenario': FlowType.SCENARIO,
        'root-cause': FlowType.ROOT_CAUSE,
    }

    ft = flow_map.get(flow_type, FlowType.KPI_REVIEW)
    bm = BoardMode(mode) if mode else BoardMode.SUMMARY

    async def event_generator():
        orchestrator = FlowOrchestrator()

        # Start session
        session = orchestrator.start_session(
            ft,
            mode=bm,
            period_start=period_start,
            period_end=period_end,
        )

        # Emit session start
        yield f"event: session_start\ndata: {json.dumps({'session_id': session.session_id, 'flow': session.flow_spec.to_dict()})}\n\n"
        await asyncio.sleep(0.1)

        # Check confidence
        session.confidence = orchestrator.confidence_engine.assess()
        yield f"event: confidence\ndata: {json.dumps(session.confidence.to_dict())}\n\n"
        await asyncio.sleep(0.1)

        # Execute agents sequentially with events
        previous_handoff = None

        for agent_name in session.flow_spec.nodes:
            if agent_name == "Evaluator":
                continue

            session.current_node = agent_name
            node = session.nodes[agent_name]

            # Emit agent start
            node.status = "active"
            node.started_at = datetime.now().isoformat()
            yield f"event: agent_start\ndata: {json.dumps({'agent': agent_name, 'started_at': node.started_at})}\n\n"
            await asyncio.sleep(0.1)

            try:
                # Run agent (this is synchronous, consider ThreadPoolExecutor for production)
                agent = orchestrator.agents[agent_name]
                output = agent.analyze(session.period_start, session.period_end)

                session.agent_outputs[agent_name] = output
                node.output = output
                node.status = "completed"
                node.ended_at = datetime.now().isoformat()

                # Create handoff
                handoff = orchestrator._create_handoff(agent_name, output, session, previous_handoff)
                node.handoff_out = handoff
                session.handoffs.append(handoff)
                previous_handoff = handoff

                # Create edge
                next_idx = session.flow_spec.nodes.index(agent_name) + 1
                if next_idx < len(session.flow_spec.nodes):
                    next_agent = session.flow_spec.nodes[next_idx]
                    session.edges.append(FlowEdge(
                        from_agent=agent_name,
                        to_agent=next_agent,
                        handoff=handoff,
                    ))

                # Emit agent complete
                yield f"event: agent_complete\ndata: {json.dumps({'agent': agent_name, 'status': 'completed', 'ended_at': node.ended_at, 'kpis': [k.to_dict() for k in output.kpis], 'insights': output.insights[:2]})}\n\n"
                await asyncio.sleep(0.3)  # Slight delay for visual effect

                # Emit handoff
                yield f"event: handoff\ndata: {json.dumps({'from': handoff.handoff_from, 'to': handoff.handoff_to, 'flags': handoff.flags, 'reason': handoff.reason})}\n\n"
                await asyncio.sleep(0.1)

            except Exception as e:
                node.status = "failed"
                node.ended_at = datetime.now().isoformat()
                yield f"event: agent_error\ndata: {json.dumps({'agent': agent_name, 'error': str(e)})}\n\n"

        # Run evaluator
        session.current_node = "Evaluator"
        eval_node = session.nodes["Evaluator"]
        eval_node.status = "active"
        eval_node.started_at = datetime.now().isoformat()
        yield f"event: agent_start\ndata: {json.dumps({'agent': 'Evaluator', 'started_at': eval_node.started_at})}\n\n"
        await asyncio.sleep(0.1)

        try:
            # Evaluate (this also checks constraints internally)
            evaluation = orchestrator.evaluator.evaluate(
                session.agent_outputs,
                session.handoffs,
                session.confidence,
                session.constraints_status,
            )
            session.evaluation = evaluation
            eval_node.status = "completed"
            eval_node.ended_at = datetime.now().isoformat()

            # Emit evaluation
            yield f"event: agent_complete\ndata: {json.dumps({'agent': 'Evaluator', 'status': 'completed', 'ended_at': eval_node.ended_at})}\n\n"

            # Serialize evaluation (handle non-serializable objects)
            eval_dict = evaluation.to_dict()
            yield f"event: evaluation\ndata: {json.dumps(eval_dict, default=str)}\n\n"
            await asyncio.sleep(0.1)
        except Exception as e:
            eval_node.status = "failed"
            eval_node.ended_at = datetime.now().isoformat()
            yield f"event: agent_error\ndata: {json.dumps({'agent': 'Evaluator', 'error': str(e)})}\n\n"

        # Complete session
        session.ended_at = datetime.now().isoformat()
        session.current_node = None
        sessions[session.session_id] = session

        yield f"event: session_complete\ndata: {json.dumps({'session_id': session.session_id, 'ended_at': session.ended_at, 'constraints_status': session.constraints_status})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# Session Endpoints
@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Get full session details."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return session.to_dict()


@app.get("/api/sessions/{session_id}/state")
async def get_session_state(session_id: str):
    """Get current session state (for polling)."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session.session_id,
        "current_node": session.current_node,
        "nodes": {k: {"status": v.status} for k, v in session.nodes.items()},
        "completed": session.ended_at is not None,
    }


@app.get("/api/sessions/{session_id}/handoffs")
async def get_session_handoffs(session_id: str):
    """Get all handoffs for a session."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session_id,
        "handoffs": [h.to_dict() for h in session.handoffs],
        "edges": [e.to_dict() for e in session.edges],
    }


@app.get("/api/sessions/{session_id}/memo", response_class=PlainTextResponse)
async def get_session_memo(session_id: str):
    """Get board memo for a session."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    memo = export_memo(session)
    return memo


@app.get("/api/sessions/{session_id}/evidence")
async def get_session_evidence(session_id: str):
    """Get evidence pack for a session."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return export_evidence(session)


@app.get("/api/sessions/{session_id}/decision-log")
async def get_session_decision_log(session_id: str):
    """Get decision audit log for a session."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return export_decision_log(session)


@app.get("/api/sessions/{session_id}/email-summary", response_class=PlainTextResponse)
async def get_session_email_summary(session_id: str):
    """Get email/Slack summary for a session."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return export_email(session)


# Confidence Endpoint
@app.get("/api/confidence")
async def get_data_confidence():
    """Get current data confidence assessment."""
    try:
        report = assess_confidence()
        return report.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Constraints Endpoints
@app.get("/api/constraints")
async def get_constraints():
    """Get current decision constraints."""
    constraints = get_default_constraints()
    return {
        k: {
            "name": v.name,
            "operator": v.operator,
            "value": v.value,
            "unit": v.unit,
        }
        for k, v in constraints.items()
    }


# Flow Specs Endpoint
@app.get("/api/flows")
async def get_available_flows():
    """Get all available flow specifications."""
    return {
        flow_type.value: spec.to_dict()
        for flow_type, spec in FLOW_SPECS.items()
    }


# Sessions List
@app.get("/api/sessions")
async def list_sessions(limit: int = Query(default=10, le=50)):
    """List recent sessions."""
    sorted_sessions = sorted(
        sessions.values(),
        key=lambda s: s.started_at,
        reverse=True
    )[:limit]

    return {
        "sessions": [
            {
                "session_id": s.session_id,
                "flow": s.flow_spec.name,
                "mode": s.mode.value,
                "started_at": s.started_at,
                "ended_at": s.ended_at,
                "score": s.evaluation.overall_score if s.evaluation else None,
                "risk_level": s.evaluation.risk_level if s.evaluation else None,
            }
            for s in sorted_sessions
        ]
    }


# ============================================================
# LLM-Powered Endpoints
# ============================================================

# Try to import LLM components (optional - only if OPENROUTER_API_KEY is set)
try:
    from agents.intent_router import IntentRouter, ParsedIntent, IntentType
    from agents.sql_analyst import SQLAnalyst, generate_sql
    from agents.conflict_detector import ConflictDetector, detect_conflicts
    LLM_AVAILABLE = True
except Exception as e:
    LLM_AVAILABLE = False
    LLM_ERROR = str(e)


class AskRequest(BaseModel):
    """Request for /ask endpoint."""
    question: str
    run_flow: bool = True  # Whether to actually run the flow or just parse intent


class QueryRequest(BaseModel):
    """Request for /query endpoint."""
    question: str
    agent: str = "CEO"
    date_from: Optional[str] = None
    date_to: Optional[str] = None


@app.post("/api/ask")
async def ask_question(request: AskRequest):
    """
    Free-form question endpoint using LLM intent routing.

    Takes a natural language question, routes it to the appropriate flow,
    and optionally executes the flow.

    Examples:
    - "How are we doing?" → KPI Review flow
    - "Should we run a promotion?" → Trade-off flow
    - "What if we increase discount to 20%?" → Scenario flow
    - "Why did margin drop?" → Root Cause flow
    """
    if not LLM_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=f"LLM not available. Set OPENROUTER_API_KEY environment variable. Error: {LLM_ERROR}"
        )

    try:
        # Parse intent
        router = IntentRouter()
        intent = router.parse_intent(request.question)

        response = {
            "question": request.question,
            "parsed_intent": {
                "intent_type": intent.intent_type.value,
                "confidence": intent.confidence,
                "agents": intent.agents,
                "time_window": intent.time_window,
                "focus_areas": intent.focus_areas,
                "reasoning": intent.reasoning,
            }
        }

        # Optionally run the flow
        if request.run_flow and intent.intent_type != IntentType.CLARIFICATION:
            flow_config = router.to_flow_config(intent)

            orchestrator = FlowOrchestrator()
            session = orchestrator.start_session(
                flow_config["flow_type"],
                mode=BoardMode.SUMMARY,
                period_start=flow_config["period_start"],
                period_end=flow_config["period_end"],
            )
            session = orchestrator.run_flow(session)
            sessions[session.session_id] = session

            response["session_id"] = session.session_id
            response["flow_executed"] = True
            response["evaluation"] = session.evaluation.to_dict() if session.evaluation else None

            # Run LLM conflict detection on the outputs
            if session.agent_outputs:
                try:
                    detector = ConflictDetector()
                    conflict_report = detector.detect_conflicts(
                        session.agent_outputs,
                        session.constraints,
                    )
                    response["llm_conflicts"] = {
                        "conflicts": [
                            {
                                "agents": c.agents_involved,
                                "type": c.conflict_type,
                                "description": c.description,
                                "severity": c.severity.value,
                                "resolution": c.suggested_resolution,
                            }
                            for c in conflict_report.conflicts
                        ],
                        "tensions": conflict_report.tensions,
                        "alignment_score": conflict_report.alignment_score,
                        "summary": conflict_report.summary,
                    }
                except Exception as e:
                    response["llm_conflicts"] = {"error": str(e)}

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/query")
async def run_query(request: QueryRequest):
    """
    Generate and execute a SQL query from natural language.

    Uses LLM to convert the question to SQL, validates against guardrails,
    and executes if valid.

    Examples:
    - "What was total revenue last month?" → SELECT SUM(net_revenue)...
    - "Show margin by category" → SELECT category_name, margin_pct...
    """
    if not LLM_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="LLM not available. Set OPENROUTER_API_KEY environment variable."
        )

    try:
        from datetime import datetime, timedelta

        # Default dates
        today = datetime.now()
        date_from = request.date_from or (today - timedelta(days=90)).strftime("%Y-%m-%d")
        date_to = request.date_to or today.strftime("%Y-%m-%d")

        # Generate SQL
        result = generate_sql(
            question=request.question,
            agent=request.agent,
            date_from=date_from,
            date_to=date_to,
        )

        response = {
            "question": request.question,
            "agent": request.agent,
            "date_range": {"from": date_from, "to": date_to},
            "success": result.success,
            "sql": result.sql,
            "view_used": result.view_used,
            "guardrail_validated": result.guardrail_validated,
        }

        if not result.success:
            response["error"] = result.error
            return response

        # Execute the query
        try:
            db = DatabaseConnection()

            # Add LIMIT if not present
            sql = result.sql
            if "limit" not in sql.lower():
                sql = sql.rstrip(";") + " LIMIT 100"

            rows = db.execute_query(sql)
            response["data"] = rows
            response["row_count"] = len(rows)

        except Exception as e:
            response["execution_error"] = str(e)

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/llm/status")
async def llm_status():
    """Check if LLM is available and configured."""
    import os

    return {
        "available": LLM_AVAILABLE,
        "api_key_set": bool(os.environ.get("OPENROUTER_API_KEY")),
        "error": LLM_ERROR if not LLM_AVAILABLE else None,
    }


# ============================================================
# LangChain Chat Endpoint
# ============================================================

# Try to import LangChain orchestrator
try:
    from agents.langchain_orchestrator import LangChainOrchestrator, StreamingBoardroomChat
    LANGCHAIN_AVAILABLE = True
except Exception as e:
    LANGCHAIN_AVAILABLE = False
    LANGCHAIN_ERROR = str(e)


class ChatRequest(BaseModel):
    """Request for /chat endpoint."""
    message: str
    session_id: Optional[str] = None  # For conversation continuity
    quick_mode: bool = False  # Use full agent flow (with real data) by default


class ChatResponse(BaseModel):
    """Response from /chat endpoint."""
    message: str
    flow_used: str
    flow_reasoning: str
    confidence: float
    session_id: str
    key_findings: List[str]
    recommendations: List[str]
    risks: List[str]
    overall_score: Optional[float] = None


@app.post("/api/chat")
async def chat_with_boardroom(request: ChatRequest):
    """
    Natural language chat interface to the boardroom.

    Send a question in plain English, and the system will:
    1. Analyze your question to determine the best analysis approach
    2. Route to the appropriate agent flow (KPI Review, Trade-off, etc.)
    3. Execute the flow with all relevant agents
    4. Synthesize a decision with recommendations

    Examples:
    - "How is the business performing this quarter?"
    - "Should we run more promotions or focus on margins?"
    - "Why did sales drop in the East region?"
    - "What would happen if we increased prices by 10%?"
    - "Prepare a summary for the board meeting"

    Returns a structured decision with findings, recommendations, and risks.
    """
    if not LANGCHAIN_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=f"LangChain not available. Error: {LANGCHAIN_ERROR}"
        )

    try:
        orchestrator = LangChainOrchestrator()
        result = orchestrator.chat_sync(request.message, quick_mode=request.quick_mode)

        # Build response with full session data
        response = {
            "message": result["decision"]["summary"],
            "flow_used": result["flow_selection"]["flow_type"],
            "flow_reasoning": result["flow_selection"]["reasoning"],
            "confidence": result["flow_selection"]["confidence"],
            "session_id": result["session"]["session_id"],
            "agents_involved": result["session"]["agents_involved"],
            "key_findings": result["decision"]["key_findings"],
            "recommendations": result["decision"]["recommendations"],
            "risks": result["decision"]["risks"],
            "confidence_level": result["decision"]["confidence_level"],
            "next_steps": result["decision"]["next_steps"],
            "overall_score": result["session"]["overall_score"],
        }

        # Add full session data if available (from full agent flow)
        if "full_session" in result:
            session = result["full_session"]
            # Agent outputs with KPIs and insights
            response["agent_outputs"] = {}
            for agent_name, output in session.agent_outputs.items():
                if output:
                    response["agent_outputs"][agent_name] = {
                        "kpis": [kpi.to_dict() if hasattr(kpi, 'to_dict') else kpi for kpi in (output.kpis or [])],
                        "insights": output.insights or [],
                        "recommendations": [rec.to_dict() if hasattr(rec, 'to_dict') else {"action": str(rec)} for rec in (output.recommendations or [])],
                        "risks": output.risks or [],
                    }

            # Handoffs (agent-to-agent communication)
            response["handoffs"] = [h.to_dict() if hasattr(h, 'to_dict') else h for h in session.handoffs]

            # Evaluation with conflicts
            if session.evaluation:
                eval_data = session.evaluation
                response["evaluation"] = {
                    "overall_score": eval_data.overall_score,
                    "risk_level": eval_data.risk_level,
                    "confidence": eval_data.confidence,
                    "dimension_scores": [d.to_dict() for d in eval_data.dimension_scores],
                    "conflicts": [c.to_dict() for c in eval_data.conflicts],
                    "has_blocking_conflicts": eval_data.has_blocking_conflicts,
                    "decisions": [d.to_dict() for d in eval_data.decisions],
                }

        return response

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/chat/stream/{question}")
async def stream_chat(question: str):
    """
    Streaming chat interface with real-time progress updates.

    Returns Server-Sent Events (SSE) with progress as the analysis runs:
    - routing: Analyzing your question
    - flow_selected: Flow has been chosen
    - agent_start: An agent is starting analysis
    - agent_complete: An agent has finished
    - synthesizing: Generating final decision
    - decision: Final decision with recommendations

    Use this for a real-time chat experience.
    """
    if not LANGCHAIN_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=f"LangChain not available. Error: {LANGCHAIN_ERROR}"
        )

    async def event_generator():
        try:
            chat = StreamingBoardroomChat()
            async for event in chat.stream_chat(question):
                yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.get("/api/chat/status")
async def chat_status():
    """Check if LangChain chat is available."""
    return {
        "available": LANGCHAIN_AVAILABLE,
        "error": LANGCHAIN_ERROR if not LANGCHAIN_AVAILABLE else None,
    }


# Vercel serverless handler
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
