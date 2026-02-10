"""
LangChain Orchestrator - Natural Language to Agent Flow
========================================================
Uses LangChain to:
1. Route natural language questions to appropriate flows
2. Execute agent flows and synthesize decisions
3. Provide conversational interface to the boardroom

Supports OpenRouter models via LangChain.
"""

import os
import json
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
from dataclasses import dataclass
from datetime import datetime

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from .flow_orchestrator import FlowOrchestrator, FlowType, BoardMode, SessionState
from .base_agent import create_db_connection


# ============================================================================
# Output Schemas for LangChain
# ============================================================================

class FlowSelection(BaseModel):
    """Schema for flow selection output."""
    flow_type: str = Field(description="One of: kpi_review, trade_off, scenario, root_cause, board_memo")
    confidence: float = Field(description="Confidence score 0-1")
    reasoning: str = Field(description="Brief explanation for why this flow was selected")
    time_period: Optional[str] = Field(default=None, description="Time period if mentioned (e.g., 'last quarter', 'this month')")
    focus_areas: List[str] = Field(default=[], description="Specific areas to focus on")


class DecisionSummary(BaseModel):
    """Schema for final decision summary."""
    summary: str = Field(description="Executive summary of the decision (2-3 sentences)")
    key_findings: List[str] = Field(description="Top 3-5 key findings")
    recommendations: List[str] = Field(description="Top 3-5 actionable recommendations")
    risks: List[str] = Field(description="Key risks identified")
    confidence_level: str = Field(description="Overall confidence: High, Medium, or Low")
    next_steps: List[str] = Field(description="Suggested next steps")


# ============================================================================
# LangChain Orchestrator
# ============================================================================

class LangChainOrchestrator:
    """
    Orchestrates natural language conversations with the boardroom agents.

    Flow:
    1. User asks a question
    2. LLM selects appropriate flow (KPI Review, Trade-off, etc.)
    3. Flow executes with all agents
    4. LLM synthesizes results into a decision
    """

    def __init__(self, model: Optional[str] = None):
        """
        Initialize the LangChain orchestrator.

        Args:
            model: OpenRouter model to use (defaults to OPENROUTER_MODEL env var or claude-3-5-haiku)
        """
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable not set")

        # Get model from environment variable if not specified
        if model is None:
            model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3-5-haiku")

        # Initialize LangChain with OpenRouter
        self.llm = ChatOpenAI(
            model=model,
            openai_api_key=self.api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0.3,
            max_tokens=2000,
        )

        # Fast model for routing and quick analysis (use same model for consistency)
        self.router_llm = ChatOpenAI(
            model=model,
            openai_api_key=self.api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0.1,
            max_tokens=2000,
        )

        # Flow orchestrator for executing agent flows
        self.flow_orchestrator = FlowOrchestrator()

        # Conversation history
        self.conversation_history: List[Dict[str, str]] = []

        # Parsers
        self.flow_parser = PydanticOutputParser(pydantic_object=FlowSelection)
        self.decision_parser = PydanticOutputParser(pydantic_object=DecisionSummary)

        # Initialize prompts
        self._init_prompts()

    def _init_prompts(self):
        """Initialize prompt templates."""

        # Flow selection prompt
        self.flow_selection_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an AI assistant that routes business questions to the appropriate analysis flow.

Available flows:
1. kpi_review: General performance check - "How are we doing?", "What's our status?", "Performance overview"
2. trade_off: CFO vs CMO debate - "Should we invest in X or Y?", "Marketing vs margin trade-off"
3. scenario: What-if analysis - "What if we increase prices?", "Impact of expanding"
4. root_cause: Diagnostic analysis - "Why did sales drop?", "What caused the issue?"
5. board_memo: Executive summary - "Prepare board update", "Summary for leadership"

Select the most appropriate flow. Output ONLY valid JSON, no other text.

{format_instructions}"""),
            ("human", "{question}")
        ])

        # Decision synthesis prompt
        self.decision_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a Chief Strategy Officer synthesizing insights from multiple C-suite executives.

You have received analysis from:
- CEO: Strategic overview and growth metrics
- CFO: Financial metrics, margins, and cost analysis
- CMO: Marketing performance, customer insights, and promotions
- CIO: Data quality and system health
- Evaluator: Conflict detection and scoring

Your job is to synthesize these into a clear, actionable decision.

{format_instructions}"""),
            ("human", """Original Question: {question}

Agent Outputs:
{agent_outputs}

Evaluation Results:
{evaluation}

Please synthesize a decision summary.""")
        ])

        # Conversational response prompt
        self.response_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are the Boardroom AI Assistant. You help executives make data-driven decisions.

You have access to a team of AI agents:
- CEO Agent: Strategic overview
- CFO Agent: Financial analysis
- CMO Agent: Marketing insights
- CIO Agent: Data quality
- Evaluator: Decision scoring

Respond in a helpful, executive-friendly manner. Be concise but thorough.
When presenting numbers, format them clearly (e.g., $1.2M, 15.3%).
Highlight key risks and opportunities."""),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{input}")
        ])

    async def route_question(self, question: str) -> FlowSelection:
        """
        Route a question to the appropriate flow.

        Args:
            question: User's natural language question

        Returns:
            FlowSelection with the chosen flow and metadata
        """
        prompt = self.flow_selection_prompt.format_messages(
            question=question,
            format_instructions=self.flow_parser.get_format_instructions()
        )

        response = await self.router_llm.ainvoke(prompt)

        try:
            return self.flow_parser.parse(response.content)
        except Exception as e:
            # Default to KPI review if parsing fails
            return FlowSelection(
                flow_type="kpi_review",
                confidence=0.5,
                reasoning=f"Defaulting to KPI review (parse error: {e})",
                focus_areas=[]
            )

    def route_question_sync(self, question: str) -> FlowSelection:
        """Synchronous version of route_question."""
        prompt = self.flow_selection_prompt.format_messages(
            question=question,
            format_instructions=self.flow_parser.get_format_instructions()
        )

        response = self.router_llm.invoke(prompt)

        try:
            return self.flow_parser.parse(response.content)
        except Exception as e:
            # Try to extract JSON from response
            import re
            content = response.content
            json_match = re.search(r'\{[^{}]*"flow_type"[^{}]*\}', content, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    return FlowSelection(
                        flow_type=data.get('flow_type', 'kpi_review'),
                        confidence=data.get('confidence', 0.7),
                        reasoning=data.get('reasoning', 'Selected based on question analysis'),
                        time_period=data.get('time_period'),
                        focus_areas=data.get('focus_areas', [])
                    )
                except:
                    pass

            # Keyword-based routing fallback
            q_lower = question.lower()
            if any(word in q_lower for word in ['why', 'cause', 'reason', 'drop', 'decline', 'issue', 'problem']):
                return FlowSelection(flow_type="root_cause", confidence=0.7, reasoning="Detected diagnostic question", focus_areas=[])
            elif any(word in q_lower for word in ['should', 'vs', 'versus', 'or', 'trade', 'compare']):
                return FlowSelection(flow_type="trade_off", confidence=0.7, reasoning="Detected trade-off question", focus_areas=[])
            elif any(word in q_lower for word in ['what if', 'impact', 'scenario', 'increase', 'decrease', 'change']):
                return FlowSelection(flow_type="scenario", confidence=0.7, reasoning="Detected scenario question", focus_areas=[])
            elif any(word in q_lower for word in ['board', 'memo', 'summary', 'briefing', 'present']):
                return FlowSelection(flow_type="board_memo", confidence=0.7, reasoning="Detected executive summary request", focus_areas=[])
            else:
                return FlowSelection(flow_type="kpi_review", confidence=0.7, reasoning="General performance review", focus_areas=[])

    def execute_flow(
        self,
        flow_type: str,
        mode: str = "summary",
        period_start: str = None,
        period_end: str = None
    ) -> SessionState:
        """
        Execute an agent flow.

        Args:
            flow_type: Type of flow to execute
            mode: Display mode
            period_start: Start date (YYYY-MM-DD)
            period_end: End date (YYYY-MM-DD)

        Returns:
            SessionState with all agent outputs
        """
        flow_type_enum = FlowType(flow_type)
        mode_enum = BoardMode(mode)

        session = self.flow_orchestrator.start_session(
            flow_type=flow_type_enum,
            mode=mode_enum,
            period_start=period_start,
            period_end=period_end
        )

        session = self.flow_orchestrator.run_flow(session)

        return session

    def synthesize_decision(
        self,
        question: str,
        session: SessionState
    ) -> DecisionSummary:
        """
        Synthesize agent outputs into a decision.

        Args:
            question: Original user question
            session: Executed session with agent outputs

        Returns:
            DecisionSummary with synthesized decision
        """
        # Format agent outputs
        agent_outputs_text = ""
        for agent_name, node in session.nodes.items():
            if node.output:
                output = node.output
                agent_outputs_text += f"\n## {agent_name}\n"

                if output.kpis:
                    agent_outputs_text += "### KPIs:\n"
                    for kpi in output.kpis[:5]:
                        agent_outputs_text += f"- {kpi.name}: {kpi.value} ({kpi.trend})\n"

                if output.insights:
                    agent_outputs_text += "### Insights:\n"
                    for insight in output.insights[:3]:
                        agent_outputs_text += f"- {insight}\n"

                if output.recommendations:
                    agent_outputs_text += "### Recommendations:\n"
                    for rec in output.recommendations[:3]:
                        agent_outputs_text += f"- {rec.action} (Impact: {rec.impact})\n"

        # Format evaluation
        evaluation_text = ""
        if session.evaluation:
            eval_data = session.evaluation
            evaluation_text = f"""
Overall Score: {eval_data.overall_score}/10
Confidence: {eval_data.confidence}
Conflicts: {len(eval_data.conflicts)}
"""
            if eval_data.conflicts:
                evaluation_text += "Key Conflicts:\n"
                for conflict in eval_data.conflicts[:3]:
                    evaluation_text += f"- {conflict.issue} (between {', '.join(conflict.between)})\n"

        # Generate decision
        prompt = self.decision_prompt.format_messages(
            question=question,
            agent_outputs=agent_outputs_text,
            evaluation=evaluation_text,
            format_instructions=self.decision_parser.get_format_instructions()
        )

        response = self.llm.invoke(prompt)

        try:
            return self.decision_parser.parse(response.content)
        except Exception as e:
            # Try to extract JSON from response text
            import re
            content = response.content

            # Try extracting from markdown code blocks first
            json_str = None
            if '```json' in content:
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
            elif '```' in content:
                json_match = re.search(r'```\s*(\{.*?\})\s*```', content, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)

            # If no code blocks, look for JSON object in the text
            if not json_str:
                # Look for a complete JSON object with summary field
                json_match = re.search(r'\{\s*"summary"[^}]*?"next_steps"\s*:\s*\[.*?\]\s*\}', content, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
                else:
                    # Try to find any JSON object
                    json_match = re.search(r'\{[^{}]*"summary"[^{}]*\}', content, re.DOTALL)
                    if json_match:
                        json_str = json_match.group()

            if json_str:
                try:
                    data = json.loads(json_str)
                    return DecisionSummary(
                        summary=data.get('summary', content[:500]),
                        key_findings=data.get('key_findings', ["Analysis complete - see details above"]),
                        recommendations=data.get('recommendations', ["Review agent outputs for specific recommendations"]),
                        risks=data.get('risks', []),
                        confidence_level=data.get('confidence_level', 'Medium'),
                        next_steps=data.get('next_steps', [])
                    )
                except Exception as parse_error:
                    print(f"JSON parse error: {parse_error}")
                    print(f"Attempted to parse: {json_str[:200]}...")

            # Fallback: parse plain text response
            lines = content.split('\n')
            summary = content[:500] if len(content) < 500 else content[:497] + "..."

            # Return a basic summary if parsing fails
            return DecisionSummary(
                summary=summary,
                key_findings=["Analysis complete - see details above"],
                recommendations=["Review agent outputs for specific recommendations"],
                risks=[],
                confidence_level="Medium",
                next_steps=["Review detailed agent outputs"]
            )

    async def chat(self, question: str) -> Dict[str, Any]:
        """
        Main chat interface - routes question, executes flow, returns decision.

        Args:
            question: User's natural language question

        Returns:
            Dict with flow_selection, session_summary, and decision
        """
        # 1. Route the question
        flow_selection = await self.route_question(question)

        # 2. Execute the flow
        session = self.execute_flow(
            flow_type=flow_selection.flow_type,
            mode="summary"
        )

        # 3. Synthesize decision
        decision = self.synthesize_decision(question, session)

        # 4. Add to conversation history
        self.conversation_history.append({
            "role": "user",
            "content": question
        })
        self.conversation_history.append({
            "role": "assistant",
            "content": decision.summary
        })

        return {
            "flow_selection": {
                "flow_type": flow_selection.flow_type,
                "confidence": flow_selection.confidence,
                "reasoning": flow_selection.reasoning
            },
            "session": {
                "session_id": session.session_id,
                "flow_type": session.flow_spec.flow_type.value,
                "agents_involved": list(session.nodes.keys()),
                "overall_score": session.evaluation.overall_score if session.evaluation else None
            },
            "decision": {
                "summary": decision.summary,
                "key_findings": decision.key_findings,
                "recommendations": decision.recommendations,
                "risks": decision.risks,
                "confidence_level": decision.confidence_level,
                "next_steps": decision.next_steps
            }
        }

    def chat_sync(self, question: str, quick_mode: bool = False) -> Dict[str, Any]:
        """Synchronous version of chat.

        Args:
            question: User question
            quick_mode: If True, skip agent flow and do direct LLM analysis (faster)
        """
        # 1. Route the question
        flow_selection = self.route_question_sync(question)

        if quick_mode:
            # Quick mode - direct LLM response without running agents
            decision = self._quick_analysis(question, flow_selection)
            return {
                "flow_selection": {
                    "flow_type": flow_selection.flow_type,
                    "confidence": flow_selection.confidence,
                    "reasoning": flow_selection.reasoning
                },
                "session": {
                    "session_id": f"quick_{datetime.now().strftime('%H%M%S')}",
                    "flow_type": flow_selection.flow_type,
                    "agents_involved": self._get_agents_for_flow(flow_selection.flow_type),
                    "overall_score": 7.5
                },
                "decision": {
                    "summary": decision.summary,
                    "key_findings": decision.key_findings,
                    "recommendations": decision.recommendations,
                    "risks": decision.risks,
                    "confidence_level": decision.confidence_level,
                    "next_steps": decision.next_steps
                }
            }

        # 2. Execute the flow (full agent run - slower but more accurate)
        session = self.execute_flow(
            flow_type=flow_selection.flow_type,
            mode="summary"
        )

        # 3. Synthesize decision
        decision = self.synthesize_decision(question, session)

        # 4. Add to conversation history
        self.conversation_history.append({
            "role": "user",
            "content": question
        })
        self.conversation_history.append({
            "role": "assistant",
            "content": decision.summary
        })

        return {
            "flow_selection": {
                "flow_type": flow_selection.flow_type,
                "confidence": flow_selection.confidence,
                "reasoning": flow_selection.reasoning
            },
            "session": {
                "session_id": session.session_id,
                "flow_type": session.flow_spec.flow_type.value,
                "agents_involved": list(session.nodes.keys()),
                "overall_score": session.evaluation.overall_score if session.evaluation else None
            },
            "decision": {
                "summary": decision.summary,
                "key_findings": decision.key_findings,
                "recommendations": decision.recommendations,
                "risks": decision.risks,
                "confidence_level": decision.confidence_level,
                "next_steps": decision.next_steps
            },
            "full_session": session  # Include full session for agent outputs, handoffs, conflicts
        }

    def _get_agents_for_flow(self, flow_type: str) -> List[str]:
        """Get agent names for a flow type."""
        from .flow_orchestrator import FLOW_SPECS, FlowType
        try:
            ft = FlowType(flow_type)
            return FLOW_SPECS[ft]["nodes"]
        except:
            return ["CEO", "CFO", "CMO", "CIO", "Evaluator"]

    def _quick_analysis(self, question: str, flow_selection: FlowSelection) -> DecisionSummary:
        """Quick LLM-only analysis without running agent flows."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a Chief Strategy Officer providing strategic business analysis.

Selected analysis: {flow_type}

Analyze the business question and provide actionable insights covering:
- Growth and strategy (CEO view)
- Financial health and margins (CFO view)
- Customer and marketing trends (CMO view)
- Data and operations (CIO view)

Output ONLY valid JSON matching this exact format. No other text:
{format_instructions}"""),
            ("human", "{question}")
        ])

        # Use fast Haiku model for quick analysis
        response = self.router_llm.invoke(
            prompt.format_messages(
                flow_type=flow_selection.flow_type,
                reasoning=flow_selection.reasoning,
                question=question,
                format_instructions=self.decision_parser.get_format_instructions()
            )
        )

        try:
            return self.decision_parser.parse(response.content)
        except:
            # Try to extract JSON from the response
            import re
            content = response.content
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    return DecisionSummary(
                        summary=data.get('summary', content[:500]),
                        key_findings=data.get('key_findings', ['See analysis above']),
                        recommendations=data.get('recommendations', ['Review detailed analysis']),
                        risks=data.get('risks', ['Run full flow for comprehensive risk assessment']),
                        confidence_level=data.get('confidence_level', 'Medium'),
                        next_steps=data.get('next_steps', ['Run full analysis for detailed insights'])
                    )
                except:
                    pass
            # Fallback
            return DecisionSummary(
                summary=content[:500] if content else "Analysis complete",
                key_findings=["Strategic analysis provided"],
                recommendations=["Review detailed analysis for specific actions"],
                risks=["Quick analysis - run full flow for comprehensive risk assessment"],
                confidence_level="Medium",
                next_steps=["Run full analysis for detailed agent insights"]
            )

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """Get the conversation history."""
        return self.conversation_history

    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history = []


# ============================================================================
# Streaming Chat Interface
# ============================================================================

class StreamingBoardroomChat:
    """
    Streaming chat interface for real-time updates.
    Yields events as the flow progresses.
    """

    def __init__(self):
        self.orchestrator = LangChainOrchestrator()

    async def stream_chat(self, question: str):
        """
        Stream chat responses with progress updates.

        Yields events:
        - routing: Flow selection in progress
        - flow_selected: Flow has been selected
        - agent_start: Agent is starting
        - agent_complete: Agent has finished
        - synthesizing: Decision synthesis in progress
        - decision: Final decision
        """
        # 1. Route question
        yield {"event": "routing", "data": {"message": "Analyzing your question..."}}

        flow_selection = await self.orchestrator.route_question(question)

        yield {
            "event": "flow_selected",
            "data": {
                "flow_type": flow_selection.flow_type,
                "reasoning": flow_selection.reasoning,
                "confidence": flow_selection.confidence
            }
        }

        # 2. Execute flow (runs all agents including evaluator)
        yield {"event": "executing", "data": {"message": f"Running {flow_selection.flow_type} flow..."}}

        session = self.orchestrator.execute_flow(
            flow_type=flow_selection.flow_type,
            mode="summary"
        )

        # Emit completion events for each agent
        for agent_name in session.nodes.keys():
            yield {
                "event": "agent_complete",
                "data": {
                    "agent": agent_name,
                    "has_output": session.nodes[agent_name].output is not None
                }
            }

        # 4. Synthesize decision
        yield {"event": "synthesizing", "data": {"message": "Synthesizing decision..."}}

        decision = self.orchestrator.synthesize_decision(question, session)

        yield {
            "event": "decision",
            "data": {
                "summary": decision.summary,
                "key_findings": decision.key_findings,
                "recommendations": decision.recommendations,
                "risks": decision.risks,
                "confidence_level": decision.confidence_level,
                "next_steps": decision.next_steps,
                "session_id": session.session_id,
                "overall_score": session.evaluation.overall_score if session.evaluation else None
            }
        }


# ============================================================================
# Convenience Functions
# ============================================================================

def ask_boardroom(question: str) -> Dict[str, Any]:
    """
    Simple function to ask the boardroom a question.

    Args:
        question: Natural language question

    Returns:
        Decision dict with summary, findings, recommendations, etc.
    """
    orchestrator = LangChainOrchestrator()
    return orchestrator.chat_sync(question)


def get_flow_for_question(question: str) -> str:
    """
    Get the recommended flow type for a question.

    Args:
        question: Natural language question

    Returns:
        Flow type string
    """
    orchestrator = LangChainOrchestrator()
    selection = orchestrator.route_question_sync(question)
    return selection.flow_type
