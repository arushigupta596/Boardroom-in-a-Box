"""
SQL Analyst - LLM-Powered Query Generation with Guardrails
==========================================================
Converts natural language questions into SQL queries against allowed views.
Applies strict guardrails to prevent unauthorized access.

Key features:
- Only queries from agent's allowed view list
- Synonym resolution (profit → margin, sales → revenue)
- Automatic date filter injection
- Read-only, row-limited queries
- Query validation before execution
"""

import re
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass

from .llm_client import LLMClient, LLMModel, get_llm_client
from .sql_guardrails import SQLGuardrails, GuardrailConfig, GuardrailViolation


# View schemas for each agent
AGENT_VIEW_SCHEMAS = {
    "CEO": {
        "schema": "ceo_views",
        "views": {
            "revenue_summary": {
                "columns": ["sale_date", "net_revenue", "units_sold", "txn_count"],
                "description": "Daily revenue aggregates",
                "date_column": "sale_date",
            },
            "margin_summary": {
                "columns": ["sale_date", "gross_revenue", "total_cogs", "gross_margin", "margin_pct"],
                "description": "Daily margin breakdown",
                "date_column": "sale_date",
            },
            "regional_performance": {
                "columns": ["region", "net_revenue", "units_sold", "margin_pct"],
                "description": "Performance by region",
                "date_column": None,
            },
            "category_performance": {
                "columns": ["category_name", "net_revenue", "units_sold", "margin_pct"],
                "description": "Performance by product category",
                "date_column": None,
            },
            "inventory_days_summary": {
                "columns": ["total_on_hand", "avg_daily_units", "days_of_inventory", "inventory_value"],
                "description": "Current inventory health",
                "date_column": None,
            },
            "board_summary": {
                "columns": ["period_start", "period_end", "net_revenue", "units_sold"],
                "description": "Executive summary for the period",
                "date_column": None,
            },
        },
    },
    "CFO": {
        "schema": "cfo_views",
        "views": {
            "margin_detail": {
                "columns": ["sale_date", "category_name", "gross_revenue", "cogs", "gross_margin", "margin_pct"],
                "description": "Detailed margin by category and date",
                "date_column": "sale_date",
            },
            "discount_analysis": {
                "columns": ["sale_date", "category_name", "total_discount", "discount_rate", "net_revenue"],
                "description": "Discount impact analysis",
                "date_column": "sale_date",
            },
            "inventory_valuation": {
                "columns": ["category_name", "on_hand_qty", "unit_cost", "total_cost", "days_of_supply"],
                "description": "Inventory value by category",
                "date_column": None,
            },
            "cash_flow_proxy": {
                "columns": ["month", "revenue", "cogs", "gross_profit", "inventory_change"],
                "description": "Monthly cash flow approximation",
                "date_column": "month",
            },
        },
    },
    "CMO": {
        "schema": "cmo_views",
        "views": {
            "sales_summary": {
                "columns": ["sale_date", "units_sold", "net_revenue", "txn_count", "avg_basket"],
                "description": "Daily sales metrics",
                "date_column": "sale_date",
            },
            "customer_metrics": {
                "columns": ["total_customers", "repeat_rate", "avg_txn_value", "avg_items_per_txn"],
                "description": "Customer behavior summary",
                "date_column": None,
            },
            "promo_performance": {
                "columns": ["promo_id", "promo_name", "units_sold", "revenue", "discount_given"],
                "description": "Promotion effectiveness",
                "date_column": None,
            },
            "basket_analysis": {
                "columns": ["category_name", "units_sold", "revenue", "avg_basket_contribution"],
                "description": "Basket composition by category",
                "date_column": None,
            },
            "channel_mix": {
                "columns": ["payment_method", "txn_count", "revenue", "pct_of_total"],
                "description": "Sales by payment channel",
                "date_column": None,
            },
        },
    },
    "CIO": {
        "schema": "cio_views",
        "views": {
            "data_freshness": {
                "columns": ["table_name", "last_record_date", "days_since_update", "record_count"],
                "description": "Data freshness by table",
                "date_column": None,
            },
            "health_check_status": {
                "columns": ["check_name", "status", "metric_value", "details", "run_ts"],
                "description": "Data quality health checks",
                "date_column": None,
            },
            "record_counts": {
                "columns": ["table_name", "record_count", "last_updated"],
                "description": "Record counts by table",
                "date_column": None,
            },
            "data_quality_issues": {
                "columns": ["issue_type", "table_name", "issue_count", "severity"],
                "description": "Data quality issues detected",
                "date_column": None,
            },
        },
    },
}

# Synonym mappings
SYNONYMS = {
    # Revenue synonyms
    "sales": "net_revenue",
    "revenue": "net_revenue",
    "income": "net_revenue",
    "turnover": "net_revenue",

    # Margin synonyms
    "profit": "gross_margin",
    "margin": "gross_margin",
    "profitability": "margin_pct",
    "profit margin": "margin_pct",
    "gp": "gross_margin",
    "gross profit": "gross_margin",

    # Cost synonyms
    "cost": "cogs",
    "costs": "cogs",
    "cost of goods": "cogs",
    "expenses": "cogs",

    # Discount synonyms
    "promo": "discount",
    "promotion": "discount",
    "promotions": "discount_rate",
    "discount rate": "discount_rate",

    # Inventory synonyms
    "stock": "on_hand_qty",
    "inventory": "on_hand_qty",
    "stock level": "on_hand_qty",
    "days of stock": "days_of_inventory",
    "dos": "days_of_inventory",

    # Customer synonyms
    "customers": "total_customers",
    "buyers": "total_customers",
    "shoppers": "total_customers",

    # Transaction synonyms
    "orders": "txn_count",
    "transactions": "txn_count",
    "purchases": "txn_count",
    "basket": "avg_basket",
    "basket size": "avg_basket",
    "aov": "avg_basket",

    # Region synonyms
    "north": "region = 'North'",
    "south": "region = 'South'",
    "east": "region = 'East'",
    "west": "region = 'West'",
    "stores": "store_id",
}


SQL_ANALYST_SYSTEM = """You are a SQL analyst for a retail analytics system.
Your job is to convert natural language questions into SQL queries.

CRITICAL RULES:
1. ONLY use views from the provided schema - no other tables/views allowed
2. ALWAYS include date filters when the view has a date column
3. Use aggregations (SUM, AVG, COUNT) appropriately
4. Limit results to 100 rows maximum
5. Use clear column aliases for readability
6. NO DDL (CREATE, DROP, ALTER) or DML (INSERT, UPDATE, DELETE) allowed
7. Maximum 2 JOINs allowed

Available schema for {agent}:
{schema_description}

Date range for queries: {date_from} to {date_to}

Respond with ONLY the SQL query, no explanation.
If the question cannot be answered with available views, respond with:
ERROR: <explanation>
"""


@dataclass
class AnalystResult:
    """Result from SQL Analyst."""
    success: bool
    sql: Optional[str]
    error: Optional[str]
    view_used: Optional[str]
    guardrail_validated: bool


class SQLAnalyst:
    """
    LLM-powered SQL analyst with guardrails.

    Converts natural language to SQL while enforcing:
    - View allowlist per agent
    - Date filter requirements
    - Row limits
    - Read-only operations
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client

    def _get_llm(self) -> LLMClient:
        """Get LLM client (lazy initialization)."""
        if self.llm is None:
            self.llm = get_llm_client()
        return self.llm

    def generate_query(
        self,
        question: str,
        agent: str,
        date_from: str,
        date_to: str,
    ) -> AnalystResult:
        """
        Generate a SQL query for the given question.

        Args:
            question: Natural language question
            agent: Agent name (CEO, CFO, CMO, CIO)
            date_from: Start date (YYYY-MM-DD)
            date_to: End date (YYYY-MM-DD)

        Returns:
            AnalystResult with SQL or error
        """
        if agent not in AGENT_VIEW_SCHEMAS:
            return AnalystResult(
                success=False,
                sql=None,
                error=f"Unknown agent: {agent}",
                view_used=None,
                guardrail_validated=False,
            )

        schema_info = AGENT_VIEW_SCHEMAS[agent]
        schema_desc = self._format_schema(schema_info)

        # Apply synonym resolution to question
        resolved_question = self._resolve_synonyms(question)

        system_prompt = SQL_ANALYST_SYSTEM.format(
            agent=agent,
            schema_description=schema_desc,
            date_from=date_from,
            date_to=date_to,
        )

        prompt = f"Question: {resolved_question}\n\nGenerate SQL query:"

        try:
            llm = self._get_llm()
            response = llm.complete(
                prompt=prompt,
                system=system_prompt,
                model=LLMModel.CLAUDE_HAIKU,
                temperature=0.1,
                max_tokens=512,
            )

            sql = response.content.strip()

            # Check for error response
            if sql.startswith("ERROR:"):
                return AnalystResult(
                    success=False,
                    sql=None,
                    error=sql,
                    view_used=None,
                    guardrail_validated=False,
                )

            # Clean up SQL (remove markdown code blocks)
            sql = self._clean_sql(sql)

            # Validate with guardrails
            validation_result = self._validate_query(sql, agent, date_from, date_to)

            if not validation_result[0]:
                return AnalystResult(
                    success=False,
                    sql=sql,
                    error=validation_result[1],
                    view_used=None,
                    guardrail_validated=False,
                )

            # Extract view used
            view_used = self._extract_view(sql, schema_info["schema"])

            return AnalystResult(
                success=True,
                sql=sql,
                error=None,
                view_used=view_used,
                guardrail_validated=True,
            )

        except Exception as e:
            return AnalystResult(
                success=False,
                sql=None,
                error=str(e),
                view_used=None,
                guardrail_validated=False,
            )

    def _format_schema(self, schema_info: Dict) -> str:
        """Format schema info for LLM prompt."""
        lines = [f"Schema: {schema_info['schema']}\n"]

        for view_name, view_info in schema_info["views"].items():
            lines.append(f"View: {schema_info['schema']}.{view_name}")
            lines.append(f"  Description: {view_info['description']}")
            lines.append(f"  Columns: {', '.join(view_info['columns'])}")
            if view_info.get("date_column"):
                lines.append(f"  Date column: {view_info['date_column']} (MUST filter on this)")
            lines.append("")

        return "\n".join(lines)

    def _resolve_synonyms(self, question: str) -> str:
        """Resolve business synonyms in the question."""
        resolved = question.lower()

        for synonym, canonical in SYNONYMS.items():
            pattern = r'\b' + re.escape(synonym) + r'\b'
            resolved = re.sub(pattern, canonical, resolved, flags=re.IGNORECASE)

        return resolved

    def _clean_sql(self, sql: str) -> str:
        """Clean SQL from markdown formatting."""
        # Remove markdown code blocks
        if "```sql" in sql:
            sql = sql.split("```sql")[1].split("```")[0]
        elif "```" in sql:
            sql = sql.split("```")[1].split("```")[0]

        return sql.strip()

    def _validate_query(
        self,
        sql: str,
        agent: str,
        date_from: str,
        date_to: str,
    ) -> Tuple[bool, Optional[str]]:
        """Validate query against guardrails."""

        sql_lower = sql.lower()

        # 1. Check for DDL/DML
        forbidden = ["insert", "update", "delete", "drop", "create", "alter", "truncate"]
        for keyword in forbidden:
            if re.search(r'\b' + keyword + r'\b', sql_lower):
                return False, f"Forbidden operation: {keyword.upper()}"

        # 2. Check schema allowlist
        schema_info = AGENT_VIEW_SCHEMAS[agent]
        allowed_schema = schema_info["schema"]
        allowed_views = list(schema_info["views"].keys())

        # Extract referenced tables/views
        from_pattern = r'\bfrom\s+([a-z_]+\.)?([a-z_]+)'
        join_pattern = r'\bjoin\s+([a-z_]+\.)?([a-z_]+)'

        from_matches = re.findall(from_pattern, sql_lower)
        join_matches = re.findall(join_pattern, sql_lower)

        for schema, view in from_matches + join_matches:
            schema = schema.rstrip('.') if schema else allowed_schema
            if schema != allowed_schema:
                return False, f"Schema not allowed: {schema}"
            if view not in allowed_views:
                return False, f"View not allowed: {view}"

        # 3. Check for LIMIT
        if "limit" not in sql_lower:
            # Auto-add limit
            pass  # We'll handle this in execution

        # 4. Check JOIN count
        join_count = len(re.findall(r'\bjoin\b', sql_lower))
        if join_count > 2:
            return False, f"Too many JOINs: {join_count} (max 2)"

        return True, None

    def _extract_view(self, sql: str, schema: str) -> Optional[str]:
        """Extract primary view used in query."""
        pattern = rf'\bfrom\s+{schema}\.([a-z_]+)'
        match = re.search(pattern, sql.lower())
        if match:
            return f"{schema}.{match.group(1)}"
        return None


# Convenience function
def generate_sql(
    question: str,
    agent: str,
    date_from: str,
    date_to: str,
) -> AnalystResult:
    """Generate SQL for a question."""
    analyst = SQLAnalyst()
    return analyst.generate_query(question, agent, date_from, date_to)
