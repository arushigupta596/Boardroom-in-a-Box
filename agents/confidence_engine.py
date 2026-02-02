"""
Confidence Engine - CIO-Driven Data Trust
==========================================
Computes confidence based on data quality, not vibes.

Confidence Factors:
- Data freshness (from CIO views)
- Null/error rates (quality checks)
- Coverage (% sales with customer_id, etc.)
- Health check status

Output: High/Medium/Low with reasons
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
from datetime import datetime, timedelta

from .base_agent import DatabaseConnection


class ConfidenceLevel(Enum):
    """Confidence levels."""
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


@dataclass
class ConfidenceFactor:
    """A single factor contributing to confidence."""
    name: str
    score: float  # 0-100
    weight: float  # 0-1
    status: str  # PASS/WARN/FAIL
    details: str
    threshold: Optional[float] = None
    actual: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "score": self.score,
            "weight": self.weight,
            "status": self.status,
            "details": self.details,
            "threshold": self.threshold,
            "actual": self.actual,
        }


@dataclass
class ConfidenceReport:
    """Complete confidence assessment."""
    level: ConfidenceLevel
    score: float  # 0-100
    factors: List[ConfidenceFactor]
    blocking_issues: List[str]
    warnings: List[str]
    timestamp: str
    can_proceed: bool
    summary: str

    def to_dict(self) -> dict:
        return {
            "level": self.level.value,
            "score": round(self.score, 1),
            "factors": [f.to_dict() for f in self.factors],
            "blocking_issues": self.blocking_issues,
            "warnings": self.warnings,
            "timestamp": self.timestamp,
            "can_proceed": self.can_proceed,
            "summary": self.summary,
        }


class ConfidenceEngine:
    """
    Computes data confidence based on CIO views.
    """

    # Factor weights (must sum to 1.0)
    WEIGHTS = {
        "data_freshness": 0.30,
        "health_checks": 0.25,
        "data_quality": 0.20,
        "coverage": 0.15,
        "integrity": 0.10,
    }

    # Thresholds
    FRESHNESS_SLA_DAYS = 1  # Data should be < 1 day old
    HEALTH_PASS_THRESHOLD = 80  # % of health checks passing
    QUALITY_THRESHOLD = 95  # % records without quality issues
    COVERAGE_THRESHOLD = 90  # % coverage required

    def __init__(self, db: DatabaseConnection = None):
        self.db = db or DatabaseConnection()

    def assess(self) -> ConfidenceReport:
        """
        Assess overall data confidence.

        Returns:
            ConfidenceReport with level, score, and factors
        """
        factors = []
        blocking_issues = []
        warnings = []

        # 1. Data Freshness
        freshness_factor = self._check_freshness()
        factors.append(freshness_factor)
        if freshness_factor.status == "FAIL":
            blocking_issues.append(freshness_factor.details)
        elif freshness_factor.status == "WARN":
            warnings.append(freshness_factor.details)

        # 2. Health Checks
        health_factor = self._check_health_status()
        factors.append(health_factor)
        if health_factor.status == "FAIL":
            blocking_issues.append(health_factor.details)
        elif health_factor.status == "WARN":
            warnings.append(health_factor.details)

        # 3. Data Quality
        quality_factor = self._check_data_quality()
        factors.append(quality_factor)
        if quality_factor.status == "FAIL":
            blocking_issues.append(quality_factor.details)
        elif quality_factor.status == "WARN":
            warnings.append(quality_factor.details)

        # 4. Coverage
        coverage_factor = self._check_coverage()
        factors.append(coverage_factor)
        if coverage_factor.status == "WARN":
            warnings.append(coverage_factor.details)

        # 5. Referential Integrity
        integrity_factor = self._check_integrity()
        factors.append(integrity_factor)
        if integrity_factor.status == "FAIL":
            blocking_issues.append(integrity_factor.details)
        elif integrity_factor.status == "WARN":
            warnings.append(integrity_factor.details)

        # Calculate overall score
        overall_score = sum(f.score * f.weight for f in factors)

        # Determine level
        if blocking_issues:
            level = ConfidenceLevel.LOW
            can_proceed = False
        elif overall_score >= 80:
            level = ConfidenceLevel.HIGH
            can_proceed = True
        elif overall_score >= 60:
            level = ConfidenceLevel.MEDIUM
            can_proceed = True
        else:
            level = ConfidenceLevel.LOW
            can_proceed = False

        # Generate summary
        if level == ConfidenceLevel.HIGH:
            summary = "Data quality excellent. All checks passing. Decisions can proceed with high confidence."
        elif level == ConfidenceLevel.MEDIUM:
            summary = f"Data quality acceptable with {len(warnings)} warnings. Review noted issues before critical decisions."
        else:
            summary = f"Data quality issues detected: {len(blocking_issues)} blocking. Resolve issues before proceeding."

        return ConfidenceReport(
            level=level,
            score=overall_score,
            factors=factors,
            blocking_issues=blocking_issues,
            warnings=warnings,
            timestamp=datetime.now().isoformat(),
            can_proceed=can_proceed,
            summary=summary,
        )

    def _check_freshness(self) -> ConfidenceFactor:
        """Check data freshness from CIO views."""
        try:
            query = """
            SELECT
                table_name,
                days_since_update
            FROM cio_views.data_freshness
            ORDER BY days_since_update DESC
            LIMIT 1
            """
            result = self.db.execute_query(query)

            if result:
                max_days = result[0]['days_since_update'] or 0
                stale_table = result[0]['table_name']

                if max_days <= self.FRESHNESS_SLA_DAYS:
                    return ConfidenceFactor(
                        name="Data Freshness",
                        score=100,
                        weight=self.WEIGHTS["data_freshness"],
                        status="PASS",
                        details=f"All data within {self.FRESHNESS_SLA_DAYS} day SLA",
                        threshold=self.FRESHNESS_SLA_DAYS,
                        actual=max_days,
                    )
                elif max_days <= 7:
                    score = max(50, 100 - (max_days * 10))
                    return ConfidenceFactor(
                        name="Data Freshness",
                        score=score,
                        weight=self.WEIGHTS["data_freshness"],
                        status="WARN",
                        details=f"{stale_table} is {max_days} days old",
                        threshold=self.FRESHNESS_SLA_DAYS,
                        actual=max_days,
                    )
                else:
                    return ConfidenceFactor(
                        name="Data Freshness",
                        score=20,
                        weight=self.WEIGHTS["data_freshness"],
                        status="FAIL",
                        details=f"STALE: {stale_table} is {max_days} days old",
                        threshold=self.FRESHNESS_SLA_DAYS,
                        actual=max_days,
                    )

            return self._default_factor("Data Freshness", self.WEIGHTS["data_freshness"])

        except Exception as e:
            return ConfidenceFactor(
                name="Data Freshness",
                score=50,
                weight=self.WEIGHTS["data_freshness"],
                status="WARN",
                details=f"Could not check freshness: {str(e)[:50]}",
            )

    def _check_health_status(self) -> ConfidenceFactor:
        """Check health check status from CIO views."""
        try:
            query = """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'PASS' THEN 1 ELSE 0 END) AS passed,
                SUM(CASE WHEN status = 'FAIL' THEN 1 ELSE 0 END) AS failed,
                SUM(CASE WHEN status = 'WARN' THEN 1 ELSE 0 END) AS warned
            FROM cio_views.health_check_status
            """
            result = self.db.execute_query(query)

            if result and result[0]['total']:
                total = result[0]['total']
                passed = result[0]['passed'] or 0
                failed = result[0]['failed'] or 0
                warned = result[0]['warned'] or 0

                pass_rate = (passed / total) * 100

                if failed > 0:
                    return ConfidenceFactor(
                        name="Health Checks",
                        score=30,
                        weight=self.WEIGHTS["health_checks"],
                        status="FAIL",
                        details=f"{failed}/{total} health checks FAILING",
                        threshold=self.HEALTH_PASS_THRESHOLD,
                        actual=pass_rate,
                    )
                elif pass_rate >= self.HEALTH_PASS_THRESHOLD:
                    return ConfidenceFactor(
                        name="Health Checks",
                        score=100,
                        weight=self.WEIGHTS["health_checks"],
                        status="PASS",
                        details=f"{passed}/{total} health checks passing",
                        threshold=self.HEALTH_PASS_THRESHOLD,
                        actual=pass_rate,
                    )
                else:
                    return ConfidenceFactor(
                        name="Health Checks",
                        score=60,
                        weight=self.WEIGHTS["health_checks"],
                        status="WARN",
                        details=f"{warned} warnings, {pass_rate:.0f}% pass rate",
                        threshold=self.HEALTH_PASS_THRESHOLD,
                        actual=pass_rate,
                    )

            return self._default_factor("Health Checks", self.WEIGHTS["health_checks"])

        except Exception as e:
            return ConfidenceFactor(
                name="Health Checks",
                score=50,
                weight=self.WEIGHTS["health_checks"],
                status="WARN",
                details=f"Could not check health: {str(e)[:50]}",
            )

    def _check_data_quality(self) -> ConfidenceFactor:
        """Check data quality from CIO views."""
        try:
            query = """
            SELECT
                SUM(issue_count) AS total_issues
            FROM cio_views.data_quality
            """
            result = self.db.execute_query(query)

            if result:
                total_issues = result[0]['total_issues'] or 0

                if total_issues == 0:
                    return ConfidenceFactor(
                        name="Data Quality",
                        score=100,
                        weight=self.WEIGHTS["data_quality"],
                        status="PASS",
                        details="No data quality issues detected",
                        actual=0,
                    )
                elif total_issues < 100:
                    return ConfidenceFactor(
                        name="Data Quality",
                        score=80,
                        weight=self.WEIGHTS["data_quality"],
                        status="WARN",
                        details=f"{total_issues} minor quality issues",
                        actual=total_issues,
                    )
                else:
                    return ConfidenceFactor(
                        name="Data Quality",
                        score=40,
                        weight=self.WEIGHTS["data_quality"],
                        status="FAIL",
                        details=f"{total_issues} quality issues require attention",
                        actual=total_issues,
                    )

            return self._default_factor("Data Quality", self.WEIGHTS["data_quality"])

        except Exception as e:
            return ConfidenceFactor(
                name="Data Quality",
                score=70,
                weight=self.WEIGHTS["data_quality"],
                status="WARN",
                details=f"Could not check quality: {str(e)[:50]}",
            )

    def _check_coverage(self) -> ConfidenceFactor:
        """Check data coverage from CIO views."""
        try:
            query = """
            SELECT
                sku_coverage_pct
            FROM cio_views.inventory_coverage
            """
            result = self.db.execute_query(query)

            if result:
                coverage = result[0]['sku_coverage_pct'] or 0

                if coverage >= self.COVERAGE_THRESHOLD:
                    return ConfidenceFactor(
                        name="Data Coverage",
                        score=100,
                        weight=self.WEIGHTS["coverage"],
                        status="PASS",
                        details=f"SKU coverage at {coverage:.1f}%",
                        threshold=self.COVERAGE_THRESHOLD,
                        actual=coverage,
                    )
                elif coverage >= 70:
                    return ConfidenceFactor(
                        name="Data Coverage",
                        score=70,
                        weight=self.WEIGHTS["coverage"],
                        status="WARN",
                        details=f"SKU coverage at {coverage:.1f}% (target: {self.COVERAGE_THRESHOLD}%)",
                        threshold=self.COVERAGE_THRESHOLD,
                        actual=coverage,
                    )
                else:
                    return ConfidenceFactor(
                        name="Data Coverage",
                        score=40,
                        weight=self.WEIGHTS["coverage"],
                        status="FAIL",
                        details=f"Low SKU coverage: {coverage:.1f}%",
                        threshold=self.COVERAGE_THRESHOLD,
                        actual=coverage,
                    )

            return self._default_factor("Data Coverage", self.WEIGHTS["coverage"])

        except Exception as e:
            return ConfidenceFactor(
                name="Data Coverage",
                score=70,
                weight=self.WEIGHTS["coverage"],
                status="WARN",
                details=f"Could not check coverage: {str(e)[:50]}",
            )

    def _check_integrity(self) -> ConfidenceFactor:
        """Check referential integrity from CIO views."""
        try:
            query = """
            SELECT
                SUM(violation_count) AS total_violations
            FROM cio_views.referential_integrity
            """
            result = self.db.execute_query(query)

            if result:
                violations = result[0]['total_violations'] or 0

                if violations == 0:
                    return ConfidenceFactor(
                        name="Referential Integrity",
                        score=100,
                        weight=self.WEIGHTS["integrity"],
                        status="PASS",
                        details="No integrity violations",
                        actual=0,
                    )
                elif violations < 10:
                    return ConfidenceFactor(
                        name="Referential Integrity",
                        score=70,
                        weight=self.WEIGHTS["integrity"],
                        status="WARN",
                        details=f"{violations} minor integrity issues",
                        actual=violations,
                    )
                else:
                    return ConfidenceFactor(
                        name="Referential Integrity",
                        score=30,
                        weight=self.WEIGHTS["integrity"],
                        status="FAIL",
                        details=f"{violations} integrity violations detected",
                        actual=violations,
                    )

            return self._default_factor("Referential Integrity", self.WEIGHTS["integrity"])

        except Exception as e:
            return ConfidenceFactor(
                name="Referential Integrity",
                score=70,
                weight=self.WEIGHTS["integrity"],
                status="WARN",
                details=f"Could not check integrity: {str(e)[:50]}",
            )

    def _default_factor(self, name: str, weight: float) -> ConfidenceFactor:
        """Return default factor when data unavailable."""
        return ConfidenceFactor(
            name=name,
            score=70,
            weight=weight,
            status="WARN",
            details="Data unavailable for check",
        )


# Quick assessment function
def assess_confidence(db: DatabaseConnection = None) -> ConfidenceReport:
    """Quick confidence assessment."""
    engine = ConfidenceEngine(db)
    return engine.assess()
