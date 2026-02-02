"""
Intent Router - LLM-Powered Flow Selection
===========================================
Takes a user question and decides:
- Which flow to run (KPI Review, Trade-off, Scenario, Root Cause, Memo)
- Which agents should participate
- What time window applies

Uses LLM for natural language understanding but applies deterministic
validation on the output.
"""

import json
import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from .llm_client import LLMClient, LLMModel, get_llm_client


class IntentType(Enum):
    """Detected intent types."""
    KPI_REVIEW = "kpi_review"          # General performance check
    TRADE_OFF = "trade_off"            # CFO vs CMO debate
    SCENARIO = "scenario"              # What-if analysis
    ROOT_CAUSE = "root_cause"          # Why did X happen?
    BOARD_MEMO = "board_memo"          # Executive summary
    DIRECT_QUERY = "direct_query"      # Specific data question
    CLARIFICATION = "clarification"    # Need more info


@dataclass
class ParsedIntent:
    """Parsed user intent."""
    intent_type: IntentType
    confidence: float  # 0-1
    agents: List[str]
    time_window: Dict[str, str]  # {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}
    focus_areas: List[str]       # e.g., ["margin", "inventory", "regional"]
    parameters: Dict[str, Any]   # Flow-specific params
    original_question: str
    reasoning: str


ROUTER_SYSTEM_PROMPT = """You are an intent router for a retail analytics boardroom system.

Given a user question, determine:
1. Which analysis flow to run
2. Which agents should participate
3. What time window applies
4. Key focus areas

AVAILABLE FLOWS:
- kpi_review: General performance review (CEO → CFO → CMO → CIO → Evaluator)
- trade_off: Debate between finance and marketing (CFO vs CMO → Evaluator)
- scenario: What-if analysis with parameters (CFO → CMO → Evaluator)
- root_cause: Diagnostic analysis (CIO → CFO → CMO → Evaluator)
- board_memo: Executive summary only (CEO → Evaluator)
- direct_query: Specific data question (single agent)
- clarification: Need more information from user

AVAILABLE AGENTS:
- CEO: Strategic overview, revenue, margin, growth
- CFO: Financial metrics, margin, costs, discounts, inventory value
- CMO: Sales, transactions, customers, promotions, basket analysis
- CIO: Data quality, system health, freshness checks

TIME WINDOWS (use relative dates from today):
- "last week", "this month", "last quarter", "YTD", etc.
- Default to last 90 days if not specified
- Today's date: {today}

FOCUS AREAS:
- revenue, margin, profit, sales
- inventory, stock, days_of_inventory
- promotions, discounts, marketing
- customers, transactions, basket
- regional, stores, geography
- categories, products, SKUs
- data_quality, freshness, health

Respond in JSON format:
{{
  "intent_type": "kpi_review|trade_off|scenario|root_cause|board_memo|direct_query|clarification",
  "confidence": 0.0-1.0,
  "agents": ["CEO", "CFO", ...],
  "time_window": {{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}},
  "focus_areas": ["margin", "inventory", ...],
  "parameters": {{}},
  "reasoning": "Brief explanation of why this flow was chosen"
}}
"""

EXAMPLES = """
EXAMPLES:

User: "How are we doing?"
→ kpi_review, all agents, last 90 days, focus: [revenue, margin]

User: "Should we run a promotion on electronics?"
→ trade_off, [CFO, CMO], last 30 days, focus: [promotions, margin, category]

User: "What if we increase discount to 20%?"
→ scenario, [CFO, CMO], last 90 days, focus: [margin, discounts], params: {discount_rate: 0.20}

User: "Why did margin drop last month?"
→ root_cause, [CIO, CFO, CMO], last month, focus: [margin, discounts, costs]

User: "Give me a board summary"
→ board_memo, [CEO], last quarter, focus: [revenue, margin, growth]

User: "What's the data freshness?"
→ direct_query, [CIO], current, focus: [data_quality, freshness]

User: "Compare regions"
→ kpi_review, [CEO], last 90 days, focus: [regional, revenue]
"""


class IntentRouter:
    """
    Routes user questions to appropriate flows using LLM.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client

    def _get_llm(self) -> LLMClient:
        """Get LLM client (lazy initialization)."""
        if self.llm is None:
            self.llm = get_llm_client()
        return self.llm

    def parse_intent(self, question: str) -> ParsedIntent:
        """
        Parse user question into a structured intent.

        Args:
            question: Natural language question from user

        Returns:
            ParsedIntent with flow selection and parameters
        """
        today = datetime.now().strftime("%Y-%m-%d")

        system_prompt = ROUTER_SYSTEM_PROMPT.format(today=today) + "\n" + EXAMPLES

        prompt = f"User question: {question}\n\nParse this into a flow selection."

        try:
            llm = self._get_llm()
            result = llm.complete_json(
                prompt=prompt,
                system=system_prompt,
                model=LLMModel.CLAUDE_HAIKU,  # Fast model for routing
                temperature=0.1,
            )

            # Validate and normalize the result
            return self._validate_and_build(result, question)

        except Exception as e:
            # Fallback to default KPI review
            return self._fallback_intent(question, str(e))

    def _validate_and_build(self, result: Dict, question: str) -> ParsedIntent:
        """Validate LLM output and build ParsedIntent."""

        # Validate intent type
        intent_str = result.get("intent_type", "kpi_review")
        try:
            intent_type = IntentType(intent_str)
        except ValueError:
            intent_type = IntentType.KPI_REVIEW

        # Validate agents
        valid_agents = {"CEO", "CFO", "CMO", "CIO"}
        agents = [a for a in result.get("agents", []) if a in valid_agents]
        if not agents:
            agents = self._default_agents_for_intent(intent_type)

        # Validate time window
        time_window = result.get("time_window", {})
        time_window = self._validate_time_window(time_window)

        # Validate focus areas
        valid_focus = {
            "revenue", "margin", "profit", "sales", "inventory", "stock",
            "promotions", "discounts", "marketing", "customers", "transactions",
            "basket", "regional", "stores", "geography", "categories",
            "products", "skus", "data_quality", "freshness", "health"
        }
        focus_areas = [f for f in result.get("focus_areas", []) if f.lower() in valid_focus]

        return ParsedIntent(
            intent_type=intent_type,
            confidence=min(1.0, max(0.0, result.get("confidence", 0.8))),
            agents=agents,
            time_window=time_window,
            focus_areas=focus_areas,
            parameters=result.get("parameters", {}),
            original_question=question,
            reasoning=result.get("reasoning", ""),
        )

    def _default_agents_for_intent(self, intent_type: IntentType) -> List[str]:
        """Get default agents for an intent type."""
        defaults = {
            IntentType.KPI_REVIEW: ["CEO", "CFO", "CMO", "CIO"],
            IntentType.TRADE_OFF: ["CFO", "CMO"],
            IntentType.SCENARIO: ["CFO", "CMO"],
            IntentType.ROOT_CAUSE: ["CIO", "CFO", "CMO"],
            IntentType.BOARD_MEMO: ["CEO"],
            IntentType.DIRECT_QUERY: ["CEO"],
            IntentType.CLARIFICATION: [],
        }
        return defaults.get(intent_type, ["CEO"])

    def _validate_time_window(self, window: Dict) -> Dict[str, str]:
        """Validate and normalize time window."""
        today = datetime.now()

        # Default: last 90 days
        default_start = (today - timedelta(days=90)).strftime("%Y-%m-%d")
        default_end = today.strftime("%Y-%m-%d")

        start = window.get("start", default_start)
        end = window.get("end", default_end)

        # Validate date formats
        try:
            datetime.strptime(start, "%Y-%m-%d")
        except (ValueError, TypeError):
            start = default_start

        try:
            datetime.strptime(end, "%Y-%m-%d")
        except (ValueError, TypeError):
            end = default_end

        return {"start": start, "end": end}

    def _fallback_intent(self, question: str, error: str) -> ParsedIntent:
        """Create fallback intent when LLM fails."""
        today = datetime.now()

        return ParsedIntent(
            intent_type=IntentType.KPI_REVIEW,
            confidence=0.5,
            agents=["CEO", "CFO", "CMO", "CIO"],
            time_window={
                "start": (today - timedelta(days=90)).strftime("%Y-%m-%d"),
                "end": today.strftime("%Y-%m-%d"),
            },
            focus_areas=["revenue", "margin"],
            parameters={},
            original_question=question,
            reasoning=f"Fallback due to: {error}",
        )

    def to_flow_config(self, intent: ParsedIntent) -> Dict[str, Any]:
        """Convert ParsedIntent to flow configuration."""
        from .flow_orchestrator import FlowType

        # Map intent to flow type
        flow_map = {
            IntentType.KPI_REVIEW: FlowType.KPI_REVIEW,
            IntentType.TRADE_OFF: FlowType.TRADE_OFF,
            IntentType.SCENARIO: FlowType.SCENARIO,
            IntentType.ROOT_CAUSE: FlowType.ROOT_CAUSE,
            IntentType.BOARD_MEMO: FlowType.BOARD_MEMO,
            IntentType.DIRECT_QUERY: FlowType.KPI_REVIEW,  # Fallback
            IntentType.CLARIFICATION: FlowType.KPI_REVIEW,
        }

        return {
            "flow_type": flow_map.get(intent.intent_type, FlowType.KPI_REVIEW),
            "period_start": intent.time_window["start"],
            "period_end": intent.time_window["end"],
            "agents": intent.agents,
            "focus_areas": intent.focus_areas,
            "parameters": intent.parameters,
        }


# Convenience function
def route_question(question: str) -> ParsedIntent:
    """Route a user question to the appropriate flow."""
    router = IntentRouter()
    return router.parse_intent(question)
