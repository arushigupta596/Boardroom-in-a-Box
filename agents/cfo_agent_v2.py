"""
CFO Agent v2
============
Chief Financial Officer - Uses ONLY allowed views from cfo_views schema.
NO access to raw customer data or raw supplier tables.
"""

from typing import Optional
from .base_agent import BaseAgent, DatabaseConnection, GuardrailedDatabaseConnection
from .contract import (
    AgentOutput, AgentRole, KPI, Recommendation, Evidence,
    Trend, Confidence
)


class CFOAgentV2(BaseAgent):
    """
    CFO Agent v2 - Scope-enforced version with SQL guardrails.

    ALLOWED DATA SURFACE (cfo_views schema only):
    - cfo_views.margin_by_store
    - cfo_views.margin_by_category
    - cfo_views.cogs_summary
    - cfo_views.inventory_value
    - cfo_views.returns_impact
    - cfo_views.returns_by_reason
    - cfo_views.po_summary
    - cfo_views.discount_analysis
    - cfo_views.daily_pnl

    DENIED:
    - retail.customer (no individual data)
    - retail.supplier_product (use cogs_summary instead)

    SECURITY:
    - SQL guardrails enforce schema/table allowlist
    - Max 4 JOINs, 5000 row limit, 5s timeout
    - Date filter required for fact tables
    - DDL/DML operations blocked
    """

    # Enable guardrails for this agent
    ENABLE_GUARDRAILS = True

    ALLOWED_VIEWS = [
        'cfo_views.margin_by_store',
        'cfo_views.margin_by_category',
        'cfo_views.cogs_summary',
        'cfo_views.inventory_value',
        'cfo_views.returns_impact',
        'cfo_views.returns_by_reason',
        'cfo_views.po_summary',
        'cfo_views.discount_analysis',
        'cfo_views.daily_pnl',
    ]

    def _get_role_name(self) -> str:
        """Return role name for guardrails initialization."""
        return "CFO"

    @property
    def role(self) -> AgentRole:
        return AgentRole.CFO

    def analyze(self, date_from: str = None, date_to: str = None) -> AgentOutput:
        """Perform CFO analysis using allowed views only."""

        # Get date range if not specified
        if not date_from or not date_to:
            date_from, date_to = self._get_date_range_from_pnl()

        window = f"{date_from} to {date_to}"

        # Calculate KPIs from allowed views
        kpis = []

        # 1. Gross Margin % from daily P&L
        pnl_data = self._get_pnl_summary(date_from, date_to)
        margin_pct = (pnl_data['gross_profit'] / max(pnl_data['net_revenue'], 1)) * 100
        kpis.append(KPI(
            name="Gross Margin %",
            value=round(margin_pct, 1),
            unit="%",
            trend=self._get_margin_trend(date_from, date_to),
            window=window
        ))

        # 2. Net Revenue
        kpis.append(KPI(
            name="Net Revenue",
            value=round(pnl_data['net_revenue'], 2),
            unit="$",
            trend=Trend.UP,
            window=window
        ))

        # 3. Total COGS
        kpis.append(KPI(
            name="Total COGS",
            value=round(pnl_data['cogs'], 2),
            unit="$",
            trend=Trend.UP,
            window=window
        ))

        # 4. Discount Rate from discount_analysis
        discount_data = self._get_discount_summary(date_from, date_to)
        kpis.append(KPI(
            name="Avg Discount Rate",
            value=round(discount_data['discount_rate'], 1),
            unit="%",
            trend=Trend.FLAT,
            window=window
        ))

        # Generate insights
        insights = self._generate_insights(pnl_data, discount_data, date_from, date_to)

        # Identify risks
        risks = self._identify_risks(pnl_data, discount_data, date_from, date_to)

        # Generate recommendations
        recommendations = self._generate_recommendations(pnl_data, discount_data)

        return AgentOutput(
            agent=self.role,
            kpis=kpis,
            insights=insights[:3],
            risks=risks[:3],
            recommendations=recommendations[:3],
            evidence=self._evidence,
            confidence=Confidence.HIGH if pnl_data['net_revenue'] > 0 else Confidence.LOW
        )

    def _get_date_range_from_pnl(self) -> tuple:
        """Get date range from daily P&L view."""
        query = "SELECT MIN(sale_date) as min_date, MAX(sale_date) as max_date FROM cfo_views.daily_pnl"
        result = self.db.execute_query(query)
        if result and result[0]['min_date']:
            return result[0]['min_date'], result[0]['max_date']
        return '2025-01-01', '2025-03-31'

    def _get_pnl_summary(self, date_from: str, date_to: str) -> dict:
        """Get P&L summary from cfo_views.daily_pnl."""
        query = """
        SELECT
            SUM(gross_revenue) AS gross_revenue,
            SUM(discounts) AS discounts,
            SUM(net_revenue) AS net_revenue,
            SUM(cogs) AS cogs,
            SUM(gross_profit) AS gross_profit,
            SUM(returns) AS returns,
            SUM(adjusted_gross_profit) AS adjusted_gross_profit
        FROM cfo_views.daily_pnl
        WHERE sale_date BETWEEN %s AND %s
        """
        self._add_evidence("cfo_views.daily_pnl", f"sale_date between '{date_from}' and '{date_to}'")
        result = self.db.execute_query(query, (date_from, date_to))
        if result:
            return {
                'gross_revenue': result[0].get('gross_revenue', 0) or 0,
                'discounts': result[0].get('discounts', 0) or 0,
                'net_revenue': result[0].get('net_revenue', 0) or 0,
                'cogs': result[0].get('cogs', 0) or 0,
                'gross_profit': result[0].get('gross_profit', 0) or 0,
                'returns': result[0].get('returns', 0) or 0,
                'adjusted_gross_profit': result[0].get('adjusted_gross_profit', 0) or 0
            }
        return {'net_revenue': 0, 'cogs': 0, 'gross_profit': 0}

    def _get_discount_summary(self, date_from: str, date_to: str) -> dict:
        """Get discount summary from cfo_views.discount_analysis."""
        query = """
        SELECT
            SUM(gross_revenue) AS gross_revenue,
            SUM(total_discount) AS total_discount,
            CASE
                WHEN SUM(gross_revenue) > 0
                THEN SUM(total_discount) / SUM(gross_revenue) * 100
                ELSE 0
            END AS discount_rate
        FROM cfo_views.discount_analysis
        WHERE sale_date BETWEEN %s AND %s
        """
        self._add_evidence("cfo_views.discount_analysis", f"sale_date between '{date_from}' and '{date_to}'")
        result = self.db.execute_query(query, (date_from, date_to))
        if result:
            return {
                'gross_revenue': result[0].get('gross_revenue', 0) or 0,
                'total_discount': result[0].get('total_discount', 0) or 0,
                'discount_rate': result[0].get('discount_rate', 0) or 0
            }
        return {'discount_rate': 0}

    def _get_margin_by_category(self, date_from: str, date_to: str) -> list:
        """Get margin by category from cfo_views.margin_by_category."""
        query = """
        SELECT
            category_name,
            SUM(gross_revenue) AS gross_revenue,
            SUM(cogs) AS cogs,
            SUM(gross_margin) AS gross_margin,
            CASE
                WHEN SUM(gross_revenue) > 0
                THEN SUM(gross_margin) / SUM(gross_revenue) * 100
                ELSE 0
            END AS margin_pct
        FROM cfo_views.margin_by_category
        WHERE sale_date BETWEEN %s AND %s
        GROUP BY category_name
        ORDER BY margin_pct ASC
        LIMIT 5
        """
        self._add_evidence("cfo_views.margin_by_category", f"lowest margin categories")
        return self.db.execute_query(query, (date_from, date_to))

    def _get_margin_trend(self, date_from: str, date_to: str) -> Trend:
        """Calculate margin trend from daily P&L."""
        query = """
        WITH monthly AS (
            SELECT
                DATE_TRUNC('month', sale_date) AS month,
                SUM(gross_profit) / NULLIF(SUM(net_revenue), 0) * 100 AS margin_pct
            FROM cfo_views.daily_pnl
            WHERE sale_date BETWEEN %s AND %s
            GROUP BY DATE_TRUNC('month', sale_date)
            ORDER BY month
        )
        SELECT
            (SELECT margin_pct FROM monthly ORDER BY month LIMIT 1) AS first_month,
            (SELECT margin_pct FROM monthly ORDER BY month DESC LIMIT 1) AS last_month
        """
        result = self.db.execute_query(query, (date_from, date_to))
        if result and result[0]['first_month'] and result[0]['last_month']:
            return self._calculate_trend(result[0]['last_month'], result[0]['first_month'])
        return Trend.FLAT

    def _get_returns_summary(self, date_from: str, date_to: str) -> dict:
        """Get returns summary from cfo_views.returns_impact."""
        query = """
        SELECT
            SUM(return_count) AS total_returns,
            SUM(units_returned) AS units_returned,
            SUM(total_refund) AS total_refund
        FROM cfo_views.returns_impact
        WHERE return_date BETWEEN %s AND %s
        """
        self._add_evidence("cfo_views.returns_impact", f"return_date between '{date_from}' and '{date_to}'")
        result = self.db.execute_query(query, (date_from, date_to))
        if result:
            return {
                'total_returns': result[0].get('total_returns', 0) or 0,
                'units_returned': result[0].get('units_returned', 0) or 0,
                'total_refund': result[0].get('total_refund', 0) or 0
            }
        return {'total_refund': 0}

    def _get_inventory_value(self) -> dict:
        """Get inventory value from cfo_views.inventory_value."""
        query = """
        SELECT
            SUM(total_on_hand) AS total_units,
            SUM(inventory_cost_value) AS cost_value,
            SUM(inventory_retail_value) AS retail_value
        FROM cfo_views.inventory_value
        """
        self._add_evidence("cfo_views.inventory_value", "current inventory valuation")
        result = self.db.execute_query(query)
        if result:
            return {
                'total_units': result[0].get('total_units', 0) or 0,
                'cost_value': result[0].get('cost_value', 0) or 0,
                'retail_value': result[0].get('retail_value', 0) or 0
            }
        return {'cost_value': 0}

    def _generate_insights(self, pnl_data: dict, discount_data: dict,
                          date_from: str, date_to: str) -> list:
        """Generate CFO insights from allowed views."""
        insights = []

        # P&L insight
        margin_pct = (pnl_data['gross_profit'] / max(pnl_data['net_revenue'], 1)) * 100
        insights.append(
            f"Gross margin at {margin_pct:.1f}% with net revenue of ${pnl_data['net_revenue']:,.0f}."
        )

        # Discount insight
        discount_rate = discount_data.get('discount_rate', 0)
        if discount_rate > 5:
            insights.append(f"Discount rate of {discount_rate:.1f}% impacting margins.")
        else:
            insights.append(f"Discount rate controlled at {discount_rate:.1f}%.")

        # COGS insight
        cogs_pct = (pnl_data['cogs'] / max(pnl_data['net_revenue'], 1)) * 100
        insights.append(f"COGS represents {cogs_pct:.1f}% of net revenue.")

        return insights

    def _identify_risks(self, pnl_data: dict, discount_data: dict,
                       date_from: str, date_to: str) -> list:
        """Identify financial risks from allowed views."""
        risks = []

        margin_pct = (pnl_data['gross_profit'] / max(pnl_data['net_revenue'], 1)) * 100

        if margin_pct < 20:
            risks.append(f"Margin at {margin_pct:.1f}% is below 20% target threshold.")

        if margin_pct < 18:
            risks.append("Critical: Margin approaching floor level. Immediate review needed.")

        # Returns risk
        returns_data = self._get_returns_summary(date_from, date_to)
        return_pct = (returns_data['total_refund'] / max(pnl_data['net_revenue'], 1)) * 100
        if return_pct > 3:
            risks.append(f"Returns at {return_pct:.1f}% of revenue - above 3% threshold.")

        # Category margin risk
        low_margin_cats = self._get_margin_by_category(date_from, date_to)
        if low_margin_cats and low_margin_cats[0].get('margin_pct', 100) < 15:
            risks.append(
                f"Low margin in {low_margin_cats[0]['category_name']}: "
                f"{low_margin_cats[0]['margin_pct']:.1f}%"
            )

        if not risks:
            risks.append("Financial metrics within acceptable ranges.")

        return risks

    def _generate_recommendations(self, pnl_data: dict, discount_data: dict) -> list:
        """Generate CFO recommendations from allowed view data."""
        recommendations = []

        margin_pct = (pnl_data['gross_profit'] / max(pnl_data['net_revenue'], 1)) * 100
        discount_rate = discount_data.get('discount_rate', 0)

        if margin_pct < 25:
            recommendations.append(Recommendation(
                action="Review category-level pricing to improve overall margin",
                impact=f"Target margin increase from {margin_pct:.1f}% toward 25%",
                priority="High" if margin_pct < 20 else "Medium"
            ))

        if discount_rate > 5:
            recommendations.append(Recommendation(
                action="Implement discount caps on low-margin categories",
                impact=f"Reduce discount rate from {discount_rate:.1f}% to protect margins",
                priority="High"
            ))

        # Inventory recommendation
        inv_data = self._get_inventory_value()
        if inv_data['cost_value'] > 0:
            recommendations.append(Recommendation(
                action="Optimize inventory levels to improve working capital",
                impact=f"Current inventory at ${inv_data['cost_value']:,.0f} cost value",
                priority="Medium"
            ))

        return recommendations


# CLI interface
if __name__ == "__main__":
    import sys

    agent = CFOAgentV2()
    date_from = sys.argv[1] if len(sys.argv) > 1 else None
    date_to = sys.argv[2] if len(sys.argv) > 2 else None

    print(agent.run(date_from, date_to))
