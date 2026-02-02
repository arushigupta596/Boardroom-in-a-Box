"""
CIO Agent
=========
Chief Information Officer - Focus on data health, system integrity, and operational metrics.
"""

from typing import Optional
from .base_agent import BaseAgent, DatabaseConnection
from .contract import (
    AgentOutput, AgentRole, KPI, Recommendation, Evidence,
    Trend, Confidence
)


class CIOAgent(BaseAgent):
    """
    CIO Agent analyzes:
    - Data quality and health
    - System integrity metrics
    - Inventory data accuracy
    - Supply chain data flow
    - Data freshness and completeness
    """

    @property
    def role(self) -> AgentRole:
        return AgentRole.CIO

    def analyze(self, date_from: str = None, date_to: str = None) -> AgentOutput:
        """Perform CIO analysis on data health and system metrics."""

        # Get date range if not specified
        if not date_from or not date_to:
            date_from, date_to = self.get_date_range()

        window = f"{date_from} to {date_to}"

        # Calculate KPIs
        kpis = []

        # 1. Data Health Score
        health_data = self._get_health_check_results()
        health_score = self._calculate_health_score(health_data)
        kpis.append(KPI(
            name="Data Health Score",
            value=health_score,
            unit="%",
            trend=Trend.UP if health_score >= 90 else Trend.FLAT,
            window="Current"
        ))

        # 2. Record Count
        record_counts = self._get_record_counts()
        total_records = sum(record_counts.values())
        kpis.append(KPI(
            name="Total Records",
            value=total_records,
            unit="records",
            trend=Trend.FLAT,
            window="Current"
        ))

        # 3. Inventory Coverage
        inventory_data = self._get_inventory_coverage()
        kpis.append(KPI(
            name="Inventory Coverage",
            value=round(inventory_data['coverage_pct'], 1),
            unit="%",
            trend=Trend.FLAT,
            window="Current"
        ))

        # 4. Data Freshness (days since last transaction)
        freshness = self._get_data_freshness()
        kpis.append(KPI(
            name="Data Freshness",
            value=freshness['days_since_last_txn'],
            unit="days",
            trend=Trend.DOWN if freshness['days_since_last_txn'] > 7 else Trend.UP,
            window="Current"
        ))

        # Generate insights
        insights = self._generate_insights(health_data, record_counts, inventory_data)

        # Identify risks
        risks = self._identify_risks(health_data, freshness)

        # Generate recommendations
        recommendations = self._generate_recommendations(health_data, inventory_data)

        # Determine confidence based on health score
        if health_score >= 90:
            confidence = Confidence.HIGH
        elif health_score >= 70:
            confidence = Confidence.MEDIUM
        else:
            confidence = Confidence.LOW

        return AgentOutput(
            agent=self.role,
            kpis=kpis,
            insights=insights[:3],
            risks=risks[:3],
            recommendations=recommendations[:3],
            evidence=self._evidence,
            confidence=confidence
        )

    def _get_health_check_results(self) -> list:
        """Get latest health check results."""
        query = """
        SELECT
            check_name,
            status,
            metric_value,
            details,
            run_ts
        FROM retail.data_health_checks
        WHERE run_ts = (SELECT MAX(run_ts) FROM retail.data_health_checks)
        ORDER BY check_name
        """
        self._add_evidence(
            "retail.data_health_checks",
            "latest run_ts"
        )
        return self.db.execute_query(query)

    def _calculate_health_score(self, health_data: list) -> float:
        """Calculate overall health score from individual checks."""
        if not health_data:
            return 0.0

        total_checks = len(health_data)
        passed = sum(1 for h in health_data if h['status'] == 'PASS')
        warned = sum(1 for h in health_data if h['status'] == 'WARN')

        # PASS = 100%, WARN = 50%, FAIL = 0%
        score = (passed * 100 + warned * 50) / total_checks
        return round(score, 1)

    def _get_record_counts(self) -> dict:
        """Get record counts for key tables."""
        tables = [
            'pos_transaction', 'pos_transaction_line', 'sku', 'product',
            'store', 'store_inventory', 'customer', 'purchase_order'
        ]

        counts = {}
        for table in tables:
            query = f"SELECT COUNT(*) as cnt FROM retail.{table}"
            result = self.db.execute_query(query)
            counts[table] = result[0]['cnt'] if result else 0

        self._add_evidence(
            "retail.* (multiple tables)",
            "record counts"
        )
        return counts

    def _get_inventory_coverage(self) -> dict:
        """Calculate inventory coverage metrics."""
        query = """
        SELECT
            (SELECT COUNT(DISTINCT sku_id) FROM retail.store_inventory) as skus_in_inventory,
            (SELECT COUNT(*) FROM retail.sku WHERE status = 'ACTIVE') as active_skus,
            (SELECT COUNT(DISTINCT store_id) FROM retail.store_inventory) as stores_with_inventory,
            (SELECT COUNT(*) FROM retail.store) as total_stores
        """
        self._add_evidence(
            "retail.store_inventory + retail.sku + retail.store",
            "inventory coverage calculation"
        )
        result = self.db.execute_query(query)

        if result:
            data = result[0]
            active_skus = data['active_skus'] or 1
            total_stores = data['total_stores'] or 1
            return {
                'skus_in_inventory': data['skus_in_inventory'] or 0,
                'active_skus': active_skus,
                'stores_with_inventory': data['stores_with_inventory'] or 0,
                'total_stores': total_stores,
                'coverage_pct': (data['skus_in_inventory'] or 0) / active_skus * 100
            }
        return {'coverage_pct': 0}

    def _get_data_freshness(self) -> dict:
        """Calculate data freshness metrics."""
        query = """
        SELECT
            MAX(txn_ts)::date as last_txn_date,
            CURRENT_DATE - MAX(txn_ts)::date as days_since_last_txn,
            MIN(txn_ts)::date as first_txn_date
        FROM retail.pos_transaction
        """
        self._add_evidence(
            "retail.pos_transaction",
            "data freshness check"
        )
        result = self.db.execute_query(query)

        if result and result[0]['last_txn_date']:
            return {
                'last_txn_date': result[0]['last_txn_date'],
                'days_since_last_txn': result[0]['days_since_last_txn'] or 0,
                'first_txn_date': result[0]['first_txn_date']
            }
        return {'days_since_last_txn': 999, 'last_txn_date': None}

    def _get_referential_integrity(self) -> dict:
        """Check referential integrity across key relationships."""
        checks = {}

        # Check for orphan transaction lines
        query = """
        SELECT COUNT(*) as cnt
        FROM retail.pos_transaction_line ptl
        LEFT JOIN retail.pos_transaction pt ON pt.txn_id = ptl.txn_id
        WHERE pt.txn_id IS NULL
        """
        result = self.db.execute_query(query)
        checks['orphan_txn_lines'] = result[0]['cnt'] if result else 0

        # Check for orphan SKUs
        query = """
        SELECT COUNT(*) as cnt
        FROM retail.sku s
        LEFT JOIN retail.product p ON p.product_id = s.product_id
        WHERE p.product_id IS NULL
        """
        result = self.db.execute_query(query)
        checks['orphan_skus'] = result[0]['cnt'] if result else 0

        self._add_evidence(
            "retail.pos_transaction_line + retail.sku",
            "referential integrity checks"
        )
        return checks

    def _generate_insights(self, health_data: list, record_counts: dict, inventory_data: dict) -> list:
        """Generate CIO insights from the data."""
        insights = []

        # Health check summary
        if health_data:
            passed = sum(1 for h in health_data if h['status'] == 'PASS')
            total = len(health_data)
            insights.append(
                f"Data health: {passed}/{total} checks passing."
            )

        # Record volume insight
        txn_count = record_counts.get('pos_transaction', 0)
        sku_count = record_counts.get('sku', 0)
        insights.append(
            f"System contains {txn_count:,} transactions across {sku_count} SKUs."
        )

        # Inventory coverage insight
        coverage = inventory_data.get('coverage_pct', 0)
        insights.append(
            f"Inventory coverage at {coverage:.1f}% of active SKUs."
        )

        return insights

    def _identify_risks(self, health_data: list, freshness: dict) -> list:
        """Identify data/system risks."""
        risks = []

        # Check for failed health checks
        if health_data:
            failed = [h for h in health_data if h['status'] == 'FAIL']
            for f in failed[:2]:  # Report top 2 failures
                risks.append(f"FAIL: {f['check_name']} - {f['details']}")

        # Check data freshness
        days_old = freshness.get('days_since_last_txn', 0)
        if days_old > 30:
            risks.append(
                f"Data staleness: No transactions in {days_old} days. "
                "Consider data pipeline review."
            )
        elif days_old > 7:
            risks.append(
                f"Data freshness warning: Last transaction {days_old} days ago."
            )

        if not risks:
            risks.append("No critical data risks identified. Systems healthy.")

        return risks

    def _generate_recommendations(self, health_data: list, inventory_data: dict) -> list:
        """Generate CIO recommendations."""
        recommendations = []

        # Health check remediation
        if health_data:
            failed = [h for h in health_data if h['status'] == 'FAIL']
            warned = [h for h in health_data if h['status'] == 'WARN']

            if failed:
                recommendations.append(Recommendation(
                    action=f"Remediate {len(failed)} failing data health checks",
                    impact="Restore data integrity and agent reliability",
                    priority="High"
                ))

            if warned:
                recommendations.append(Recommendation(
                    action=f"Investigate {len(warned)} warning-level health checks",
                    impact="Prevent potential data quality degradation",
                    priority="Medium"
                ))

        # Inventory coverage
        coverage = inventory_data.get('coverage_pct', 0)
        if coverage < 95:
            recommendations.append(Recommendation(
                action="Increase inventory data coverage for all active SKUs",
                impact=f"Improve coverage from {coverage:.1f}% to 100%",
                priority="Medium"
            ))

        # Default recommendation
        if not recommendations:
            recommendations.append(Recommendation(
                action="Schedule routine data quality audit",
                impact="Maintain high data reliability for agent insights",
                priority="Low"
            ))

        return recommendations

    def run_health_checks(self) -> None:
        """Run and persist health checks to the data_health_checks table."""
        query = """
        INSERT INTO retail.data_health_checks (check_name, status, metric_value, details)

        -- Check 1: Orphan SKUs
        SELECT
            'orphan_skus' AS check_name,
            CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
            COUNT(*) AS metric_value,
            'SKUs without matching products' AS details
        FROM retail.sku s
        LEFT JOIN retail.product p ON s.product_id = p.product_id
        WHERE p.product_id IS NULL

        UNION ALL

        -- Check 2: Bad prices in transactions
        SELECT
            'bad_transaction_prices',
            CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
            COUNT(*),
            'Transaction lines with null or negative unit_price'
        FROM retail.pos_transaction_line
        WHERE unit_price IS NULL OR unit_price < 0

        UNION ALL

        -- Check 3: Negative inventory
        SELECT
            'negative_inventory',
            CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
            COUNT(*),
            'Store inventory records with negative on_hand_qty'
        FROM retail.store_inventory
        WHERE on_hand_qty < 0

        UNION ALL

        -- Check 4: Data freshness
        SELECT
            'data_freshness',
            CASE WHEN COUNT(*) > 0 THEN 'PASS' ELSE 'WARN' END,
            COUNT(*),
            'Transactions in last 30 days'
        FROM retail.pos_transaction
        WHERE txn_ts >= CURRENT_DATE - INTERVAL '30 days'

        UNION ALL

        -- Check 5: Referential integrity - PO lines
        SELECT
            'po_line_integrity',
            CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
            COUNT(*),
            'PO lines with invalid SKU references'
        FROM retail.purchase_order_line pol
        LEFT JOIN retail.sku s ON pol.sku_id = s.sku_id
        WHERE s.sku_id IS NULL;
        """
        conn = self.db.connect()
        with conn.cursor() as cur:
            cur.execute(query)
        conn.commit()


# CLI interface
if __name__ == "__main__":
    import sys

    agent = CIOAgent()

    # Check for --run-checks flag
    if len(sys.argv) > 1 and sys.argv[1] == "--run-checks":
        agent.run_health_checks()
        print("Health checks executed and persisted.")
    else:
        date_from = sys.argv[1] if len(sys.argv) > 1 else None
        date_to = sys.argv[2] if len(sys.argv) > 2 else None
        print(agent.run(date_from, date_to))
