"""
CEO Agent
=========
Chief Executive Officer - Focus on strategic overview, cross-functional synthesis, and executive summary.
"""

from typing import Optional, List
from .base_agent import BaseAgent, DatabaseConnection
from .contract import (
    AgentOutput, AgentRole, KPI, Recommendation, Evidence,
    Trend, Confidence
)


class CEOAgent(BaseAgent):
    """
    CEO Agent provides:
    - Executive summary across all functions
    - Strategic KPIs (revenue, margin, growth)
    - Cross-functional risk synthesis
    - Strategic recommendations
    - Board-ready insights
    """

    @property
    def role(self) -> AgentRole:
        return AgentRole.CEO

    def analyze(self, date_from: str = None, date_to: str = None) -> AgentOutput:
        """Perform CEO-level strategic analysis."""

        # Get date range if not specified
        if not date_from or not date_to:
            date_from, date_to = self.get_date_range()

        window = f"{date_from} to {date_to}"

        # Calculate strategic KPIs
        kpis = []

        # 1. Net Revenue (primary metric)
        board_summary = self._get_board_summary()
        kpis.append(KPI(
            name="Net Revenue",
            value=round(board_summary['net_revenue'], 2),
            unit="$",
            trend=Trend.UP,
            window=window
        ))

        # 2. Gross Margin %
        margin_data = self._get_margin_summary(date_from, date_to)
        kpis.append(KPI(
            name="Gross Margin",
            value=round(margin_data['margin_pct'], 1),
            unit="%",
            trend=self._get_margin_trend(date_from, date_to),
            window=window
        ))

        # 3. Units Sold (volume indicator)
        kpis.append(KPI(
            name="Units Sold",
            value=int(board_summary['units_sold']),
            unit="units",
            trend=Trend.UP,
            window=window
        ))

        # 4. Store Performance
        store_data = self._get_store_performance_summary(date_from, date_to)
        kpis.append(KPI(
            name="Avg Revenue/Store",
            value=round(store_data['avg_revenue_per_store'], 2),
            unit="$",
            trend=Trend.FLAT,
            window=window
        ))

        # Generate strategic insights
        insights = self._generate_strategic_insights(
            board_summary, margin_data, store_data, date_from, date_to
        )

        # Synthesize cross-functional risks
        risks = self._synthesize_risks(margin_data, store_data, date_from, date_to)

        # Generate strategic recommendations
        recommendations = self._generate_strategic_recommendations(
            margin_data, store_data
        )

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
        """Get high-level board summary metrics."""
        query = """
        SELECT
            period_start,
            period_end,
            net_revenue,
            units_sold
        FROM retail.v_board_summary
        """
        self._add_evidence("retail.v_board_summary", "executive summary metrics")
        result = self.db.execute_query(query)
        if result:
            return {
                'period_start': result[0]['period_start'],
                'period_end': result[0]['period_end'],
                'net_revenue': result[0]['net_revenue'] or 0,
                'units_sold': result[0]['units_sold'] or 0
            }
        return {'net_revenue': 0, 'units_sold': 0}

    def _get_margin_summary(self, date_from: str, date_to: str) -> dict:
        """Get margin summary for executive view."""
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
        if result:
            return {
                'total_revenue': result[0]['total_revenue'] or 0,
                'total_cogs': result[0]['total_cogs'] or 0,
                'total_margin': result[0]['total_margin'] or 0,
                'margin_pct': result[0]['margin_pct'] or 0
            }
        return {'total_revenue': 0, 'total_cogs': 0, 'total_margin': 0, 'margin_pct': 0}

    def _get_margin_trend(self, date_from: str, date_to: str) -> Trend:
        """Calculate margin trend over the period."""
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

    def _get_store_performance_summary(self, date_from: str, date_to: str) -> dict:
        """Get store performance summary."""
        query = """
        SELECT
            COUNT(DISTINCT store_id) as active_stores,
            SUM(net_revenue) as total_revenue,
            SUM(net_revenue) / NULLIF(COUNT(DISTINCT store_id), 0) as avg_revenue_per_store,
            SUM(units_sold) as total_units
        FROM retail.v_sales_daily_store_category
        WHERE sale_date BETWEEN %s AND %s
        """
        self._add_evidence(
            "retail.v_sales_daily_store_category",
            f"sale_date between '{date_from}' and '{date_to}'"
        )
        result = self.db.execute_query(query, (date_from, date_to))
        if result:
            return {
                'active_stores': result[0]['active_stores'] or 0,
                'total_revenue': result[0]['total_revenue'] or 0,
                'avg_revenue_per_store': result[0]['avg_revenue_per_store'] or 0,
                'total_units': result[0]['total_units'] or 0
            }
        return {'active_stores': 0, 'total_revenue': 0, 'avg_revenue_per_store': 0, 'total_units': 0}

    def _get_top_categories(self, date_from: str, date_to: str, limit: int = 3) -> list:
        """Get top performing categories."""
        query = """
        SELECT
            category_name,
            SUM(net_revenue) as revenue,
            SUM(units_sold) as units
        FROM retail.v_sales_daily_store_category
        WHERE sale_date BETWEEN %s AND %s
        GROUP BY category_name
        ORDER BY revenue DESC
        LIMIT %s
        """
        self._add_evidence(
            "retail.v_sales_daily_store_category",
            f"top {limit} categories by revenue"
        )
        return self.db.execute_query(query, (date_from, date_to, limit))

    def _get_regional_performance(self, date_from: str, date_to: str) -> list:
        """Get performance by region."""
        query = """
        SELECT
            s.region,
            COUNT(DISTINCT s.store_id) as stores,
            SUM(v.net_revenue) as revenue,
            SUM(v.units_sold) as units
        FROM retail.v_sales_daily_store_category v
        JOIN retail.dim_store s ON s.store_id = v.store_id
        WHERE v.sale_date BETWEEN %s AND %s
        GROUP BY s.region
        ORDER BY revenue DESC
        """
        self._add_evidence(
            "retail.v_sales_daily_store_category + retail.dim_store",
            f"regional performance"
        )
        return self.db.execute_query(query, (date_from, date_to))

    def _generate_strategic_insights(
        self,
        board_summary: dict,
        margin_data: dict,
        store_data: dict,
        date_from: str,
        date_to: str
    ) -> list:
        """Generate CEO-level strategic insights."""
        insights = []

        # Revenue and volume headline
        revenue = board_summary.get('net_revenue', 0)
        units = board_summary.get('units_sold', 0)
        insights.append(
            f"Total revenue of ${revenue:,.0f} from {units:,} units sold "
            f"across {store_data.get('active_stores', 0)} stores."
        )

        # Margin insight
        margin_pct = margin_data.get('margin_pct', 0)
        if margin_pct >= 20:
            insights.append(
                f"Healthy gross margin of {margin_pct:.1f}% indicates strong pricing power."
            )
        else:
            insights.append(
                f"Gross margin at {margin_pct:.1f}% - below 20% target requires attention."
            )

        # Top categories
        top_categories = self._get_top_categories(date_from, date_to)
        if top_categories:
            cat_names = [c['category_name'] for c in top_categories[:3]]
            insights.append(
                f"Revenue led by: {', '.join(cat_names)}."
            )

        return insights

    def _synthesize_risks(
        self,
        margin_data: dict,
        store_data: dict,
        date_from: str,
        date_to: str
    ) -> list:
        """Synthesize cross-functional risks for CEO view."""
        risks = []

        # Margin risk
        margin_pct = margin_data.get('margin_pct', 0)
        if margin_pct < 18:
            risks.append(
                f"MARGIN ALERT: Gross margin at {margin_pct:.1f}% threatens profitability."
            )
        elif margin_pct < 20:
            risks.append(
                f"Margin pressure: {margin_pct:.1f}% approaching minimum threshold."
            )

        # Store concentration risk
        regions = self._get_regional_performance(date_from, date_to)
        if regions:
            total_revenue = sum(r.get('revenue', 0) for r in regions)
            top_region_share = (regions[0].get('revenue', 0) / max(total_revenue, 1)) * 100
            if top_region_share > 40:
                risks.append(
                    f"Geographic concentration: {regions[0]['region']} region "
                    f"represents {top_region_share:.1f}% of revenue."
                )

        # Return risk (quality indicator)
        return_data = self._get_return_summary(date_from, date_to)
        if return_data.get('return_rate', 0) > 5:
            risks.append(
                f"Return rate at {return_data['return_rate']:.1f}% may indicate quality issues."
            )

        if not risks:
            risks.append("Business fundamentals healthy. No critical strategic risks.")

        return risks

    def _get_return_summary(self, date_from: str, date_to: str) -> dict:
        """Get return summary for quality assessment."""
        query = """
        WITH sales AS (
            SELECT SUM(qty) as total_sold FROM retail.fact_sales_line
            WHERE sale_date BETWEEN %s AND %s
        ),
        returns AS (
            SELECT SUM(qty) as total_returned FROM retail.fact_returns_line
            WHERE return_date BETWEEN %s AND %s
        )
        SELECT
            COALESCE(r.total_returned, 0) as total_returned,
            COALESCE(s.total_sold, 0) as total_sold,
            CASE
                WHEN COALESCE(s.total_sold, 0) > 0
                THEN (COALESCE(r.total_returned, 0)::float / s.total_sold * 100)
                ELSE 0
            END as return_rate
        FROM sales s, returns r
        """
        self._add_evidence(
            "retail.fact_sales_line + retail.fact_returns_line",
            f"return rate calculation"
        )
        result = self.db.execute_query(query, (date_from, date_to, date_from, date_to))
        if result:
            return {
                'total_returned': result[0]['total_returned'] or 0,
                'total_sold': result[0]['total_sold'] or 0,
                'return_rate': result[0]['return_rate'] or 0
            }
        return {'return_rate': 0}

    def _generate_strategic_recommendations(
        self,
        margin_data: dict,
        store_data: dict
    ) -> list:
        """Generate CEO-level strategic recommendations."""
        recommendations = []

        margin_pct = margin_data.get('margin_pct', 0)

        # Margin improvement
        if margin_pct < 20:
            recommendations.append(Recommendation(
                action="Launch margin improvement initiative across low-performing categories",
                impact=f"Target margin increase from {margin_pct:.1f}% to 22%",
                priority="High"
            ))

        # Growth recommendation
        avg_revenue = store_data.get('avg_revenue_per_store', 0)
        recommendations.append(Recommendation(
            action="Expand high-performing store format to new markets",
            impact=f"Potential revenue uplift of ${avg_revenue*0.1:,.0f} per new store",
            priority="Medium"
        ))

        # Operational excellence
        recommendations.append(Recommendation(
            action="Implement unified inventory optimization across all DCs",
            impact="Reduce stockouts by 15% and improve customer satisfaction",
            priority="Medium"
        ))

        return recommendations


# CLI interface
if __name__ == "__main__":
    import sys

    agent = CEOAgent()
    date_from = sys.argv[1] if len(sys.argv) > 1 else None
    date_to = sys.argv[2] if len(sys.argv) > 2 else None

    print(agent.run(date_from, date_to))
