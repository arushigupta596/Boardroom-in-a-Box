"""
CFO Agent
=========
Chief Financial Officer - Focus on margin, revenue, cost control, and financial health.
"""

from typing import Optional
from .base_agent import BaseAgent, DatabaseConnection
from .contract import (
    AgentOutput, AgentRole, KPI, Recommendation, Evidence,
    Trend, Confidence
)


class CFOAgent(BaseAgent):
    """
    CFO Agent analyzes:
    - Gross margin trends
    - Revenue performance
    - Cost of goods sold (COGS)
    - Discount impact on margins
    - Financial risks and opportunities
    """

    @property
    def role(self) -> AgentRole:
        return AgentRole.CFO

    def analyze(self, date_from: str = None, date_to: str = None) -> AgentOutput:
        """Perform CFO analysis on financial metrics."""

        # Get date range if not specified
        if not date_from or not date_to:
            date_from, date_to = self.get_date_range()

        filters = f"sale_date between '{date_from}' and '{date_to}'"
        window = f"{date_from} to {date_to}"

        # Calculate KPIs
        kpis = []

        # 1. Gross Margin %
        margin_data = self._get_margin_metrics(date_from, date_to)
        kpis.append(KPI(
            name="Gross Margin %",
            value=round(margin_data['margin_pct'], 1),
            unit="%",
            trend=self._calculate_margin_trend(date_from, date_to),
            window=window
        ))

        # 2. Net Revenue
        revenue_data = self._get_revenue_metrics(date_from, date_to)
        kpis.append(KPI(
            name="Net Revenue",
            value=round(revenue_data['net_revenue'], 2),
            unit="$",
            trend=Trend.UP,  # Would compare to previous period
            window=window
        ))

        # 3. COGS
        kpis.append(KPI(
            name="Total COGS",
            value=round(margin_data['total_cogs'], 2),
            unit="$",
            trend=Trend.UP,
            window=window
        ))

        # 4. Discount Rate
        discount_data = self._get_discount_metrics(date_from, date_to)
        kpis.append(KPI(
            name="Avg Discount Rate",
            value=round(discount_data['discount_rate'], 1),
            unit="%",
            trend=Trend.UP if discount_data['discount_rate'] > 5 else Trend.FLAT,
            window=window
        ))

        # Generate insights
        insights = self._generate_insights(margin_data, revenue_data, discount_data)

        # Identify risks
        risks = self._identify_risks(margin_data, discount_data)

        # Generate recommendations
        recommendations = self._generate_recommendations(margin_data, discount_data)

        return AgentOutput(
            agent=self.role,
            kpis=kpis,
            insights=insights[:3],
            risks=risks[:3],
            recommendations=recommendations[:3],
            evidence=self._evidence,
            confidence=Confidence.HIGH if margin_data['total_revenue'] > 0 else Confidence.LOW
        )

    def _get_margin_metrics(self, date_from: str, date_to: str) -> dict:
        """Calculate margin metrics from the margin view."""
        query = """
        SELECT
            SUM(gross_revenue) as total_revenue,
            SUM(cogs) as total_cogs,
            SUM(gross_margin) as total_margin,
            CASE
                WHEN SUM(gross_revenue) > 0
                THEN (SUM(gross_margin) / SUM(gross_revenue) * 100)
                ELSE 0
            END as margin_pct
        FROM retail.v_margin_daily_store_sku
        WHERE sale_date BETWEEN %s AND %s
        """
        self._add_evidence(
            "retail.v_margin_daily_store_sku",
            f"sale_date between '{date_from}' and '{date_to}'"
        )
        result = self.db.execute_query(query, (date_from, date_to))
        return result[0] if result else {
            'total_revenue': 0, 'total_cogs': 0, 'total_margin': 0, 'margin_pct': 0
        }

    def _get_revenue_metrics(self, date_from: str, date_to: str) -> dict:
        """Calculate revenue metrics."""
        query = """
        SELECT
            SUM(gross_revenue) as gross_revenue,
            SUM(discount) as total_discount,
            SUM(net_revenue) as net_revenue,
            SUM(units_sold) as total_units
        FROM retail.v_sales_daily_store_category
        WHERE sale_date BETWEEN %s AND %s
        """
        self._add_evidence(
            "retail.v_sales_daily_store_category",
            f"sale_date between '{date_from}' and '{date_to}'"
        )
        result = self.db.execute_query(query, (date_from, date_to))
        return result[0] if result else {
            'gross_revenue': 0, 'total_discount': 0, 'net_revenue': 0, 'total_units': 0
        }

    def _get_discount_metrics(self, date_from: str, date_to: str) -> dict:
        """Calculate discount metrics."""
        query = """
        SELECT
            SUM(discount) as total_discount,
            SUM(gross_revenue) as gross_revenue,
            CASE
                WHEN SUM(gross_revenue) > 0
                THEN (SUM(discount) / SUM(gross_revenue) * 100)
                ELSE 0
            END as discount_rate
        FROM retail.v_sales_daily_store_category
        WHERE sale_date BETWEEN %s AND %s
        """
        result = self.db.execute_query(query, (date_from, date_to))
        return result[0] if result else {
            'total_discount': 0, 'gross_revenue': 0, 'discount_rate': 0
        }

    def _get_category_margin_breakdown(self, date_from: str, date_to: str) -> list:
        """Get margin breakdown by category."""
        query = """
        SELECT
            d.category_name,
            SUM(m.gross_revenue) as revenue,
            SUM(m.gross_margin) as margin,
            CASE
                WHEN SUM(m.gross_revenue) > 0
                THEN (SUM(m.gross_margin) / SUM(m.gross_revenue) * 100)
                ELSE 0
            END as margin_pct
        FROM retail.v_margin_daily_store_sku m
        JOIN retail.dim_product d ON d.sku_id = m.sku_id
        WHERE m.sale_date BETWEEN %s AND %s
        GROUP BY d.category_name
        ORDER BY margin_pct ASC
        LIMIT 5
        """
        self._add_evidence(
            "retail.v_margin_daily_store_sku + retail.dim_product",
            f"sale_date between '{date_from}' and '{date_to}'"
        )
        return self.db.execute_query(query, (date_from, date_to))

    def _calculate_margin_trend(self, date_from: str, date_to: str) -> Trend:
        """Calculate margin trend by comparing first and last month."""
        query = """
        WITH monthly AS (
            SELECT
                DATE_TRUNC('month', sale_date) as month,
                SUM(gross_revenue) as revenue,
                SUM(gross_margin) as margin
            FROM retail.v_margin_daily_store_sku
            WHERE sale_date BETWEEN %s AND %s
            GROUP BY DATE_TRUNC('month', sale_date)
            ORDER BY month
        )
        SELECT
            (SELECT margin/NULLIF(revenue,0)*100 FROM monthly ORDER BY month LIMIT 1) as first_month,
            (SELECT margin/NULLIF(revenue,0)*100 FROM monthly ORDER BY month DESC LIMIT 1) as last_month
        """
        result = self.db.execute_query(query, (date_from, date_to))
        if result and result[0]['first_month'] and result[0]['last_month']:
            return self._calculate_trend(result[0]['last_month'], result[0]['first_month'])
        return Trend.FLAT

    def _generate_insights(self, margin_data: dict, revenue_data: dict, discount_data: dict) -> list:
        """Generate CFO insights from the data."""
        insights = []

        # Margin insight
        margin_pct = margin_data.get('margin_pct', 0)
        if margin_pct > 0:
            insights.append(
                f"Gross margin stands at {margin_pct:.1f}%, "
                f"with total revenue of ${revenue_data.get('net_revenue', 0):,.0f}."
            )

        # Discount insight
        discount_rate = discount_data.get('discount_rate', 0)
        if discount_rate > 5:
            insights.append(
                f"Discount rate of {discount_rate:.1f}% is impacting gross margins. "
                f"Total discounts: ${discount_data.get('total_discount', 0):,.0f}."
            )
        else:
            insights.append(
                f"Discount rate is controlled at {discount_rate:.1f}%."
            )

        # COGS insight
        cogs_pct = (margin_data.get('total_cogs', 0) / max(margin_data.get('total_revenue', 1), 1)) * 100
        insights.append(
            f"COGS represents {cogs_pct:.1f}% of revenue."
        )

        return insights

    def _identify_risks(self, margin_data: dict, discount_data: dict) -> list:
        """Identify financial risks."""
        risks = []

        margin_pct = margin_data.get('margin_pct', 0)
        if margin_pct < 20:
            risks.append(
                f"Margin at {margin_pct:.1f}% is below typical retail target of 20-25%."
            )

        if margin_pct < 18:
            risks.append(
                "Margin is approaching critical floor. Immediate action recommended."
            )

        discount_rate = discount_data.get('discount_rate', 0)
        if discount_rate > 10:
            risks.append(
                f"High discount rate ({discount_rate:.1f}%) eroding profitability."
            )

        if not risks:
            risks.append("No critical financial risks identified.")

        return risks

    def _generate_recommendations(self, margin_data: dict, discount_data: dict) -> list:
        """Generate CFO recommendations."""
        recommendations = []

        margin_pct = margin_data.get('margin_pct', 0)
        discount_rate = discount_data.get('discount_rate', 0)

        if margin_pct < 20:
            recommendations.append(Recommendation(
                action="Review pricing strategy for low-margin categories",
                impact=f"Target margin improvement of {20 - margin_pct:.1f}pp",
                priority="High"
            ))

        if discount_rate > 8:
            recommendations.append(Recommendation(
                action=f"Cap promotional discounts at 10% for standard SKUs",
                impact="Protect margin floor while maintaining competitiveness",
                priority="High"
            ))

        recommendations.append(Recommendation(
            action="Analyze supplier costs for top-volume SKUs",
            impact="Potential COGS reduction of 2-5% through renegotiation",
            priority="Medium"
        ))

        return recommendations


# CLI interface
if __name__ == "__main__":
    import sys

    agent = CFOAgent()
    date_from = sys.argv[1] if len(sys.argv) > 1 else None
    date_to = sys.argv[2] if len(sys.argv) > 2 else None

    print(agent.run(date_from, date_to))
