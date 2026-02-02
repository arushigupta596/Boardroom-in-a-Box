"""
CMO Agent
=========
Chief Marketing Officer - Focus on sales performance, promotions, customer segments, and growth.
"""

from typing import Optional
from .base_agent import BaseAgent, DatabaseConnection
from .contract import (
    AgentOutput, AgentRole, KPI, Recommendation, Evidence,
    Trend, Confidence
)


class CMOAgent(BaseAgent):
    """
    CMO Agent analyzes:
    - Sales performance by category and store
    - Promotion effectiveness
    - Customer segment performance
    - Growth opportunities
    - Market trends
    """

    @property
    def role(self) -> AgentRole:
        return AgentRole.CMO

    def analyze(self, date_from: str = None, date_to: str = None) -> AgentOutput:
        """Perform CMO analysis on marketing and sales metrics."""

        # Get date range if not specified
        if not date_from or not date_to:
            date_from, date_to = self.get_date_range()

        filters = f"sale_date between '{date_from}' and '{date_to}'"
        window = f"{date_from} to {date_to}"

        # Calculate KPIs
        kpis = []

        # 1. Total Units Sold
        sales_data = self._get_sales_metrics(date_from, date_to)
        kpis.append(KPI(
            name="Units Sold",
            value=int(sales_data['total_units']),
            unit="units",
            trend=Trend.UP,
            window=window
        ))

        # 2. Average Transaction Value
        kpis.append(KPI(
            name="Avg Transaction Value",
            value=round(sales_data['avg_txn_value'], 2),
            unit="$",
            trend=self._calculate_atv_trend(date_from, date_to),
            window=window
        ))

        # 3. Promotion Performance
        promo_data = self._get_promotion_metrics(date_from, date_to)
        kpis.append(KPI(
            name="Active Promotions",
            value=promo_data['active_promos'],
            unit="count",
            trend=Trend.FLAT,
            window=window
        ))

        # 4. Top Category Growth
        category_data = self._get_category_performance(date_from, date_to)
        if category_data:
            top_category = category_data[0]
            kpis.append(KPI(
                name=f"Top Category ({top_category['category_name']})",
                value=round(top_category['revenue'], 2),
                unit="$",
                trend=Trend.UP,
                window=window
            ))

        # Generate insights
        insights = self._generate_insights(sales_data, promo_data, category_data)

        # Identify risks
        risks = self._identify_risks(sales_data, category_data)

        # Generate recommendations
        recommendations = self._generate_recommendations(sales_data, promo_data, category_data)

        return AgentOutput(
            agent=self.role,
            kpis=kpis,
            insights=insights[:3],
            risks=risks[:3],
            recommendations=recommendations[:3],
            evidence=self._evidence,
            confidence=Confidence.HIGH if sales_data['total_units'] > 0 else Confidence.LOW
        )

    def _get_sales_metrics(self, date_from: str, date_to: str) -> dict:
        """Calculate overall sales metrics."""
        query = """
        SELECT
            SUM(units_sold) as total_units,
            SUM(gross_revenue) as gross_revenue,
            SUM(net_revenue) as net_revenue,
            COUNT(DISTINCT sale_date) as trading_days,
            COUNT(DISTINCT store_id) as active_stores
        FROM retail.v_sales_daily_store_category
        WHERE sale_date BETWEEN %s AND %s
        """
        self._add_evidence(
            "retail.v_sales_daily_store_category",
            f"sale_date between '{date_from}' and '{date_to}'"
        )
        result = self.db.execute_query(query, (date_from, date_to))
        data = result[0] if result else {}

        # Get average transaction value
        atv_query = """
        SELECT
            AVG(total_amount) as avg_txn_value,
            COUNT(DISTINCT txn_id) as total_transactions
        FROM retail.pos_transaction
        WHERE txn_ts::date BETWEEN %s AND %s
        """
        self._add_evidence(
            "retail.pos_transaction",
            f"txn_ts between '{date_from}' and '{date_to}'"
        )
        atv_result = self.db.execute_query(atv_query, (date_from, date_to))
        if atv_result:
            data.update(atv_result[0])

        return {
            'total_units': data.get('total_units', 0) or 0,
            'gross_revenue': data.get('gross_revenue', 0) or 0,
            'net_revenue': data.get('net_revenue', 0) or 0,
            'trading_days': data.get('trading_days', 0) or 0,
            'active_stores': data.get('active_stores', 0) or 0,
            'avg_txn_value': data.get('avg_txn_value', 0) or 0,
            'total_transactions': data.get('total_transactions', 0) or 0
        }

    def _get_promotion_metrics(self, date_from: str, date_to: str) -> dict:
        """Calculate promotion metrics."""
        query = """
        SELECT
            COUNT(DISTINCT p.promo_id) as active_promos,
            COUNT(DISTINCT ps.sku_id) as promoted_skus,
            SUM(ps.discount_value) as total_discount_value
        FROM retail.promotion p
        JOIN retail.promotion_sku ps ON ps.promo_id = p.promo_id
        WHERE p.start_date <= %s AND p.end_date >= %s
        """
        self._add_evidence(
            "retail.promotion + retail.promotion_sku",
            f"promotion period overlapping '{date_from}' to '{date_to}'"
        )
        result = self.db.execute_query(query, (date_to, date_from))
        return {
            'active_promos': result[0].get('active_promos', 0) or 0 if result else 0,
            'promoted_skus': result[0].get('promoted_skus', 0) or 0 if result else 0,
            'total_discount_value': result[0].get('total_discount_value', 0) or 0 if result else 0
        }

    def _get_category_performance(self, date_from: str, date_to: str) -> list:
        """Get sales performance by category."""
        query = """
        SELECT
            category_name,
            SUM(units_sold) as units,
            SUM(gross_revenue) as revenue,
            SUM(net_revenue) as net_revenue
        FROM retail.v_sales_daily_store_category
        WHERE sale_date BETWEEN %s AND %s
        GROUP BY category_name
        ORDER BY revenue DESC
        """
        self._add_evidence(
            "retail.v_sales_daily_store_category",
            f"sale_date between '{date_from}' and '{date_to}', grouped by category"
        )
        return self.db.execute_query(query, (date_from, date_to))

    def _get_store_performance(self, date_from: str, date_to: str) -> list:
        """Get sales performance by store."""
        query = """
        SELECT
            s.store_id,
            s.name as store_name,
            s.city,
            s.region,
            SUM(v.units_sold) as units,
            SUM(v.gross_revenue) as revenue
        FROM retail.v_sales_daily_store_category v
        JOIN retail.dim_store s ON s.store_id = v.store_id
        WHERE v.sale_date BETWEEN %s AND %s
        GROUP BY s.store_id, s.name, s.city, s.region
        ORDER BY revenue DESC
        LIMIT 10
        """
        self._add_evidence(
            "retail.v_sales_daily_store_category + retail.dim_store",
            f"sale_date between '{date_from}' and '{date_to}', top 10 stores"
        )
        return self.db.execute_query(query, (date_from, date_to))

    def _get_customer_segment_metrics(self, date_from: str, date_to: str) -> list:
        """Get metrics by customer segment."""
        query = """
        SELECT
            c.segment,
            COUNT(DISTINCT pt.txn_id) as transactions,
            SUM(pt.total_amount) as revenue,
            AVG(pt.total_amount) as avg_basket
        FROM retail.pos_transaction pt
        JOIN retail.customer c ON c.customer_id = pt.customer_id
        WHERE pt.txn_ts::date BETWEEN %s AND %s
        GROUP BY c.segment
        ORDER BY revenue DESC
        """
        self._add_evidence(
            "retail.pos_transaction + retail.customer",
            f"txn_ts between '{date_from}' and '{date_to}', by segment"
        )
        return self.db.execute_query(query, (date_from, date_to))

    def _calculate_atv_trend(self, date_from: str, date_to: str) -> Trend:
        """Calculate average transaction value trend."""
        query = """
        WITH monthly AS (
            SELECT
                DATE_TRUNC('month', txn_ts) as month,
                AVG(total_amount) as avg_txn
            FROM retail.pos_transaction
            WHERE txn_ts::date BETWEEN %s AND %s
            GROUP BY DATE_TRUNC('month', txn_ts)
            ORDER BY month
        )
        SELECT
            (SELECT avg_txn FROM monthly ORDER BY month LIMIT 1) as first_month,
            (SELECT avg_txn FROM monthly ORDER BY month DESC LIMIT 1) as last_month
        """
        result = self.db.execute_query(query, (date_from, date_to))
        if result and result[0]['first_month'] and result[0]['last_month']:
            return self._calculate_trend(result[0]['last_month'], result[0]['first_month'])
        return Trend.FLAT

    def _generate_insights(self, sales_data: dict, promo_data: dict, category_data: list) -> list:
        """Generate CMO insights from the data."""
        insights = []

        # Sales volume insight
        total_units = sales_data.get('total_units', 0)
        total_txns = sales_data.get('total_transactions', 0)
        insights.append(
            f"Sold {total_units:,} units across {total_txns:,} transactions "
            f"from {sales_data.get('active_stores', 0)} stores."
        )

        # Average transaction insight
        avg_txn = sales_data.get('avg_txn_value', 0)
        insights.append(
            f"Average transaction value is ${avg_txn:.2f}."
        )

        # Top categories insight
        if category_data and len(category_data) >= 3:
            top_3 = [c['category_name'] for c in category_data[:3]]
            insights.append(
                f"Top performing categories: {', '.join(top_3)}."
            )

        return insights

    def _identify_risks(self, sales_data: dict, category_data: list) -> list:
        """Identify marketing/sales risks."""
        risks = []

        # Check for concentration risk
        if category_data:
            total_revenue = sum(c.get('revenue', 0) for c in category_data)
            top_category_share = (category_data[0].get('revenue', 0) / max(total_revenue, 1)) * 100
            if top_category_share > 30:
                risks.append(
                    f"Revenue concentration: {category_data[0]['category_name']} "
                    f"represents {top_category_share:.1f}% of total sales."
                )

        # Check transaction count
        trading_days = sales_data.get('trading_days', 0)
        total_txns = sales_data.get('total_transactions', 0)
        if trading_days > 0:
            daily_txns = total_txns / trading_days
            if daily_txns < 100:
                risks.append(
                    f"Low transaction volume: {daily_txns:.0f} daily average."
                )

        if not risks:
            risks.append("No critical sales risks identified.")

        return risks

    def _generate_recommendations(self, sales_data: dict, promo_data: dict, category_data: list) -> list:
        """Generate CMO recommendations."""
        recommendations = []

        # Promotion recommendation
        active_promos = promo_data.get('active_promos', 0)
        if active_promos < 3:
            recommendations.append(Recommendation(
                action="Launch targeted promotions in underperforming categories",
                impact="Increase sales velocity by 10-15%",
                priority="High"
            ))

        # Category focus recommendation
        if category_data and len(category_data) > 5:
            bottom_categories = category_data[-3:]
            recommendations.append(Recommendation(
                action=f"Review merchandising for {', '.join([c['category_name'] for c in bottom_categories])}",
                impact="Rebalance category mix and improve overall basket",
                priority="Medium"
            ))

        # ATV improvement
        avg_txn = sales_data.get('avg_txn_value', 0)
        recommendations.append(Recommendation(
            action="Implement cross-sell suggestions at checkout",
            impact=f"Target ATV increase from ${avg_txn:.2f} to ${avg_txn*1.1:.2f}",
            priority="Medium"
        ))

        return recommendations


# CLI interface
if __name__ == "__main__":
    import sys

    agent = CMOAgent()
    date_from = sys.argv[1] if len(sys.argv) > 1 else None
    date_to = sys.argv[2] if len(sys.argv) > 2 else None

    print(agent.run(date_from, date_to))
