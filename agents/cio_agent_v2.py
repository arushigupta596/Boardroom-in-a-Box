"""
CIO Agent v2
============
Chief Information Officer - Uses ONLY allowed views from cio_views schema.
CIO has broadest data access for health monitoring but NO PII access.
"""

from typing import Optional
from .base_agent import BaseAgent, DatabaseConnection, GuardrailedDatabaseConnection
from .contract import (
    AgentOutput, AgentRole, KPI, Recommendation, Evidence,
    Trend, Confidence
)


class CIOAgentV2(BaseAgent):
    """
    CIO Agent v2 - Scope-enforced version with SQL guardrails.

    ALLOWED DATA SURFACE (cio_views schema only):
    - cio_views.health_check_status
    - cio_views.health_check_history
    - cio_views.data_freshness
    - cio_views.table_counts
    - cio_views.referential_integrity
    - cio_views.data_quality
    - cio_views.inventory_coverage
    - cio_views.pipeline_health
    - cio_views.available_views

    DENIED:
    - retail.customer (no PII access)

    SECURITY:
    - SQL guardrails enforce schema/table allowlist
    - Max 5 JOINs, 10000 row limit, 10s timeout
    - DDL/DML operations blocked
    """

    # Enable guardrails for this agent
    ENABLE_GUARDRAILS = True

    ALLOWED_VIEWS = [
        'cio_views.health_check_status',
        'cio_views.health_check_history',
        'cio_views.data_freshness',
        'cio_views.table_counts',
        'cio_views.referential_integrity',
        'cio_views.data_quality',
        'cio_views.inventory_coverage',
        'cio_views.pipeline_health',
        'cio_views.available_views',
    ]

    def _get_role_name(self) -> str:
        """Return role name for guardrails initialization."""
        return "CIO"

    @property
    def role(self) -> AgentRole:
        return AgentRole.CIO

    def analyze(self, date_from: str = None, date_to: str = None) -> AgentOutput:
        """Perform CIO analysis using allowed views only."""

        window = "Current"

        # Calculate KPIs from allowed views
        kpis = []

        # 1. Data Health Score from health check status
        health_data = self._get_health_status()
        health_score = self._calculate_health_score(health_data)
        kpis.append(KPI(
            name="Data Health Score",
            value=health_score,
            unit="%",
            trend=Trend.UP if health_score >= 90 else Trend.FLAT,
            window=window
        ))

        # 2. Total Records from table counts
        record_counts = self._get_table_counts()
        total_records = sum(r.get('row_count', 0) for r in record_counts)
        kpis.append(KPI(
            name="Total Records",
            value=total_records,
            unit="records",
            trend=Trend.FLAT,
            window=window
        ))

        # 3. Inventory Coverage from inventory coverage view
        coverage_data = self._get_inventory_coverage()
        kpis.append(KPI(
            name="SKU Coverage",
            value=round(coverage_data.get('sku_coverage_pct', 0), 1),
            unit="%",
            trend=Trend.FLAT,
            window=window
        ))

        # 4. Data Freshness from data freshness view
        freshness_data = self._get_data_freshness()
        max_days = max((f.get('days_since_update', 0) or 0) for f in freshness_data) if freshness_data else 0
        kpis.append(KPI(
            name="Data Freshness",
            value=max_days,
            unit="days",
            trend=Trend.DOWN if max_days > 7 else Trend.UP,
            window=window
        ))

        # Generate insights
        insights = self._generate_insights(health_data, record_counts, coverage_data)

        # Identify risks
        risks = self._identify_risks(health_data, freshness_data)

        # Generate recommendations
        recommendations = self._generate_recommendations(health_data, coverage_data)

        # Determine confidence
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

    def _get_health_status(self) -> list:
        """Get current health check status from cio_views.health_check_status."""
        query = "SELECT * FROM cio_views.health_check_status"
        self._add_evidence("cio_views.health_check_status", "latest health checks")
        return self.db.execute_query(query)

    def _calculate_health_score(self, health_data: list) -> float:
        """Calculate overall health score."""
        if not health_data:
            return 0.0

        total = len(health_data)
        passed = sum(1 for h in health_data if h.get('status') == 'PASS')
        warned = sum(1 for h in health_data if h.get('status') == 'WARN')

        score = (passed * 100 + warned * 50) / total
        return round(score, 1)

    def _get_health_history(self, days: int = 7) -> list:
        """Get health check history from cio_views.health_check_history."""
        query = f"""
        SELECT * FROM cio_views.health_check_history
        ORDER BY check_date DESC
        LIMIT {days}
        """
        self._add_evidence("cio_views.health_check_history", f"last {days} days")
        return self.db.execute_query(query)

    def _get_table_counts(self) -> list:
        """Get table record counts from cio_views.table_counts."""
        query = "SELECT * FROM cio_views.table_counts ORDER BY row_count DESC"
        self._add_evidence("cio_views.table_counts", "all monitored tables")
        return self.db.execute_query(query)

    def _get_data_freshness(self) -> list:
        """Get data freshness from cio_views.data_freshness."""
        query = "SELECT * FROM cio_views.data_freshness ORDER BY days_since_update DESC"
        self._add_evidence("cio_views.data_freshness", "transaction table freshness")
        return self.db.execute_query(query)

    def _get_referential_integrity(self) -> list:
        """Get referential integrity status from cio_views.referential_integrity."""
        query = "SELECT * FROM cio_views.referential_integrity"
        self._add_evidence("cio_views.referential_integrity", "integrity violation counts")
        return self.db.execute_query(query)

    def _get_data_quality(self) -> list:
        """Get data quality metrics from cio_views.data_quality."""
        query = "SELECT * FROM cio_views.data_quality"
        self._add_evidence("cio_views.data_quality", "quality issue counts")
        return self.db.execute_query(query)

    def _get_inventory_coverage(self) -> dict:
        """Get inventory coverage from cio_views.inventory_coverage."""
        query = "SELECT * FROM cio_views.inventory_coverage"
        self._add_evidence("cio_views.inventory_coverage", "inventory data coverage")
        result = self.db.execute_query(query)
        return result[0] if result else {}

    def _get_pipeline_health(self) -> list:
        """Get pipeline health from cio_views.pipeline_health."""
        query = "SELECT * FROM cio_views.pipeline_health LIMIT 5"
        self._add_evidence("cio_views.pipeline_health", "recent pipeline runs")
        return self.db.execute_query(query)

    def _get_available_views(self) -> list:
        """Get available views catalog from cio_views.available_views."""
        query = "SELECT * FROM cio_views.available_views"
        return self.db.execute_query(query)

    def _generate_insights(self, health_data: list, record_counts: list,
                          coverage_data: dict) -> list:
        """Generate CIO insights from allowed views."""
        insights = []

        # Health check summary
        if health_data:
            passed = sum(1 for h in health_data if h.get('status') == 'PASS')
            total = len(health_data)
            insights.append(f"Data health: {passed}/{total} checks passing.")

        # Record counts
        if record_counts:
            txn_records = next((r['row_count'] for r in record_counts
                               if r['table_name'] == 'pos_transaction'), 0)
            sku_records = next((r['row_count'] for r in record_counts
                               if r['table_name'] == 'sku'), 0)
            insights.append(f"System contains {txn_records:,} transactions across {sku_records} SKUs.")

        # Coverage
        coverage_pct = coverage_data.get('sku_coverage_pct', 0)
        insights.append(f"Inventory data coverage at {coverage_pct:.1f}% of active SKUs.")

        return insights

    def _identify_risks(self, health_data: list, freshness_data: list) -> list:
        """Identify data/system risks from allowed views."""
        risks = []

        # Failed health checks
        if health_data:
            failed = [h for h in health_data if h.get('status') == 'FAIL']
            for f in failed[:2]:
                risks.append(f"FAIL: {f['check_name']} - {f.get('details', 'No details')}")

        # Data freshness
        if freshness_data:
            stale = [f for f in freshness_data if (f.get('days_since_update') or 0) > 30]
            for s in stale[:1]:
                risks.append(
                    f"Data staleness: {s['table_name']} not updated in "
                    f"{s['days_since_update']} days."
                )

        # Referential integrity
        integrity = self._get_referential_integrity()
        violations = [i for i in integrity if (i.get('violation_count', 0) or 0) > 0]
        for v in violations[:1]:
            risks.append(f"Integrity issue: {v['violation_count']} {v['description']}")

        # Data quality
        quality = self._get_data_quality()
        issues = [q for q in quality if (q.get('issue_count', 0) or 0) > 0]
        for q in issues[:1]:
            risks.append(f"Quality issue: {q['issue_count']} {q['description']}")

        if not risks:
            risks.append("All systems healthy. No critical data risks identified.")

        return risks

    def _generate_recommendations(self, health_data: list, coverage_data: dict) -> list:
        """Generate CIO recommendations from allowed view data."""
        recommendations = []

        # Health check remediation
        if health_data:
            failed = [h for h in health_data if h.get('status') == 'FAIL']
            warned = [h for h in health_data if h.get('status') == 'WARN']

            if failed:
                recommendations.append(Recommendation(
                    action=f"Remediate {len(failed)} failing health checks immediately",
                    impact="Restore data integrity for reliable agent insights",
                    priority="High"
                ))

            if warned:
                recommendations.append(Recommendation(
                    action=f"Investigate {len(warned)} warning-level health checks",
                    impact="Prevent potential data quality degradation",
                    priority="Medium"
                ))

        # Coverage improvement
        coverage_pct = coverage_data.get('sku_coverage_pct', 0)
        if coverage_pct < 95:
            recommendations.append(Recommendation(
                action="Expand inventory tracking to cover all active SKUs",
                impact=f"Improve coverage from {coverage_pct:.1f}% to 100%",
                priority="Medium"
            ))

        if not recommendations:
            recommendations.append(Recommendation(
                action="Schedule routine data quality audit for next quarter",
                impact="Maintain high data reliability standards",
                priority="Low"
            ))

        return recommendations


# CLI interface
if __name__ == "__main__":
    import sys

    agent = CIOAgentV2()
    date_from = sys.argv[1] if len(sys.argv) > 1 else None
    date_to = sys.argv[2] if len(sys.argv) > 2 else None

    print(agent.run(date_from, date_to))
