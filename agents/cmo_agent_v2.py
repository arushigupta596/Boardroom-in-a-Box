"""
CMO Agent v2
============
Chief Marketing Officer - Uses ONLY allowed views from cmo_views schema.
NO access to individual customer data or raw transaction tables.
"""

from typing import Optional
from .base_agent import BaseAgent, DatabaseConnection, GuardrailedDatabaseConnection
from .contract import (
    AgentOutput, AgentRole, KPI, Recommendation, Evidence,
    Trend, Confidence
)


class CMOAgentV2(BaseAgent):
    """
    CMO Agent v2 - Scope-enforced version with SQL guardrails.

    ALLOWED DATA SURFACE (cmo_views schema only):
    - cmo_views.sales_demand_category
    - cmo_views.sales_demand_store
    - cmo_views.promo_coverage
    - cmo_views.promo_lift
    - cmo_views.basket_metrics
    - cmo_views.segment_performance
    - cmo_views.repeat_rate
    - cmo_views.category_mix_by_format
    - cmo_views.brand_performance

    DENIED:
    - retail.customer (no individual data)
    - retail.pos_transaction (use aggregated views)

    SECURITY:
    - SQL guardrails enforce schema/table allowlist
    - Max 4 JOINs, 5000 row limit, 5s timeout
    - Date filter required for sales/basket fact tables
    - DDL/DML operations blocked
    """

    # Enable guardrails for this agent
    ENABLE_GUARDRAILS = True

    ALLOWED_VIEWS = [
        'cmo_views.sales_demand_category',
        'cmo_views.sales_demand_store',
        'cmo_views.promo_coverage',
        'cmo_views.promo_lift',
        'cmo_views.basket_metrics',
        'cmo_views.segment_performance',
        'cmo_views.repeat_rate',
        'cmo_views.category_mix_by_format',
        'cmo_views.brand_performance',
    ]

    def _get_role_name(self) -> str:
        """Return role name for guardrails initialization."""
        return "CMO"

    @property
    def role(self) -> AgentRole:
        return AgentRole.CMO

    def analyze(self, date_from: str = None, date_to: str = None) -> AgentOutput:
        """Perform CMO analysis using allowed views only."""

        # Get date range if not specified
        if not date_from or not date_to:
            date_from, date_to = self._get_date_range_from_sales()

        window = f"{date_from} to {date_to}"

        # Calculate KPIs from allowed views
        kpis = []

        # 1. Units Sold from sales demand
        sales_data = self._get_sales_summary(date_from, date_to)
        kpis.append(KPI(
            name="Units Sold",
            value=int(sales_data['units_sold']),
            unit="units",
            trend=Trend.UP,
            window=window
        ))

        # 2. Average Basket Value from basket metrics
        basket_data = self._get_basket_summary(date_from, date_to)
        kpis.append(KPI(
            name="Avg Basket Value",
            value=round(basket_data['avg_basket_value'], 2),
            unit="$",
            trend=self._get_basket_trend(date_from, date_to),
            window=window
        ))

        # 3. Active Promotions from promo coverage
        promo_data = self._get_promo_summary(date_from, date_to)
        kpis.append(KPI(
            name="Active Promotions",
            value=promo_data['promo_count'],
            unit="count",
            trend=Trend.FLAT,
            window=window
        ))

        # 4. Repeat Purchase Rate
        repeat_data = self._get_repeat_rate()
        kpis.append(KPI(
            name="Repeat Customers",
            value=round(repeat_data['repeat_pct'], 1),
            unit="%",
            trend=Trend.FLAT,
            window="All time"
        ))

        # Generate insights
        insights = self._generate_insights(sales_data, basket_data, promo_data)

        # Identify risks
        risks = self._identify_risks(sales_data, basket_data)

        # Generate recommendations
        recommendations = self._generate_recommendations(sales_data, basket_data, promo_data)

        return AgentOutput(
            agent=self.role,
            kpis=kpis,
            insights=insights[:3],
            risks=risks[:3],
            recommendations=recommendations[:3],
            evidence=self._evidence,
            confidence=Confidence.HIGH if sales_data['units_sold'] > 0 else Confidence.LOW
        )

    def _get_date_range_from_sales(self) -> tuple:
        """Get date range from sales demand view."""
        query = """
        SELECT MIN(sale_date) AS min_date, MAX(sale_date) AS max_date
        FROM cmo_views.sales_demand_category
        """
        result = self.db.execute_query(query)
        if result and result[0]['min_date']:
            return result[0]['min_date'], result[0]['max_date']
        return '2025-01-01', '2025-03-31'

    def _get_sales_summary(self, date_from: str, date_to: str) -> dict:
        """Get sales summary from cmo_views.sales_demand_category."""
        query = """
        SELECT
            SUM(units_sold) AS units_sold,
            SUM(gross_revenue) AS gross_revenue,
            SUM(net_revenue) AS net_revenue,
            COUNT(DISTINCT category_id) AS category_count
        FROM cmo_views.sales_demand_category
        WHERE sale_date BETWEEN %s AND %s
        """
        self._add_evidence("cmo_views.sales_demand_category", f"sale_date between '{date_from}' and '{date_to}'")
        result = self.db.execute_query(query, (date_from, date_to))
        if result:
            return {
                'units_sold': result[0].get('units_sold', 0) or 0,
                'gross_revenue': result[0].get('gross_revenue', 0) or 0,
                'net_revenue': result[0].get('net_revenue', 0) or 0,
                'category_count': result[0].get('category_count', 0) or 0
            }
        return {'units_sold': 0, 'gross_revenue': 0}

    def _get_basket_summary(self, date_from: str, date_to: str) -> dict:
        """Get basket metrics from cmo_views.basket_metrics."""
        query = """
        SELECT
            SUM(transaction_count) AS total_transactions,
            SUM(total_revenue) AS total_revenue,
            SUM(total_revenue) / NULLIF(SUM(transaction_count), 0) AS avg_basket_value,
            AVG(avg_items_per_basket) AS avg_items_per_basket
        FROM cmo_views.basket_metrics
        WHERE sale_date BETWEEN %s AND %s
        """
        self._add_evidence("cmo_views.basket_metrics", f"sale_date between '{date_from}' and '{date_to}'")
        result = self.db.execute_query(query, (date_from, date_to))
        if result:
            return {
                'total_transactions': result[0].get('total_transactions', 0) or 0,
                'total_revenue': result[0].get('total_revenue', 0) or 0,
                'avg_basket_value': result[0].get('avg_basket_value', 0) or 0,
                'avg_items_per_basket': result[0].get('avg_items_per_basket', 0) or 0
            }
        return {'avg_basket_value': 0, 'total_transactions': 0}

    def _get_basket_trend(self, date_from: str, date_to: str) -> Trend:
        """Calculate basket value trend."""
        query = """
        WITH monthly AS (
            SELECT
                DATE_TRUNC('month', sale_date) AS month,
                SUM(total_revenue) / NULLIF(SUM(transaction_count), 0) AS avg_basket
            FROM cmo_views.basket_metrics
            WHERE sale_date BETWEEN %s AND %s
            GROUP BY DATE_TRUNC('month', sale_date)
            ORDER BY month
        )
        SELECT
            (SELECT avg_basket FROM monthly ORDER BY month LIMIT 1) AS first_month,
            (SELECT avg_basket FROM monthly ORDER BY month DESC LIMIT 1) AS last_month
        """
        result = self.db.execute_query(query, (date_from, date_to))
        if result and result[0]['first_month'] and result[0]['last_month']:
            return self._calculate_trend(result[0]['last_month'], result[0]['first_month'])
        return Trend.FLAT

    def _get_promo_summary(self, date_from: str, date_to: str) -> dict:
        """Get promotion summary from cmo_views.promo_coverage."""
        query = """
        SELECT
            COUNT(*) AS promo_count,
            SUM(sku_count) AS total_sku_coverage,
            SUM(category_count) AS category_coverage
        FROM cmo_views.promo_coverage
        WHERE start_date <= %s AND end_date >= %s
        """
        self._add_evidence("cmo_views.promo_coverage", f"promotions active during '{date_from}' to '{date_to}'")
        result = self.db.execute_query(query, (date_to, date_from))
        if result:
            return {
                'promo_count': result[0].get('promo_count', 0) or 0,
                'total_sku_coverage': result[0].get('total_sku_coverage', 0) or 0,
                'category_coverage': result[0].get('category_coverage', 0) or 0
            }
        return {'promo_count': 0}

    def _get_repeat_rate(self) -> dict:
        """Get repeat purchase rate from cmo_views.repeat_rate."""
        query = """
        SELECT
            SUM(CASE WHEN customer_tier != 'One-time' THEN customer_count ELSE 0 END) AS repeat_customers,
            SUM(customer_count) AS total_customers,
            ROUND(
                SUM(CASE WHEN customer_tier != 'One-time' THEN customer_count ELSE 0 END)::numeric /
                NULLIF(SUM(customer_count), 0) * 100, 1
            ) AS repeat_pct
        FROM cmo_views.repeat_rate
        """
        self._add_evidence("cmo_views.repeat_rate", "customer repeat purchase tiers")
        result = self.db.execute_query(query)
        if result:
            return {
                'repeat_customers': result[0].get('repeat_customers', 0) or 0,
                'total_customers': result[0].get('total_customers', 0) or 0,
                'repeat_pct': result[0].get('repeat_pct', 0) or 0
            }
        return {'repeat_pct': 0}

    def _get_top_categories(self, date_from: str, date_to: str, limit: int = 5) -> list:
        """Get top categories from cmo_views.sales_demand_category."""
        query = """
        SELECT
            category_name,
            SUM(units_sold) AS units_sold,
            SUM(net_revenue) AS net_revenue
        FROM cmo_views.sales_demand_category
        WHERE sale_date BETWEEN %s AND %s
        GROUP BY category_name
        ORDER BY net_revenue DESC
        LIMIT %s
        """
        self._add_evidence("cmo_views.sales_demand_category", f"top {limit} categories")
        return self.db.execute_query(query, (date_from, date_to, limit))

    def _get_segment_performance(self) -> list:
        """Get segment performance from cmo_views.segment_performance."""
        query = "SELECT * FROM cmo_views.segment_performance ORDER BY total_revenue DESC"
        self._add_evidence("cmo_views.segment_performance", "customer segment aggregates")
        return self.db.execute_query(query)

    def _get_brand_performance(self, limit: int = 5) -> list:
        """Get brand performance from cmo_views.brand_performance."""
        query = f"SELECT * FROM cmo_views.brand_performance ORDER BY net_revenue DESC LIMIT {limit}"
        self._add_evidence("cmo_views.brand_performance", f"top {limit} brands")
        return self.db.execute_query(query)

    def _generate_insights(self, sales_data: dict, basket_data: dict, promo_data: dict) -> list:
        """Generate CMO insights from allowed views."""
        insights = []

        # Sales insight
        units = sales_data.get('units_sold', 0)
        txns = basket_data.get('total_transactions', 0)
        insights.append(
            f"Sold {units:,} units across {txns:,} transactions."
        )

        # Basket insight
        avg_basket = basket_data.get('avg_basket_value', 0)
        avg_items = basket_data.get('avg_items_per_basket', 0)
        insights.append(
            f"Average basket value ${avg_basket:.2f} with {avg_items:.1f} items per transaction."
        )

        # Segment insight
        segments = self._get_segment_performance()
        if segments:
            top_segment = segments[0]
            insights.append(
                f"Top segment: {top_segment['segment']} with ${top_segment['total_revenue']:,.0f} revenue."
            )

        return insights

    def _identify_risks(self, sales_data: dict, basket_data: dict) -> list:
        """Identify marketing risks from allowed views."""
        risks = []

        # Transaction volume
        txns = basket_data.get('total_transactions', 0)
        # Assuming 90 days in Q1
        if txns > 0:
            daily_txns = txns / 90
            if daily_txns < 80:
                risks.append(f"Low transaction volume: {daily_txns:.0f} daily average.")

        # One-time customer risk
        repeat_data = self._get_repeat_rate()
        one_time_pct = 100 - repeat_data.get('repeat_pct', 0)
        if one_time_pct > 60:
            risks.append(f"High one-time customer rate: {one_time_pct:.1f}% don't return.")

        if not risks:
            risks.append("Sales metrics within expected ranges.")

        return risks

    def _generate_recommendations(self, sales_data: dict, basket_data: dict,
                                  promo_data: dict) -> list:
        """Generate CMO recommendations from allowed view data."""
        recommendations = []

        # Basket improvement
        avg_basket = basket_data.get('avg_basket_value', 0)
        recommendations.append(Recommendation(
            action="Implement cross-sell recommendations at checkout",
            impact=f"Target basket increase from ${avg_basket:.2f} to ${avg_basket*1.1:.2f}",
            priority="High"
        ))

        # Promotion recommendation
        promo_count = promo_data.get('promo_count', 0)
        if promo_count < 5:
            recommendations.append(Recommendation(
                action="Expand promotional calendar with targeted category campaigns",
                impact="Increase traffic and conversion in underperforming categories",
                priority="Medium"
            ))

        # Repeat rate
        repeat_data = self._get_repeat_rate()
        if repeat_data.get('repeat_pct', 0) < 50:
            recommendations.append(Recommendation(
                action="Launch loyalty program to improve customer retention",
                impact=f"Target repeat rate improvement from {repeat_data['repeat_pct']:.1f}% to 50%",
                priority="High"
            ))

        return recommendations


# CLI interface
if __name__ == "__main__":
    import sys

    agent = CMOAgentV2()
    date_from = sys.argv[1] if len(sys.argv) > 1 else None
    date_to = sys.argv[2] if len(sys.argv) > 2 else None

    print(agent.run(date_from, date_to))
