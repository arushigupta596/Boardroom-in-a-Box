"""
CEO Agent v2
============
Chief Executive Officer - Uses ONLY allowed views from ceo_views schema.
NO access to raw tables, customer data, or supplier costs.
"""

from typing import Optional, List
from .base_agent import BaseAgent, DatabaseConnection, GuardrailedDatabaseConnection
from .contract import (
    AgentOutput, AgentRole, KPI, Recommendation, Evidence,
    Trend, Confidence
)


class CEOAgentV2(BaseAgent):
    """
    CEO Agent v2 - Scope-enforced version with SQL guardrails.

    ALLOWED DATA SURFACE (ceo_views schema only):
    - ceo_views.revenue_summary
    - ceo_views.margin_summary
    - ceo_views.sssg_proxy
    - ceo_views.inventory_days_summary
    - ceo_views.regional_performance
    - ceo_views.category_performance
    - ceo_views.board_summary

    DENIED:
    - retail.customer (no individual data)
    - retail.pos_transaction (no transaction detail)
    - retail.supplier_product (no cost data)

    SECURITY:
    - SQL guardrails enforce schema/table allowlist
    - Max 3 JOINs, 1000 row limit, 5s timeout
    - DDL/DML operations blocked
    """

    # Enable guardrails for this agent
    ENABLE_GUARDRAILS = True

    # Define allowed views for this agent
    ALLOWED_VIEWS = [
        'ceo_views.revenue_summary',
        'ceo_views.margin_summary',
        'ceo_views.sssg_proxy',
        'ceo_views.inventory_days_summary',
        'ceo_views.regional_performance',
        'ceo_views.category_performance',
        'ceo_views.board_summary',
    ]

    def _get_role_name(self) -> str:
        """Return role name for guardrails initialization."""
        return "CEO"

    @property
    def role(self) -> AgentRole:
        return AgentRole.CEO

    def analyze(self, date_from: str = None, date_to: str = None) -> AgentOutput:
        """Perform CEO-level strategic analysis using allowed views only."""

        # Get date range from board summary
        board_summary = self._get_board_summary()
        if not date_from:
            date_from = board_summary.get('period_start', '2025-01-01')
        if not date_to:
            date_to = board_summary.get('period_end', '2025-03-31')

        window = f"{date_from} to {date_to}"

        # Calculate strategic KPIs using allowed views
        kpis = []

        # 1. Net Revenue from board summary
        kpis.append(KPI(
            name="Net Revenue",
            value=round(board_summary['net_revenue'], 2),
            unit="$",
            trend=Trend.UP,
            window=window
        ))

        # 2. Gross Margin from margin summary
        margin_data = self._get_margin_summary(date_from, date_to)
        kpis.append(KPI(
            name="Gross Margin",
            value=round(margin_data['margin_pct'], 1),
            unit="%",
            trend=self._get_margin_trend(date_from, date_to),
            window=window
        ))

        # 3. Units Sold
        kpis.append(KPI(
            name="Units Sold",
            value=int(board_summary['units_sold']),
            unit="units",
            trend=Trend.UP,
            window=window
        ))

        # 4. Inventory Days
        inventory_data = self._get_inventory_days()
        kpis.append(KPI(
            name="Days of Inventory",
            value=round(inventory_data['days_of_inventory'], 1),
            unit="days",
            trend=Trend.FLAT,
            window="Current"
        ))

        # Generate insights from allowed views
        insights = self._generate_insights(board_summary, margin_data, date_from, date_to)

        # Identify risks from regional and category data
        risks = self._identify_risks(date_from, date_to)

        # Generate strategic recommendations
        recommendations = self._generate_recommendations(margin_data)

        return AgentOutput(
            agent=self.role,
            kpis=kpis,
            insights=insights[:3],
            risks=risks[:3],
            recommendations=recommendations[:3],
            evidence=self._evidence,
            confidence=Confidence.HIGH
        )

    def _get_board_summary(self) -> dict:
        """Get executive summary from ceo_views.board_summary."""
        query = "SELECT * FROM ceo_views.board_summary"
        self._add_evidence("ceo_views.board_summary", "executive summary")
        result = self.db.execute_query(query)
        if result:
            return {
                'period_start': result[0].get('period_start'),
                'period_end': result[0].get('period_end'),
                'net_revenue': result[0].get('net_revenue', 0) or 0,
                'units_sold': result[0].get('units_sold', 0) or 0
            }
        return {'net_revenue': 0, 'units_sold': 0}

    def _get_margin_summary(self, date_from: str, date_to: str) -> dict:
        """Get margin summary from ceo_views.margin_summary."""
        query = """
        SELECT
            SUM(gross_revenue) AS gross_revenue,
            SUM(total_cogs) AS total_cogs,
            SUM(gross_margin) AS gross_margin,
            CASE
                WHEN SUM(gross_revenue) > 0
                THEN ROUND((SUM(gross_margin) / SUM(gross_revenue) * 100)::numeric, 2)
                ELSE 0
            END AS margin_pct
        FROM ceo_views.margin_summary
        WHERE sale_date BETWEEN %s AND %s
        """
        self._add_evidence("ceo_views.margin_summary", f"sale_date between '{date_from}' and '{date_to}'")
        result = self.db.execute_query(query, (date_from, date_to))
        if result:
            return {
                'gross_revenue': result[0].get('gross_revenue', 0) or 0,
                'total_cogs': result[0].get('total_cogs', 0) or 0,
                'gross_margin': result[0].get('gross_margin', 0) or 0,
                'margin_pct': result[0].get('margin_pct', 0) or 0
            }
        return {'margin_pct': 0}

    def _get_margin_trend(self, date_from: str, date_to: str) -> Trend:
        """Calculate margin trend from ceo_views.margin_summary."""
        query = """
        WITH monthly AS (
            SELECT
                DATE_TRUNC('month', sale_date) AS month,
                SUM(gross_margin) / NULLIF(SUM(gross_revenue), 0) * 100 AS margin_pct
            FROM ceo_views.margin_summary
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

    def _get_inventory_days(self) -> dict:
        """Get inventory days from ceo_views.inventory_days_summary."""
        query = "SELECT * FROM ceo_views.inventory_days_summary"
        self._add_evidence("ceo_views.inventory_days_summary", "current inventory health")
        result = self.db.execute_query(query)
        if result:
            return {
                'total_on_hand': result[0].get('total_on_hand', 0) or 0,
                'avg_daily_units': result[0].get('avg_daily_units', 0) or 0,
                'days_of_inventory': result[0].get('days_of_inventory', 0) or 0
            }
        return {'days_of_inventory': 0}

    def _get_regional_performance(self) -> list:
        """Get regional performance from ceo_views.regional_performance."""
        query = "SELECT * FROM ceo_views.regional_performance ORDER BY net_revenue DESC"
        self._add_evidence("ceo_views.regional_performance", "regional aggregates")
        return self.db.execute_query(query)

    def _get_category_performance(self, limit: int = 5) -> list:
        """Get category performance from ceo_views.category_performance."""
        query = f"SELECT * FROM ceo_views.category_performance LIMIT {limit}"
        self._add_evidence("ceo_views.category_performance", f"top {limit} categories")
        return self.db.execute_query(query)

    def _get_sssg(self) -> list:
        """Get same-store sales growth from ceo_views.sssg_proxy."""
        query = "SELECT * FROM ceo_views.sssg_proxy ORDER BY current_month DESC LIMIT 3"
        self._add_evidence("ceo_views.sssg_proxy", "recent SSSG trends")
        return self.db.execute_query(query)

    def _generate_insights(self, board_summary: dict, margin_data: dict,
                          date_from: str, date_to: str) -> list:
        """Generate insights from allowed views only."""
        insights = []

        # Revenue insight from board summary
        revenue = board_summary.get('net_revenue', 0)
        units = board_summary.get('units_sold', 0)
        insights.append(
            f"Total revenue of ${revenue:,.0f} from {units:,} units sold."
        )

        # Margin insight
        margin_pct = margin_data.get('margin_pct', 0)
        if margin_pct >= 25:
            insights.append(f"Strong gross margin of {margin_pct:.1f}% indicates healthy pricing.")
        elif margin_pct >= 20:
            insights.append(f"Gross margin at {margin_pct:.1f}% - within target range.")
        else:
            insights.append(f"Gross margin of {margin_pct:.1f}% below 20% target - review needed.")

        # Category insight from allowed view
        categories = self._get_category_performance(3)
        if categories:
            top_cats = [c['category_name'] for c in categories[:3]]
            insights.append(f"Revenue led by: {', '.join(top_cats)}.")

        return insights

    def _identify_risks(self, date_from: str, date_to: str) -> list:
        """Identify risks from allowed views only."""
        risks = []

        # Regional concentration from allowed view
        regions = self._get_regional_performance()
        if regions:
            total_rev = sum(r.get('net_revenue', 0) for r in regions)
            if total_rev > 0:
                top_region_share = (regions[0].get('net_revenue', 0) / total_rev) * 100
                if top_region_share > 40:
                    risks.append(
                        f"Geographic concentration: {regions[0]['region']} region "
                        f"represents {top_region_share:.1f}% of revenue."
                    )

        # SSSG trend risk
        sssg = self._get_sssg()
        if sssg and len(sssg) >= 2:
            latest_sssg = sssg[0].get('sssg_pct', 0)
            if latest_sssg and latest_sssg < 0:
                risks.append(f"Same-store sales declining: {latest_sssg:.1f}% in latest period.")

        if not risks:
            risks.append("No critical strategic risks identified from available data.")

        return risks

    def _generate_recommendations(self, margin_data: dict) -> list:
        """Generate recommendations based on allowed view data."""
        recommendations = []

        margin_pct = margin_data.get('margin_pct', 0)

        if margin_pct < 25:
            recommendations.append(Recommendation(
                action="Review pricing strategy to improve margin toward 25% target",
                impact=f"Target margin improvement from {margin_pct:.1f}% to 25%",
                priority="High" if margin_pct < 20 else "Medium"
            ))

        recommendations.append(Recommendation(
            action="Expand high-performing categories to underperforming regions",
            impact="Balance regional revenue concentration and drive growth",
            priority="Medium"
        ))

        recommendations.append(Recommendation(
            action="Monitor inventory days and optimize stock levels",
            impact="Improve cash flow and reduce carrying costs",
            priority="Medium"
        ))

        return recommendations


# CLI interface
if __name__ == "__main__":
    import sys

    agent = CEOAgentV2()
    date_from = sys.argv[1] if len(sys.argv) > 1 else None
    date_to = sys.argv[2] if len(sys.argv) > 2 else None

    print(agent.run(date_from, date_to))
